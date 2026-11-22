"""Audit exact redundancy of original embeddings and verify post-shuffle provenance."""

import argparse
from collections import Counter
from contextlib import closing, contextmanager
import hashlib
import io
from itertools import groupby
import json
from pathlib import Path
import sqlite3
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.scripts.check_sampled_modalities import load_source, source_array
from data_pipeline.scripts.global_epitope_labels.build import ROOT, row_path, write_json


DIMENSIONS = (1024, 768)
WIDTH = sum(DIMENSIONS)
VARIANTS_PER_ORIGINAL = 26
SHUFFLE_COLUMNS = ("chunk_id", "row_idx_in_chunk", "source_dataset_id", "source_chunk_id",
                   "source_row_idx_in_chunk", "source_group_id", "group_id", "protein_group_id", "y")


def original_address(group, chunk_rows):
    return divmod((group - 1) * VARIANTS_PER_ORIGINAL, chunk_rows)


def vector_digest(vector):
    if not np.isfinite(vector).all():
        raise ValueError("Nonfinite embedding encountered.")
    canonical = np.where(vector == 0, np.float32(0), vector).astype("<f4", copy=False)
    return hashlib.sha256(canonical.tobytes()).digest()


def verified_representatives(items, vectors, columns):
    """Hashes nominate candidates. A class ID is assigned by exact vector comparison."""
    for _, group in groupby(items, key=lambda item: item[0]):
        representatives = []
        for _, row in group:
            # Keep addresses, not vectors, so even a large bucket has bounded vector storage.
            vector = vectors[row, columns]
            for representative in representatives:
                if np.array_equal(vector, vectors[representative, columns]):
                    yield row, representative
                    break
            else:
                representatives.append(row)
                yield row, row


@contextmanager
def csv_stream(path, prefix):
    if path.is_file():
        with path.open("rb") as raw:
            yield raw
        return
    archive = Path(str(path) + ".zst")
    with subprocess.Popen(["zstd", "-qdc", str(archive)], stdout=subprocess.PIPE) as proc:
        try:
            yield proc.stdout
        finally:
            if prefix and proc.poll() is None:
                proc.terminate()
        if not prefix and proc.wait():
            raise ValueError(f"Could not finish reading archived provenance: {archive}")


def shuffled_frames(path, chunk_rows, max_chunks):
    with csv_stream(path, max_chunks is not None) as stream:
        with pd.read_csv(stream, usecols=list(SHUFFLE_COLUMNS), dtype="int64", chunksize=chunk_rows) as batches:
            for number, frame in enumerate(batches):
                if max_chunks is not None and number >= max_chunks:
                    break
                if (not frame.chunk_id.eq(number).all()
                        or not np.array_equal(frame.row_idx_in_chunk.to_numpy(), np.arange(len(frame)))):
                    raise ValueError(f"Misaligned shuffled index at chunk {number}.")
                groups = frame.source_group_id.to_numpy()
                if (groups < 1).any():
                    raise ValueError(f"Invalid source group in shuffled chunk {number}.")
                positions = (groups - 1) * VARIANTS_PER_ORIGINAL
                is_original = ((positions // chunk_rows == frame.source_chunk_id.to_numpy())
                               & (positions % chunk_rows == frame.source_row_idx_in_chunk.to_numpy()))
                yield number, frame.loc[is_original, list(SHUFFLE_COLUMNS)]


class OriginalVectors:
    def __init__(self, source):
        self.primary_root = Path(source["master_index"]).parent
        self.secondary_root = Path(source["secondary"])
        self.primary_chunk = self.secondary_chunk = None
        self.secondary_ids = source_array(self.secondary_root / "group_id.npy")
        self.secondary_manifest = pd.read_csv(
            io.BytesIO(load_source(self.secondary_root / "chunks_manifest.csv"))
        )
        self.ends = self.secondary_manifest["end"].to_numpy()
        starts = self.secondary_manifest["start"].to_numpy()
        if (self.secondary_ids.ndim != 1 or (np.diff(self.secondary_ids) <= 0).any()
                or starts[0] != 0 or self.ends[-1] != len(self.secondary_ids)
                or not np.array_equal(starts[1:], self.ends[:-1])):
            raise ValueError(f"SecondaryBERT index is invalid: {self.secondary_root}")

    def vector_pair(self, chunk, row, group, protein, label):
        if chunk != self.primary_chunk:
            prefix = self.primary_root / f"chunk_{chunk:06d}"
            self.primary = source_array(Path(f"{prefix}_X.npy"))
            self.group = source_array(Path(f"{prefix}_group_id.npy"))
            self.protein = source_array(Path(f"{prefix}_protein_group_id.npy"))
            self.labels = source_array(Path(f"{prefix}_y.npy"))
            self.primary_chunk = chunk
            print(f"READ original {self.primary_root.parent.name} chunk {chunk}", flush=True)
        if (self.primary.dtype != np.float32 or self.primary.shape != (len(self.group), DIMENSIONS[0])
                or (int(self.group[row]), int(self.protein[row]), int(self.labels[row])) != (group, protein, label)):
            raise ValueError(f"Original ProtT5 address does not match metadata: {self.primary_root}/{chunk}:{row}.")
        position = int(np.searchsorted(self.secondary_ids, group))
        if position >= len(self.secondary_ids) or self.secondary_ids[position] != group:
            raise ValueError(f"Missing SecondaryBERT group: {self.secondary_root}/{group}.")
        slot = int(np.searchsorted(self.ends, position, side="right"))
        entry = self.secondary_manifest.iloc[slot]
        if slot != self.secondary_chunk:
            self.secondary = source_array(self.secondary_root / entry.x_file)
            self.secondary_group = source_array(self.secondary_root / entry.group_id_file)
            self.secondary_protein = source_array(self.secondary_root / entry.protein_group_id_file)
            self.secondary_chunk = slot
        offset = position - int(entry.start)
        if (self.secondary.shape != (int(entry.end - entry.start), DIMENSIONS[1])
                or self.secondary.dtype != np.float32
                or (int(self.secondary_group[offset]), int(self.secondary_protein[offset])) != (group, protein)):
            raise ValueError(f"SecondaryBERT address does not match original metadata: {self.secondary_root}/{group}.")
        return self.primary[row], self.secondary[offset]


def collect(dataset, config, sources, selected, vectors, db, chunk_rows):
    idx = 0
    columns = [config["sequence_column"], "group_id", "protein_group_id", "source_row_index",
               "contains_epitope", "global_contains_epitope"]
    for metadata in config["sources"]:
        family = metadata["mhc_family"]
        source = sources[family]
        wanted = None if selected is None else selected[source["id"]]
        vectors_source = OriginalVectors(source)
        read = 0
        for batch in pq.ParquetFile(row_path(dataset, metadata)).iter_batches(batch_size=20_000, columns=columns):
            records = []
            for seq, group, protein, source_row, label, global_label in zip(
                *(column.to_pylist() for column in batch.columns)
            ):
                group, protein = int(group), int(protein)
                if wanted is not None and group not in wanted:
                    continue
                if group != source_row + 1:
                    raise ValueError(f"Unexpected original group order: {family}/{source_row}.")
                chunk, row = original_address(group, chunk_rows)
                p, s = vectors_source.vector_pair(chunk, row, group, protein, label)
                vectors[idx, :DIMENSIONS[0]], vectors[idx, DIMENSIONS[0]:] = p, s
                records.append((idx, source["id"], group, protein, source_row, label, global_label,
                                seq, chunk, row, vector_digest(p), vector_digest(s), None, None))
                idx += 1
                read += 1
            with db:
                db.executemany("INSERT INTO obs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", records)
            if wanted is not None and read == len(wanted):
                break
        expected = len(wanted) if wanted is not None else pq.ParquetFile(row_path(dataset, metadata)).metadata.num_rows
        if read != expected:
            raise ValueError(f"Incomplete original audit for {family}: {read} != {expected}.")
        print(f"ORIGINAL {family}: {read:,} observations", flush=True)
        del vectors_source
    vectors.flush()
    return idx


def register_classes(db, vectors, work, count):
    assignments = np.memmap(work / "assignments.bin", mode="w+", dtype="int64", shape=(count, 2))
    for i, (digest, columns) in enumerate((
        ("hp", slice(0, DIMENSIONS[0])), ("hs", slice(DIMENSIONS[0], WIDTH)),
    )):
        db.execute(f"CREATE INDEX {digest}_lookup ON obs({digest})")
        rows = db.execute(f"SELECT {digest}, id FROM obs ORDER BY {digest}, id")
        for idx, representative in verified_representatives(rows, vectors, columns):
            assignments[idx, i] = representative
        print(f"EXACT classes verified for {digest}", flush=True)
        db.execute(f"DROP INDEX {digest}_lookup")
    for offset in range(0, count, 50_000):
        with db:
            db.executemany("UPDATE obs SET p=?,s=? WHERE id=?", (
                (int(p), int(s), idx) for idx, (p, s) in enumerate(assignments[offset:offset + 50_000], offset)
            ))
    del assignments


def compare_shuffle(db, vectors, frames, combined_root, sources, expected_full):
    offsets = {source["id"]: source["group_id_offset"] for source in sources.values()}
    counts = Counter({"compared": 0, "primary_different": 0, "secondary_different": 0})
    by_source = Counter()
    examples = []
    db.execute("CREATE TEMP TABLE seen (id INTEGER PRIMARY KEY)")
    db.execute("CREATE INDEX source_address ON obs(sid,gid)")
    for number, frame in frames:
        selected = []
        for _, shuffled_row, sid, original_chunk, original_row, group, global_group, protein, label in frame.itertuples(index=False, name=None):
            match = db.execute("SELECT id,chunk,slot,protein,original_label FROM obs WHERE sid=? AND gid=?",
                               (sid, group)).fetchone()
            if match is None:
                if expected_full:
                    raise ValueError(f"Missing pre-shuffle row: {sid}/{group}")
                continue
            idx, chunk, slot, parent, original_label = match
            if (chunk, slot, parent, original_label, group + offsets[sid]) != (
                original_chunk, original_row, protein, label, global_group
            ):
                raise ValueError(f"Shuffled provenance does not match source: {number}:{shuffled_row}.")
            selected.append((idx, shuffled_row, sid, original_chunk, original_row))
        if not selected:
            continue
        combined = np.load(combined_root / f"chunk_{number:06d}_X.npy", mmap_mode="r", allow_pickle=False)
        if combined.ndim != 2 or combined.shape[1] != WIDTH or combined.dtype != np.float32:
            raise ValueError(f"Unexpected concatenated feature schema: {number}.")
        with db:
            db.executemany("INSERT INTO seen VALUES (?)", ((idx,) for idx, *_ in selected))
        for idx, row, sid, chunk, slot in selected:
            original, shuffled = vectors[idx], combined[row]
            p_equal = np.array_equal(original[:DIMENSIONS[0]], shuffled[:DIMENSIONS[0]])
            s_equal = np.array_equal(original[DIMENSIONS[0]:], shuffled[DIMENSIONS[0]:])
            counts.update(compared=1, primary_different=int(not p_equal), secondary_different=int(not s_equal))
            by_source[sid] += 1
            if len(examples) < 12 and (not p_equal or not s_equal or len(examples) < 3):
                examples.append(dict(source_dataset_id=sid, original_chunk=chunk, original_row=slot,
                                     shuffled_chunk=number, shuffled_row=row,
                                     primary_exact=p_equal, secondary_exact=s_equal))
        print(f"SHUFFLE chunk {number}: {counts['compared']:,} originals compared", flush=True)
    if expected_full and counts["compared"] != len(vectors):
        raise ValueError("The shuffled index did not account for every original observation.")
    return dict(counts, by_source=dict(by_source), examples=examples)


def summarize(db, output):
    db.execute("CREATE INDEX representation ON obs(seq,global_label,p,s)")
    db.execute("CREATE INDEX modality_pair ON obs(p,s)")
    totals = Counter({key: 0 for key in (
        "distinct_sequences", "repeated_sequences", "primary_all_equal", "secondary_all_equal",
        "both_all_equal", "primary_any_equal_pair", "secondary_any_equal_pair", "both_any_equal_pair",
        "multiple_representations",
    )})
    for n, p, s, pair in db.execute("""
        SELECT SUM(n), COUNT(DISTINCT p), COUNT(DISTINCT s), COUNT(*)
        FROM (SELECT seq,p,s,COUNT(*) AS n FROM obs GROUP BY seq,p,s) GROUP BY seq
    """):
        totals["distinct_sequences"] += 1
        if n > 1:
            totals.update(repeated_sequences=1, primary_all_equal=int(p == 1),
                          secondary_all_equal=int(s == 1), both_all_equal=int(pair == 1),
                          primary_any_equal_pair=int(p < n), secondary_any_equal_pair=int(s < n),
                          both_any_equal_pair=int(pair < n), multiple_representations=int(pair > 1))
    totals["rows"] = db.execute("SELECT COUNT(*) FROM obs").fetchone()[0]
    totals["remaining_rows"] = db.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM obs GROUP BY seq,global_label,p,s)"
    ).fetchone()[0]
    totals["removable_rows"] = totals["rows"] - totals["remaining_rows"]
    totals["embedding_pairs_with_different_global_labels"] = db.execute("""
        SELECT COUNT(*) FROM (SELECT 1 FROM obs GROUP BY p,s HAVING MIN(global_label) <> MAX(global_label))
    """).fetchone()[0]
    totals["sequences_with_different_global_labels"] = db.execute("""
        SELECT COUNT(*) FROM (SELECT 1 FROM obs GROUP BY seq HAVING MIN(global_label) <> MAX(global_label))
    """).fetchone()[0]
    names = ("source_dataset_id", "source_row_index", "source_group_id", "source_protein_group_id",
             "original_seq", "global_contains_epitope", "primary_chunk", "primary_row",
             "representative_source_dataset_id", "representative_source_row_index")
    schema = pa.schema([(name, pa.string() if name == "original_seq" else pa.int64()) for name in names])
    query = """
        WITH candidates AS (
           SELECT sid,source_row,gid,protein,seq,global_label,chunk,slot,
                  MIN(id) OVER (PARTITION BY seq,global_label,p,s) AS representative
           FROM obs
        )
        SELECT a.sid,a.source_row,a.gid,a.protein,a.seq,a.global_label,a.chunk,a.slot,b.sid,b.source_row
        FROM candidates a JOIN obs b ON a.representative=b.id
    """
    cursor = db.execute(query)
    examples = []
    with pq.ParquetWriter(output / "proposed_provenance.parquet", schema, compression="zstd") as writer:
        while rows := cursor.fetchmany(50_000):
            columns = list(zip(*rows))
            writer.write_table(pa.Table.from_arrays([pa.array(c, type=f.type) for c, f in zip(columns, schema)],
                                                    schema=schema))
            for row in rows:
                if len(examples) < 5 and (row[0], row[1]) != (row[-2], row[-1]):
                    examples.append(dict(zip(names, row)))
    return dict(totals, duplicate_examples=examples)


def run(dataset, combined, shuffled_index, output, sample, shuffle_chunks, *, scratch=None):
    config = json.loads((dataset / "config.json").read_text())
    global_summary = json.loads((dataset / "summary.json").read_text())
    manifest = json.loads((combined / "reorder_manifest.json").read_text())
    chunk_rows = manifest["chunk_rows"]
    if (global_summary["status"] != "validated" or config["rows_per_family"] is not None
            or manifest["rows"] != VARIANTS_PER_ORIGINAL * global_summary["original_rows"]):
        raise ValueError("Expected the validated full global dataset and the aligned 26-row augmentation manifest.")
    sources = {Path(source["master_index"]).parts[-3]: source for source in manifest["sources"]}
    row_sources = {source["mhc_family"]: source for source in config["sources"]}
    if set(sources) != set(row_sources):
        raise ValueError("Global and embedding family manifests differ.")
    protected = [dataset, combined, shuffled_index.parent]
    for source in sources.values():
        protected.extend((Path(source["master_index"]).parent, Path(source["secondary"])))
    if any(output.resolve().is_relative_to(root.resolve()) for root in protected):
        raise ValueError("Expected a separate output directory.")
    if scratch is not None:
        scratch = scratch.resolve(strict=True)
        if any(scratch.is_relative_to(root.resolve()) for root in protected):
            raise ValueError("Scratch must be separate from the input stores.")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "sources.json", {source["id"]: dict(source, family=family) for family, source in sources.items()})
    first_chunks = None
    selected = None
    if sample is not None:
        first_chunks = list(shuffled_frames(shuffled_index, chunk_rows, shuffle_chunks))
        selected = {}
        for family, source in sources.items():
            sid = source["id"]
            available = pq.ParquetFile(row_path(dataset, row_sources[family])).metadata.num_rows
            selected[sid] = set(range(1, min(sample, available) + 1))
        for _, frame in first_chunks:
            for sid, group in frame.loc[frame.source_chunk_id == 0,
                                        ["source_dataset_id", "source_group_id"]].itertuples(index=False, name=None):
                selected[sid].add(group)
    count = sum(map(len, selected.values())) if selected is not None else global_summary["original_rows"]
    with TemporaryDirectory(prefix="exact-work-", dir=scratch or output) as directory:
        work = Path(directory)
        db = sqlite3.connect(work / "audit.sqlite")
        db.executescript("""
            PRAGMA cache_size=-131072;
            CREATE TABLE obs (
                id INTEGER PRIMARY KEY, sid INTEGER,gid INTEGER,protein INTEGER,source_row INTEGER,
                original_label INTEGER,global_label INTEGER,seq TEXT,chunk INTEGER,slot INTEGER,
                hp BLOB,hs BLOB,p INTEGER,s INTEGER
            );
        """)
        vectors = np.memmap(work / "vectors.bin", mode="w+", dtype="float32", shape=(count, WIDTH))
        with closing(db):
            if collect(dataset, config, sources, selected, vectors, db, chunk_rows) != count:
                raise ValueError("Original observation count differs from the requested scope.")
            register_classes(db, vectors, work, count)
            post_shuffle = compare_shuffle(
                db, vectors, first_chunks if first_chunks is not None else shuffled_frames(shuffled_index, chunk_rows, None),
                combined / "mixed/classification_mixed_ProtT5_chunks", sources, sample is None,
            )
            summary = summarize(db, output)
        del vectors
    summary.update(scope="full" if sample is None else "prefix_plus_addressed_shuffle_sample",
                   groups_per_family=sample, shuffle_chunks=shuffle_chunks if sample is not None else manifest["chunks"],
                   full_dataset_distinct_sequences=global_summary["unique_sequences"], post_shuffle=post_shuffle)
    write_json(output / "summary.json", summary)
    descriptions = {
        "rows": "Observaciones originales comparadas", "distinct_sequences": "Secuencias distintas en la auditoría",
        "repeated_sequences": "Secuencias repetidas", "primary_all_equal": "Repetidas con todos los ProtT5 iguales",
        "secondary_all_equal": "Repetidas con todos los SecondaryBERT iguales",
        "both_all_equal": "Repetidas con ambas modalidades iguales en todas sus observaciones",
        "primary_any_equal_pair": "Repetidas con algún par ProtT5 igual",
        "secondary_any_equal_pair": "Repetidas con algún par SecondaryBERT igual",
        "both_any_equal_pair": "Repetidas con algún par igual en ambas modalidades",
        "multiple_representations": "Secuencias con más de una representación conjunta",
        "removable_rows": "Filas que podrían retirarse en el alcance auditado",
        "remaining_rows": "Filas que quedarían en el alcance auditado",
        "embedding_pairs_with_different_global_labels": "Pares de embeddings idénticos con etiquetas globales diferentes",
        "sequences_with_different_global_labels": "Secuencias exactas con etiquetas globales contradictorias",
    }
    report = ["# Auditoría de redundancia exacta de embeddings", "",
              f"Alcance: {summary['scope']}. Corpus: {summary['full_dataset_distinct_sequences']:,} secuencias distintas.", "",
              "| Medida | Total |", "|---|---:|"]
    report.extend(f"| {description} | {summary[key]:,} |" for key, description in descriptions.items())
    report.extend(["", "## Comparación tras barajar", "",
                   f"Se cotejaron {post_shuffle['compared']:,} originales con direcciones de origen explícitas. "
                   f"Diferencias ProtT5: {post_shuffle['primary_different']:,}. "
                   f"Diferencias SecondaryBERT: {post_shuffle['secondary_different']:,}.", "",
                   "## Procedencia y límites", "",
                   "El primer registro de cada grupo de 26 corresponde a la secuencia original. "
                   "Las direcciones y los metadatos del grupo, proteína y etiqueta original se verifican frente a los archivos. "
                   "La deduplicación propuesta usa secuencia, ambas modalidades y etiqueta global.",
                   "SHA-256 solo selecciona candidatos. Cada igualdad declarada se verifica valor por valor en float32, "
                   "sin tolerancia. Los ceros con signo se consideran numéricamente iguales. Los no finitos se rechazan.",
                   "La muestra combina prefijos por familia y originales del primer bloque local rastreados en los primeros "
                   "chunks barajados. Sus proporciones no se extrapolan al corpus.",
                   "La tabla propuesta conserva una fila por observación y su representante. Revisar conflictos y decidir "
                   "cómo preservar la procedencia y los futuros splits antes de aplicar una limpieza.", "", "## Ejemplos", ""])
    for example in summary["duplicate_examples"]:
        report.append(f"- Secuencia `{example['original_seq']}`, origen {example['source_dataset_id']}:"
                      f"{example['source_row_index']} → representante {example['representative_source_dataset_id']}:"
                      f"{example['representative_source_row_index']}.")
    for example in post_shuffle["examples"][:3]:
        report.append(f"- Origen {example['source_dataset_id']}:{example['original_chunk']}:{example['original_row']} → "
                      f"barajado {example['shuffled_chunk']}:{example['shuffled_row']}, "
                      f"ProtT5 exacto {example['primary_exact']}, SecondaryBERT exacto {example['secondary_exact']}.")
    (output / "report.md").write_text("\n".join(report) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/global_epitope_labels")
    parser.add_argument("--combined", type=Path, default=ROOT / "data/data_input_nn_shuffled_concatenate")
    parser.add_argument("--shuffled-index", type=Path, default=ROOT / (
        "data/data_input_nn_shuffled/mixed/classification_mixed_ProtT5_chunks/master_index.csv"
    ))
    parser.add_argument("--output", type=Path, required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--groups-per-family", type=int)
    scope.add_argument("--full", action="store_true")
    parser.add_argument("--shuffle-chunks", type=int, default=12)
    parser.add_argument("--scratch", type=Path, help="Existing fast disk directory for temporary vectors and indexes.")
    args = parser.parse_args()
    if (args.groups_per_family is not None and args.groups_per_family < 1) or args.shuffle_chunks < 1:
        parser.error("Sample sizes must be positive.")
    run(args.dataset, args.combined, args.shuffled_index, args.output,
        args.groups_per_family, args.shuffle_chunks, scratch=args.scratch)


if __name__ == "__main__":
    main()
