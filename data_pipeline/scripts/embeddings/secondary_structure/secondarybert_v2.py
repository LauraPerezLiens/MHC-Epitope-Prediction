"""Index canonical SecondaryBERT archives and embed exact audited C/H/E keys."""
import argparse
from contextlib import closing, contextmanager
import hashlib
import io
import itertools
import json
from pathlib import Path
import re
import sqlite3
import subprocess
from time import perf_counter

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import generate_secondary_bert_embeddings as generator

ROOT = generator.MODEL_DIR.parents[1]
AUDIT = ROOT / "results/nap_cnb_v2_embedding_audit"
OUTPUT = ROOT / "results/nap_cnb_v2_secondarybert"
FINGERPRINT = "7714351fc71dd4c3b929d9835d00bdb7d4869e982b9fb32054e4bf9c3846b72d"
WEIGHTS = "9f116bddfad5f9232ca4d6e1f9cc183edfb9a60d46b6925ba310f245d7e30aa3"
KEY = re.compile("[CHE]{25}")
BATCH = 256
INVENTORIES = (
    ("verified_secondarybert_frequencies.parquet", "verified_reusable", 1819032, 49083724),
    ("missing_secondarybert_structures.parquet", "not_located", 28404, 39779),
)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_archive(path):
    return subprocess.check_output(["zstd", "-dc", str(path) + ".zst"])


@contextmanager
def archive_stream(path, partial):
    command = ["zstd", "-dc", str(path)]
    with subprocess.Popen(command, stdout=subprocess.PIPE) as process:
        try:
            yield process.stdout
            if not partial and process.wait() != 0:
                raise subprocess.CalledProcessError(process.returncode, command)
        finally:
            if process.poll() is None:
                process.terminate()


def inventory():
    historical, missing = {}, {}
    for (filename, status, count, windows), keys in zip(INVENTORIES, (historical, missing)):
        for batch in pq.ParquetFile(AUDIT / filename).iter_batches():
            for row in batch.to_pylist():
                key = row["secondary_structure"]
                if not KEY.fullmatch(key) or key in keys or row["status"] != status:
                    raise ValueError(f"Invalid inventory record: {row}")
                if row["windows"] <= 0 or (row["historical_rows"] > 0) != (status == "verified_reusable"):
                    raise ValueError(f"Invalid inventory counts: {row}")
                keys[key] = row["windows"]
        if (len(keys), sum(keys.values())) != (count, windows):
            raise ValueError(f"Inventory totals changed: {filename}")
    if historical.keys() & missing.keys():
        raise ValueError("Overlapping historical and pending keys")
    return historical, missing


def sources():
    frame = pd.read_csv(AUDIT / "embedding_sources.tsv", sep="\t")
    canonical = frame[frame["path"].str.endswith("_SecondaryBERT_by_group")].sort_values("records")
    if len(canonical) != 11:
        raise ValueError("Expected eleven canonical sources")
    for entry in canonical.itertuples():
        directory = Path(entry.path)
        config = json.loads(read_archive(directory / "embedding_config.json"))
        expected = {
            "model_fingerprint": FINGERPRINT, "window_size": 25, "hidden_size": 768,
            "dtype": "float32", "pooling": "mean_25_biological_tokens",
            "batch_size": 4096, "token_mapping": generator.STATE_TO_ID,
            "total_rows": int(entry.records),
        }
        if any(config.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Historical configuration mismatch: {directory}")
        manifest = pd.read_csv(io.BytesIO(read_archive(directory / "chunks_manifest.csv")))
        if len(manifest) != int(entry.chunks):
            raise ValueError(f"Unexpected manifest size: {directory}")
        yield directory, manifest, config["total_rows"]


def archived_rows(directory, manifest, total, limit=None):
    """Yield exact keys in historical tensor order, validating metadata against the index."""
    ids = ["protein_group_id", "group_id"]
    start = 0
    with (
        archive_stream(directory / "metadata.csv.zst", limit is not None) as metadata_stream,
        archive_stream(directory / "index.csv.zst", limit is not None) as index_stream,
        pd.read_csv(metadata_stream, usecols=[*ids, "clean_ss"], iterator=True) as metadata,
        pd.read_csv(index_stream, usecols=[*ids, "row_idx_in_X_ss"], iterator=True) as index,
    ):
        for chunk in itertools.islice(manifest.itertuples(), limit):
            if chunk.start != start or chunk.end != start + chunk.n_rows:
                raise ValueError(f"Noncontiguous manifest: {directory}")
            path = directory / "chunks" / Path(chunk.x_file).name
            if not Path(str(path) + ".zst").is_file():
                raise FileNotFoundError(path)
            rows = metadata.get_chunk(chunk.n_rows)
            addresses = index.get_chunk(chunk.n_rows)
            if not (
                len(rows) == len(addresses) == chunk.n_rows
                and np.array_equal(rows[ids].to_numpy(), addresses[ids].to_numpy())
                and np.array_equal(addresses["row_idx_in_X_ss"], np.arange(start, chunk.end))
            ):
                raise ValueError(f"Metadata and index mismatch: {path}")
            yield path, rows["clean_ss"].tolist()
            start = chunk.end
        if limit is None and (
            start != total or next(iter(metadata), None) is not None
            or next(iter(index), None) is not None
        ):
            raise ValueError(f"Unexpected metadata length: {directory}")


def build_index(db):
    started = perf_counter()
    historical, missing = inventory()
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE build_shard (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL)")
        db.execute("""CREATE TABLE build_inventory (
            structure TEXT PRIMARY KEY, sha256 BLOB UNIQUE NOT NULL, length INTEGER NOT NULL,
            windows INTEGER NOT NULL, shard INTEGER, row_offset INTEGER
        ) WITHOUT ROWID""")
        insert = "INSERT INTO build_inventory VALUES (?, ?, 25, ?, ?, ?)"
        for directory, manifest, total in sources():
            for path, keys in archived_rows(directory, manifest, total):
                shard = db.execute("INSERT INTO build_shard(path) VALUES (?)", (str(path),)).lastrowid
                records = []
                for offset, key in enumerate(keys):
                    if key in missing:
                        raise ValueError(f"Pending key appeared in canonical source: {key}")
                    windows = historical.pop(key, None)
                    if windows is not None:
                        records.append((key, digest_key(key), windows, shard, offset))
                db.executemany(insert, records)
            print(f"{directory.name}: {len(historical):,} historical keys left", flush=True)
        if historical:
            raise ValueError(f"{len(historical)} audited historical keys could not be addressed")
        db.executemany(insert, ((key, digest_key(key), n, None, None) for key, n in missing.items()))
        db.execute("ALTER TABLE build_inventory RENAME TO inventory")
        db.execute("ALTER TABLE build_shard RENAME TO shard")
    print(f"Index built in {perf_counter() - started:.2f} s", flush=True)


def digest_key(key):
    return hashlib.sha256(key.encode("ascii")).digest()


def load_shard(path):
    data = read_archive(path)
    receipt = json.loads(Path(str(path) + ".archive.json").read_text())
    if len(data) != receipt["original_bytes"] or hashlib.sha256(data).hexdigest() != receipt["original_sha256"]:
        raise ValueError(f"Archive receipt mismatch: {path}")
    array = np.load(io.BytesIO(data), allow_pickle=False)
    if array.dtype != np.float32 or array.ndim != 2 or array.shape[1] != 768:
        raise ValueError(f"Invalid archive tensor: {path}")
    return array


def sample(keys, count, seed):
    """Select across composition and transition strata with a fixed seed."""
    rng = np.random.default_rng(seed)
    buckets = {}
    for key in sorted(set(keys)):
        dominant = max("CHE", key=key.count)
        transitions = sum(a != b for a, b in zip(key, key[1:]))
        bucket = (dominant, len(set(key)), transitions // 5)
        buckets.setdefault(bucket, []).append(key)
    groups = [iter(rng.permutation(buckets[bucket]).tolist()) for bucket in sorted(buckets)]
    return list(itertools.islice(
        (key for row in itertools.zip_longest(*groups) for key in row if key is not None), count,
    ))


def check_historical(model, device):
    stats = []
    for directory, manifest, total in sources():
        with closing(archived_rows(directory, manifest, total, limit=1)) as chunks:
            path, keys = next(chunks)
        chosen = sample(keys, 24, seed=37)
        offsets = {key: offset for offset, key in reversed(list(enumerate(keys)))}
        started = perf_counter()
        baseline = load_shard(path)[[offsets[key] for key in chosen]].astype(np.float64)
        archive_seconds = perf_counter() - started
        # Use the planned CUDA batch dimension while comparing only the selected rows.
        padded = chosen + keys[:BATCH - len(chosen)]
        actual = generator.embed_batch(padded, model, device)[:len(chosen)].astype(np.float64)
        diff = actual - baseline
        cosine = np.sum(actual * baseline, axis=1) / (
            np.linalg.norm(actual, axis=1) * np.linalg.norm(baseline, axis=1)
        )
        metrics = {
            "source": directory.name, "n": len(chosen), "keys": chosen,
            "archive_seconds": archive_seconds,
            "max_abs": float(np.max(np.abs(diff))),
            "max_row_rmse": float(np.max(np.sqrt(np.mean(diff ** 2, axis=1)))),
            "min_cosine": float(np.min(cosine)),
        }
        if not (metrics["max_abs"] <= 0.01 and metrics["max_row_rmse"] <= 0.002
                and metrics["min_cosine"] >= 0.99999):
            raise ValueError(f"Numerical compatibility failed: {metrics}")
        stats.append(metrics)
        print(f"{directory.name}: max abs={metrics['max_abs']:.6g}, "
              f"min cosine={metrics['min_cosine']:.9f}", flush=True)
    return stats


def verified_vector(key, blob, checksum):
    vector = np.frombuffer(blob, dtype="<f4")
    if vector.shape != (768,) or not np.isfinite(vector).all():
        raise ValueError(f"Invalid vector: {key}")
    if hashlib.sha256(key.encode("ascii") + blob).digest() != checksum:
        raise ValueError(f"Vector checksum mismatch: {key}")
    return vector


def read_embeddings(db, keys):
    """Retrieve vectors in input order. Group historical requests by compressed shard."""
    result = np.empty((len(keys), 768), dtype=np.float32)
    requests = {}
    for position, key in enumerate(keys):
        row = db.execute("""
            SELECT shard.path, inventory.row_offset, embedding.vector, embedding.checksum
            FROM inventory LEFT JOIN shard ON inventory.shard = shard.id
            LEFT JOIN embedding USING (structure) WHERE structure = ?
        """, (key,)).fetchone()
        if row is None or (row[0] is None and row[2] is None):
            raise KeyError(key)
        path, offset, blob, checksum = row
        if path is None:
            result[position] = verified_vector(key, blob, checksum)
        else:
            requests.setdefault(path, []).append((position, offset))
    for path, positions in requests.items():
        array = load_shard(Path(path))
        for position, offset in positions:
            result[position] = array[offset]
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite archived vectors")
    return result


def engine_config():
    model_dir = generator.MODEL_DIR
    weights = sha(model_dir / "model.safetensors")
    fingerprint = generator.model_fingerprint(model_dir)
    if (weights, fingerprint) != (WEIGHTS, FINGERPRINT):
        raise ValueError("Checkpoint differs from audited SecondaryBERT")
    from transformers import __version__ as transformers_version
    torch = generator.torch
    return {
        "weights": weights, "fingerprint": fingerprint,
        "tokenizer": sha(model_dir / "tokenizer.json"),
        "generator": sha(Path(generator.__file__)), "workflow": sha(Path(__file__)),
        "torch": torch.__version__, "transformers": transformers_version,
        "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
        "batch": BATCH,
    }


def persist_vectors(db, keys, vectors):
    records = []
    for key, vector in zip(keys, vectors, strict=True):
        blob = vector.astype("<f4", copy=False).tobytes()
        records.append((key, blob, hashlib.sha256(key.encode("ascii") + blob).digest()))
    with db:
        db.executemany("INSERT OR IGNORE INTO embedding VALUES (?, ?, ?)", records)
        for key, _, checksum in records:
            stored = db.execute("SELECT vector, checksum FROM embedding WHERE structure = ?", (key,)).fetchone()
            verified_vector(key, *stored)
            if stored[1] != checksum:
                raise ValueError(f"Existing embedding differs from reproducibility check: {key}")


def run(db, mode):
    torch = generator.torch
    if torch.cuda.device_count() != 1:
        raise RuntimeError("Expose exactly one GPU via CUDA_VISIBLE_DEVICES")
    config = engine_config()
    evidence_path = OUTPUT / "pilot.json"
    if mode == "generate":
        evidence = json.loads(evidence_path.read_text())
        if evidence["config"] != config or evidence["n"] != 1000 or len(evidence["compatibility"]) != 11:
            raise ValueError("A successful pilot with matching configuration is required")
    generator.validate_tokenizer(generator.MODEL_DIR)
    device = torch.device("cuda:0")
    started = perf_counter()
    model = generator.load_model(generator.MODEL_DIR, device)
    torch.cuda.synchronize()
    load_seconds = perf_counter() - started
    if mode == "pilot":
        compatibility = check_historical(model, device)
    keys = [row[0] for row in db.execute(
        "SELECT structure FROM inventory WHERE shard IS NULL ORDER BY structure"
    )]
    if len(keys) != 28404 or len(set(keys)) != 28404 or any(not KEY.fullmatch(key) for key in keys):
        raise ValueError("Pending inventory differs from the audited selection")
    db.execute("""CREATE TABLE IF NOT EXISTS embedding (
        structure TEXT PRIMARY KEY REFERENCES inventory(structure),
        vector BLOB NOT NULL, checksum BLOB NOT NULL
    ) WITHOUT ROWID""")
    existing = {}
    for key, blob, checksum in db.execute("SELECT * FROM embedding"):
        verified_vector(key, blob, checksum)
        existing[key] = checksum
    if existing.keys() - set(keys):
        raise ValueError("Stored vectors include keys outside the pending inventory")
    selected = sample(keys, 1000, seed=20261120) if mode == "pilot" else [
        key for key in keys if key not in existing
    ]
    torch.cuda.reset_peak_memory_stats()
    started = perf_counter()
    for start in range(0, len(selected), BATCH):
        batch = selected[start:start + BATCH]
        vectors = generator.embed_batch(batch, model, device)
        if mode == "pilot" and not np.array_equal(vectors, generator.embed_batch(batch, model, device)):
            raise ValueError("Repeated pilot inference differs")
        persist_vectors(db, batch, vectors)
    elapsed = perf_counter() - started
    if mode == "pilot":
        historical_key = db.execute(
            "SELECT structure FROM inventory WHERE shard IS NOT NULL LIMIT 1"
        ).fetchone()[0]
        retrieved = read_embeddings(db, [historical_key, *selected])[1:]
        evidence = {
            "config": config, "compatibility": compatibility, "seed": 20261120,
            "n": len(selected), "shape": list(retrieved.shape), "dtype": str(retrieved.dtype),
            "finite": bool(np.isfinite(retrieved).all()), "bitwise_repeat": True,
            "keys_sha256": hashlib.sha256("".join(selected).encode()).hexdigest(),
            "seconds_two_passes_including_writes": elapsed, "model_load_seconds": load_seconds,
            "peak_vram_bytes": torch.cuda.max_memory_allocated(),
            "composition": {state: sum(max("CHE", key=key.count) == state for key in selected) for state in "CHE"},
            "all_states": sum(len(set(key)) == 3 for key in selected),
            "transitions": sorted({sum(a != b for a, b in zip(key, key[1:])) for key in selected}),
        }
        temporary = evidence_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(evidence, indent=2) + "\n")
        temporary.replace(evidence_path)
        print(json.dumps({k: v for k, v in evidence.items() if k != "compatibility"}, indent=2))
    else:
        expected = set(keys)
        for key, blob, checksum in db.execute("SELECT * FROM embedding"):
            verified_vector(key, blob, checksum)
            expected.remove(key)
        if expected:
            raise ValueError(f"{len(expected)} exact keys lack an embedding")
        coverage = db.execute("""
            SELECT COUNT(*), SUM(windows) FROM inventory
            LEFT JOIN embedding USING (structure)
            WHERE shard IS NOT NULL OR embedding.structure IS NOT NULL
        """).fetchone()
        if coverage != (1847436, 49123503):
            raise ValueError(f"Unexpected final coverage: {coverage}")
        print(f"Validated {coverage[0]:,} structures and {coverage[1]:,} windows in {elapsed:.2f} s")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("index", "pilot", "generate"))
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(OUTPUT / "index.sqlite", timeout=120)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        if args.mode == "index":
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory'").fetchone():
                raise RuntimeError("Index already exists")
            build_index(db)
        else:
            run(db, args.mode)


if __name__ == "__main__":
    main()
