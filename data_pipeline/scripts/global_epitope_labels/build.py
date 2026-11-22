#!/usr/bin/env python3
"""Build exact-sequence annotation tables from the original classification CSVs."""

import argparse
from collections import Counter
from contextlib import closing, contextmanager
import csv
import fcntl
import json
from pathlib import Path
import sqlite3
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "data/used_data/contradiction_sources"
FAMILIES = (
    ("human", "mhc-I", "HLA-A"), ("human", "mhc-I", "HLA-B"),
    ("human", "mhc-I", "HLA-C"), ("human", "mhc-II", "HLA-DP"),
    ("human", "mhc-II", "HLA-DQ"), ("human", "mhc-II", "HLA-DR"),
    ("mouse", "mhc-I", "H2-D"), ("mouse", "mhc-I", "H2-K"),
    ("mouse", "mhc-I", "H2-L"), ("mouse", "mhc-II", "H2-IA"),
    ("mouse", "mhc-II", "H2-IE"),
)
FAMILY_NAMES = tuple(family for _, _, family in FAMILIES)
REQUIRED = {"contains_epitope", "selected_epitope", "epitope_pos_score",
            "protein_group_id", "group_id"}
PROVENANCE = [
    ("organism", pa.string()), ("mhc_class", pa.string()),
    ("mhc_family", pa.string()), ("source_file", pa.string()),
    ("source_row_index", pa.int64()),
]
GLOBAL = [
    ("global_contains_epitope", pa.int8()), ("global_label_status", pa.string()),
    ("global_positive_family_count", pa.int8()),
    ("global_positive_families", pa.list_(pa.string())),
    ("global_positive_evidence_count", pa.int64()),
]
UNIQUE_SCHEMA = pa.schema([("original_seq", pa.string()), *GLOBAL])
COUNTS_SQL = """
    CREATE TABLE IF NOT EXISTS counts (
        sequence TEXT PRIMARY KEY COLLATE BINARY,
        negative INTEGER NOT NULL, positive INTEGER NOT NULL, families INTEGER NOT NULL
    ) WITHOUT ROWID
"""


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def input_config(root, batch_rows, row_limit):
    files = []
    columns = None
    for organism, mhc_class, family in FAMILIES:
        filename = f"classification_{organism}_{mhc_class}_{family}.csv"
        relative = Path(organism, mhc_class, family, filename)
        path = root / relative
        with path.open(newline="", encoding="utf-8-sig") as handle:
            header = next(csv.reader(handle))
        if columns is None:
            columns = header
        if header != columns or len(set(header)) != len(header):
            raise ValueError(f"Inconsistent or duplicate CSV columns: {path}")
        if not REQUIRED.issubset(header) or not {"25aa_seq", "original_seq"}.intersection(header):
            raise ValueError(f"Required classification columns missing: {path}")
        if set(header).intersection(name for name, _ in PROVENANCE + GLOBAL):
            raise ValueError(f"CSV already contains output columns: {path}")
        stat = path.stat()
        files.append({
            "file": relative.as_posix(), "organism": organism, "mhc_class": mhc_class,
            "mhc_family": family, "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        })
    return {
        "version": 1, "sources_root": str(root), "sources": files, "columns": columns,
        "sequence_column": "original_seq" if "original_seq" in columns else "25aa_seq",
        "batch_rows": batch_rows, "rows_per_family": row_limit, "compression": "zstd",
        "sequence_match": "exact, case-sensitive, no normalization",
        "row_index": "zero-based CSV data record within source_file",
    }


def check_inputs(config):
    actual = input_config(
        Path(config["sources_root"]), config["batch_rows"], config["rows_per_family"],
    )
    if actual != config:
        raise ValueError("The source manifest changed. Use a new output directory.")


@contextmanager
def output_lock(output):
    with (output / ".run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def open_index(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA cache_size=-131072")
    db.execute("PRAGMA temp_store=MEMORY")
    db.execute("PRAGMA wal_autocheckpoint=4096")
    db.execute(COUNTS_SQL)
    return db


def frames(config, source):
    path = Path(config["sources_root"]) / source["file"]
    with pd.read_csv(
        path, encoding="utf-8-sig", dtype=str, na_filter=False,
        chunksize=config["batch_rows"], nrows=config["rows_per_family"],
    ) as reader:
        for frame in reader:
            if frame.empty:
                continue
            seq = frame[config["sequence_column"]]
            if (list(frame.columns) != config["columns"] or not isinstance(frame.index, pd.RangeIndex)
                    or not seq.str.len().eq(25).all()
                    or not frame["contains_epitope"].isin(("0", "1")).all()):
                raise ValueError(f"Malformed sequence, label or CSV record: {path}, row {frame.index[0]}")
            if {"original_seq", "25aa_seq"}.issubset(frame) and not frame.original_seq.equals(frame["25aa_seq"]):
                raise ValueError(f"Sequence columns disagree: {path}, row {frame.index[0]}")
            yield frame


def add_counts(db, sequences, labels, family_index):
    positive = Counter(seq for seq, label in zip(sequences, labels) if label == "1")
    negative = Counter(seq for seq, label in zip(sequences, labels) if label == "0")
    bit = 1 << family_index
    records = ((seq, negative[seq], positive[seq], bit if seq in positive else 0)
               for seq in sorted(negative.keys() | positive.keys()))
    db.executemany("""
        INSERT INTO counts VALUES (?, ?, ?, ?)
        ON CONFLICT(sequence) DO UPDATE SET
            negative = counts.negative + excluded.negative,
            positive = counts.positive + excluded.positive,
            families = counts.families | excluded.families
    """, records)


def build_index(db, config, checkpoint=None):
    db.execute("""
        CREATE TABLE IF NOT EXISTS completed (
            family INTEGER NOT NULL, batch INTEGER NOT NULL, rows INTEGER NOT NULL,
            PRIMARY KEY (family, batch)
        ) WITHOUT ROWID
    """)
    for i, source in enumerate(config["sources"]):
        started = time.monotonic()
        done = dict(db.execute("SELECT batch, rows FROM completed WHERE family=?", (i,)))
        if -1 in done:
            print(f"INDEX {source['mhc_family']}: resumed {done[-1]:,} rows", flush=True)
            continue
        rows = 0
        for batch, frame in enumerate(frames(config, source)):
            rows += len(frame)
            if batch not in done:
                with db:
                    add_counts(db, frame[config["sequence_column"]], frame["contains_epitope"], i)
                    db.execute("INSERT INTO completed VALUES (?, ?, ?)", (i, batch, len(frame)))
                if checkpoint is not None and (batch + 1) % 20 == 0:
                    checkpoint()
            elif done[batch] != len(frame):
                raise ValueError(f"Previously indexed batch changed: {source['file']}")
            print(f"INDEX {source['mhc_family']} {rows:,} rows ({time.monotonic()-started:.1f}s)", flush=True)
        if not rows:
            raise ValueError(f"No source rows: {source['file']}")
        with db:
            db.execute("INSERT INTO completed VALUES (?, -1, ?)", (i, rows))
        if checkpoint is not None:
            checkpoint()


def annotation(positive, mask):
    families = [name for i, name in enumerate(FAMILY_NAMES) if mask & (1 << i)]
    return int(positive > 0), "positive" if positive else "unlabeled", len(families), families, positive


def row_schema(config):
    fields = [(name, pa.int8() if name == "contains_epitope" else pa.string())
              for name in config["columns"]]
    return pa.schema([*fields, *PROVENANCE, *GLOBAL])


def annotations_for(db, sequences):
    db.execute("CREATE TEMP TABLE IF NOT EXISTS requested (sequence TEXT PRIMARY KEY) WITHOUT ROWID")
    db.execute("DELETE FROM requested")
    db.executemany("INSERT INTO requested VALUES (?)", ((seq,) for seq in dict.fromkeys(sequences)))
    return {seq: annotation(positive, mask) for seq, positive, mask in db.execute("""
        SELECT counts.sequence, counts.positive, counts.families
        FROM requested CROSS JOIN counts ON counts.sequence = requested.sequence
    """)}


def table_from_columns(columns, schema):
    return pa.Table.from_arrays(
        [pa.array(values, type=field.type) for values, field in zip(columns, schema, strict=True)],
        schema=schema,
    )


def row_table(frame, source, start, config, db):
    sequences = frame[config["sequence_column"]]
    lookup = annotations_for(db, sequences)
    global_columns = list(zip(*(lookup[seq] for seq in sequences)))
    original = [frame[column].astype("int8") if column == "contains_epitope" else frame[column]
                for column in config["columns"]]
    context = [[source[key]] * len(frame) for key in ("organism", "mhc_class", "mhc_family", "file")]
    return table_from_columns(
        [*original, *context, range(start, start + len(frame)), *global_columns],
        row_schema(config),
    )


def row_path(output, source):
    return output / "rows" / (
        f"{source['organism']}_{source['mhc_class']}_{source['mhc_family']}.parquet"
    )


def export_rows(db, config, output):
    (output / "rows").mkdir(exist_ok=True)
    for source in config["sources"]:
        destination = row_path(output, source)
        if destination.is_file():
            continue
        partial = destination.with_suffix(".partial")
        started = time.monotonic()
        start = 0
        with pq.ParquetWriter(partial, row_schema(config), compression=config["compression"]) as writer:
            for frame in frames(config, source):
                writer.write_table(row_table(frame, source, start, config, db))
                start += len(frame)
                print(f"EXPORT {source['mhc_family']} {start:,} rows ({time.monotonic()-started:.1f}s)", flush=True)
        partial.replace(destination)


def unique_table(records):
    columns = zip(*((seq, *annotation(positive, mask)) for seq, _, positive, mask in records))
    return table_from_columns(columns, UNIQUE_SCHEMA)


def count_batches(db, batch_rows):
    cursor = db.execute("SELECT sequence, negative, positive, families FROM counts ORDER BY sequence")
    while batch := cursor.fetchmany(batch_rows):
        yield batch


def export_unique(db, config, output):
    destination = output / "sequences.parquet"
    if destination.is_file():
        return
    partial = destination.with_suffix(".partial")
    started = time.monotonic()
    with pq.ParquetWriter(partial, UNIQUE_SCHEMA, compression=config["compression"]) as writer:
        for i, records in enumerate(count_batches(db, config["batch_rows"]), 1):
            writer.write_table(unique_table(records))
            if i == 1 or i % 10 == 0:
                print(f"EXPORT unique batch {i:,} ({time.monotonic()-started:.1f}s)", flush=True)
    partial.replace(destination)


def build(output, sources=SOURCES, batch_rows=100_000, rows_per_family=None, *, ram_index=False):
    from data_pipeline.scripts.global_epitope_labels.validate import validate_locked

    output, sources = Path(output).resolve(), Path(sources).resolve()
    if output == sources or output.is_relative_to(sources) or sources.is_relative_to(output):
        raise ValueError("Input and output directories must be separate.")
    if not 1 <= batch_rows <= 1_000_000 or (rows_per_family is not None and rows_per_family < 1):
        raise ValueError("Batch size must be 1–1,000,000 rows and sample size must be positive.")
    config = input_config(sources, batch_rows, rows_per_family)
    output.mkdir(parents=True, exist_ok=True)
    with output_lock(output):
        started = time.monotonic()
        config_path = output / "config.json"
        if config_path.exists():
            if json.loads(config_path.read_text(encoding="utf-8")) != config:
                raise ValueError("The input manifest or configuration changed. Use a new output directory.")
        else:
            if set(output.iterdir()) - {output / ".run.lock", output / "config.json.partial"}:
                raise ValueError(f"Output directory is not empty: {output}")
            write_json(config_path, config)
        with closing(open_index(output / "index.sqlite")) as persisted:
            if ram_index:
                with closing(open_index(":memory:")) as active:
                    persisted.backup(active)

                    def checkpoint():
                        active.backup(persisted)
                        print("CHECKPOINT index committed to disk", flush=True)

                    process_index(active, config, output, checkpoint)
            else:
                process_index(persisted, config, output)
        print(f"BUILD finished in {time.monotonic()-started:.1f}s", flush=True)
        return validate_locked(output, config, ram_index=ram_index)


def process_index(db, config, output, checkpoint=None):
    build_index(db, config, checkpoint)
    check_inputs(config)
    export_rows(db, config, output)
    export_unique(db, config, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=SOURCES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-rows", type=int, default=100_000)
    parser.add_argument("--ram-index", action="store_true",
                        help="Use an in-memory working index with transactional disk checkpoints.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--full", action="store_true", help="Read every original row.")
    scope.add_argument("--rows-per-family", type=int, help="Cap the CSV prefix per family for a smoke test.")
    args = parser.parse_args()
    build(args.output, args.sources, args.batch_rows, args.rows_per_family, ram_index=args.ram_index)


if __name__ == "__main__":
    # Also support direct invocation from the repository's scripts directory.
    if not __package__:
        import sys
        sys.path.insert(0, str(ROOT))
    main()
