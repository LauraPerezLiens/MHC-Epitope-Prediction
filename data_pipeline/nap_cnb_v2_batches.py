"""Bounded data access for original v2 views, independent of model execution."""
import argparse
from collections import OrderedDict, defaultdict
from contextlib import ExitStack, closing
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import zipfile

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from data_pipeline import nap_cnb_v2 as cli
from neural_network.MLP import dataset as historical

MAX_ARCHIVE_BYTES = 320 * 1024**2
MAX_ROW_GROUP_ROWS = 250_000


def exact_keys(column):
    keys = pc.cast(column, pa.binary(25))
    if isinstance(keys, pa.ChunkedArray):
        keys = keys.combine_chunks()
    cli.require(keys.null_count == 0, "Null primary key")
    return np.frombuffer(keys.buffers()[1], dtype="S25", count=len(keys), offset=keys.offset * 25)


def locate(sorted_keys, keys):
    indices = np.searchsorted(sorted_keys, keys)
    cli.require(np.all(indices < len(sorted_keys)) and np.array_equal(sorted_keys[indices], keys),
                "Missing exact primary key")
    return indices


def cached(cache, key, limit, load):
    if key not in cache:
        if len(cache) == limit:
            cache.popitem(last=False)
        cache[key] = load(key)
    cache.move_to_end(key)
    return cache[key]


@dataclass(frozen=True)
class Batch:
    identifiers: tuple
    primary: tuple
    secondary: tuple
    split: int
    X: np.ndarray
    y: np.ndarray


class OriginalBatches:
    """One consumer per reader. Retain compact key indexes, never the feature matrices."""

    def __init__(self, root, label, primary_cache=2, secondary_cache=1):
        cli.require(label in ("original", "global"), "Unknown label contract")
        cli.require(1 <= primary_cache <= 16 and 1 <= secondary_cache <= 4, "Cache sizes out of bounds")
        self.root = Path(root)
        self.label = label
        component = cli.Component(self.root, cli.D1)
        self.contract = cli.original_training_data(component, label)
        self.primary_limit, self.secondary_limit = primary_cache, secondary_cache

    def __enter__(self):
        with ExitStack() as stack:
            spec = self.contract["embeddings"]
            manifest = json.loads((self.root / spec["ProtT5"]["manifest"]).read_text())
            self.shard_rows = manifest["shard_rows"]
            self.primary_dir = (self.root / spec["ProtT5"]["manifest"]).parent
            inventory_path = self.root / spec["ProtT5"]["inventory"]
            keys = exact_keys(pq.read_table(inventory_path, columns=["sequence"])["sequence"])
            order = np.argsort(keys)
            self.keys, self.ordinals = keys[order], order.astype(np.uint32)
            cli.require(len(self.keys) > 0 and not np.any(self.keys[1:] == self.keys[:-1]),
                        "Invalid primary inventory keys")
            assignments = pq.read_table(self.root / self.contract["splits"]["path"],
                                        columns=["effective_group_id", "split_id"])
            cli.require(np.array_equal(exact_keys(assignments["effective_group_id"]), self.keys),
                        "Split manifest primary keys disagree with inventory")
            split_codes = assignments["split_id"].combine_chunks()
            cli.require(split_codes.null_count == 0, "Null split assignment")
            self.splits = split_codes.to_numpy()
            cli.require(np.all(self.splits <= historical.TEST), "Invalid split code")
            self.view = stack.enter_context(pq.ParquetFile(self.root / self.contract["path"]))
            cli.require(self.view.metadata.num_rows == self.contract["rows"], "View row count differs")
            self.db_path = (self.root / spec["SecondaryBERT"]["index"]).resolve()
            for suffix in ("-wal", "-shm", "-journal"):
                cli.require(not Path(str(self.db_path) + suffix).exists(), "SecondaryBERT index is not finalized")
            with self.db_path.open("rb", buffering=0) as stream:
                header = stream.read(20)
            cli.require(header[:16] == b"SQLite format 3\x00" and header[18:20] == b"\x01\x01",
                        "SecondaryBERT index requires a finalized rollback-journal database")
            self.db = stack.enter_context(closing(sqlite3.connect(
                self.db_path.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0)))
            self.primary_cache, self.secondary_cache = OrderedDict(), OrderedDict()
            self.current = None
            self.stack = stack.pop_all()
        return self

    def __exit__(self, *exc):
        self.current = None
        self.primary_cache.clear()
        self.secondary_cache.clear()
        return self.stack.__exit__(*exc)

    def load_group(self, index):
        if self.current is None or self.current[0] != index:
            cli.require(0 <= index < self.view.num_row_groups, "Row group out of range")
            cli.require(self.view.metadata.row_group(index).num_rows <= MAX_ROW_GROUP_ROWS,
                        "View row group exceeds reader limit")
            columns = ["sequence", "secondary_structure", self.contract["label"]]
            if self.label == "original":
                columns.append("base_id")
            rows = self.view.read_row_group(index, columns=columns, use_threads=False)
            cli.require(all(rows[name].null_count == 0 for name in columns), "Null observation metadata")
            keys = exact_keys(rows["sequence"])
            indices = locate(self.keys, keys)
            labels = rows[self.contract["label"]].combine_chunks().to_numpy()
            cli.require(np.all((labels == 0) | (labels == 1)), "Nonbinary label")
            meta = {"y": labels, "split_id": self.splits[indices], "group_id": self.ordinals[indices].astype(np.int64)}
            self.current = index, rows, meta
        return self.current[1:]

    def primary_shard(self, shard):
        path = self.primary_dir / f"shard-{shard:04d}.npy"
        cli.read_npy_header(cli.Component(self.root, path), path)
        matrix = np.load(path, mmap_mode="r", allow_pickle=False)
        cli.require(matrix.shape[1] == historical.PRIMARY_DIM, f"Wrong primary dimension: {path}")
        return matrix

    def historical_archive(self, name):
        path = self.root / name
        receipt = cli.Component(self.root, path).load(Path(str(path) + ".archive.json"))
        length = cli.count(receipt["original_bytes"])
        cli.require(0 < length <= MAX_ARCHIVE_BYTES, f"Historical archive exceeds decode limit: {path}")
        with subprocess.Popen(["zstd", "-dc", str(path) + ".zst"], stdout=subprocess.PIPE) as process:
            try:
                raw = process.stdout.read(length + 1)
                cli.require(len(raw) == length and process.wait() == 0, f"Invalid archive length: {path}")
            finally:
                if process.poll() is None:
                    process.kill()
        cli.require(hashlib.sha256(raw).hexdigest() == receipt["original_sha256"], f"Archive checksum mismatch: {path}")
        matrix = np.load(io.BytesIO(raw), allow_pickle=False)
        cli.require(matrix.ndim == 2 and matrix.shape[1] == historical.SECONDARY_DIM and matrix.dtype == "<f4",
                    f"Invalid historical matrix: {path}")
        return matrix

    def secondary_vectors(self, keys, target):
        placements = defaultdict(list)
        archives = defaultdict(list)
        for position, key in enumerate(keys):
            placements[key].append(position)
        unique = tuple(placements)
        for start in range(0, len(unique), 500):
            chunk = unique[start:start + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows = self.db.execute(f"""
                SELECT i.structure,s.path,i.row_offset,e.vector,e.checksum FROM inventory i
                LEFT JOIN shard s ON i.shard=s.id LEFT JOIN embedding e ON i.structure=e.structure
                WHERE i.structure IN ({placeholders})
            """, chunk).fetchall()
            cli.require(len(rows) == len(chunk), "Missing SecondaryBERT key")
            for key, path, offset, value, checksum in rows:
                if path is not None:
                    archives[path].append((placements[key], offset))
                else:
                    cli.require(value is not None and len(value) == historical.SECONDARY_DIM * 4 and
                                hashlib.sha256(key.encode("ascii") + value).digest() == checksum,
                                f"Invalid new SecondaryBERT vector: {key}")
                    target[placements[key]] = np.frombuffer(value, dtype="<f4")
        for path, requests in archives.items():
            matrix = cached(self.secondary_cache, path, self.secondary_limit, self.historical_archive)
            for positions, offset in requests:
                cli.require(type(offset) is int and 0 <= offset < len(matrix), "Invalid historical row offset")
                target[positions] = matrix[offset]

    def features(self, index, positions):
        rows, meta = self.load_group(index)
        positions = np.asarray(positions)
        cli.require(positions.ndim == 1 and positions.dtype.kind in "iu" and
                    np.all((positions >= 0) & (positions < len(rows))), "Invalid requested row positions")
        ordinals = meta["group_id"][positions]
        shards, offsets = np.divmod(ordinals, self.shard_rows)
        result = np.empty((len(positions), historical.PRIMARY_DIM + historical.SECONDARY_DIM), dtype=np.float32)
        for shard in np.unique(shards):
            local = np.flatnonzero(shards == shard)
            matrix = cached(self.primary_cache, int(shard), self.primary_limit, self.primary_shard)
            cli.require(np.all(offsets[local] < len(matrix)), "Invalid ProtT5 row offset")
            result[local, :historical.PRIMARY_DIM] = matrix[offsets[local]]
        keys = pc.take(rows["secondary_structure"], positions).to_pylist()
        self.secondary_vectors(keys, result[:, historical.PRIMARY_DIM:])
        cli.require(np.isfinite(result).all(), "Nonfinite features in requested rows")
        return result

    def batches(self, split, batch_size, shuffle_seed=None):
        cli.require(split in (historical.TRAIN, historical.VALIDATION, historical.TEST), "Unknown split")
        cli.require(batch_size > 0, "Batch size must be positive")
        groups = np.arange(self.view.num_row_groups)
        rng = np.random.default_rng(shuffle_seed) if shuffle_seed is not None else None
        if rng is not None:
            rng.shuffle(groups)
        for index in groups:
            rows, meta = self.load_group(int(index))
            positions = np.flatnonzero(meta["split_id"] == split)
            if rng is not None:
                rng.shuffle(positions)
            for offset in range(0, len(positions), batch_size):
                block = positions[offset:offset + batch_size]
                primary = tuple(pc.take(rows["sequence"], block).to_pylist())
                secondary = tuple(pc.take(rows["secondary_structure"], block).to_pylist())
                ids = (tuple(pc.take(rows["base_id"], block).to_pylist()) if self.label == "original"
                       else tuple(zip(primary, secondary)))
                yield Batch(ids, primary, secondary, split, self.features(int(index), block),
                            meta["y"][block].astype(np.float32))


class LegacyRowAdapter:
    """Provide the two row access functions used by the historical engine."""

    def __init__(self, reader):
        self.reader = reader

    def load_chunk_metadata(self, dataset, chunk_id, mmap=True):
        return self.reader.load_group(chunk_id)[1]

    def load_rows(self, dataset, chunk_id, row_indices, group_ids, feature_mode, **kwargs):
        _, metadata = self.reader.load_group(chunk_id)
        cli.require(feature_mode == "primary_secondary", "Unexpected historical feature mode")
        cli.require(np.array_equal(metadata["group_id"][row_indices], group_ids), "Historical row/group mismatch")
        return self.reader.features(chunk_id, row_indices)


class BalancedTrainingSource(LegacyRowAdapter):
    """Explicit input contract for the shared engine. This class never starts a run."""

    def __init__(self, reader, scaler_path, model, profile, seed):
        super().__init__(reader)
        expected_profile = {"logistic": "lr_balanced", "mlp": "mlp_historical"}
        cli.require(model in expected_profile and profile == expected_profile[model],
                    "Unsupported balanced v2 profile")
        expected = cli.scaler_contract(reader.root, reader.label, reader.contract)
        scaler_path = Path(scaler_path)
        self.standardizer = load_train_scaler(scaler_path, expected)
        self._contract = {
            "model": model, "profile": profile, "sampling": "exact_50_50", "seed": seed,
            "view": reader.contract["path"], "label": reader.contract["label"],
            "scaler": str(scaler_path.resolve()), "scaler_sha256": hashlib.sha256(scaler_path.read_bytes()).hexdigest(),
            "scaler_provenance": cli.check_scaler_contract(scaler_path, expected),
            "checkpoint_selection": "VALIDATION", "final_evaluation": "TEST",
        }

    @property
    def chunk_count(self):
        return self.reader.view.num_row_groups

    def training_contract(self):
        return dict(self._contract)



def fit_train_scaler(reader, batch_size):
    primary = historical._RunningMoments(historical.PRIMARY_DIM)
    secondary = historical._RunningMoments(historical.SECONDARY_DIM)
    for batch in reader.batches(historical.TRAIN, batch_size):
        cli.require(batch.split == historical.TRAIN and np.isfinite(batch.X).all(), "Invalid TRAIN batch")
        primary.update(batch.X[:, :historical.PRIMARY_DIM])
        secondary.update(batch.X[:, historical.PRIMARY_DIM:])
    mean_p, scale_p = primary.finalize()
    mean_s, scale_s = secondary.finalize()
    cli.require(all(np.isfinite(values).all() for values in (mean_p, scale_p, mean_s, scale_s)), "Nonfinite scaler")
    return historical.ModalityStandardizer(mean_p, scale_p, mean_s, scale_s,
                                            np.array([reader.contract["path"]]),
                                            np.arange(reader.view.num_row_groups)), primary.count


def load_train_scaler(path, expected):
    cli.check_scaler_contract(path, expected)
    with np.load(path, allow_pickle=False) as payload:
        values = {}
        for name, width in (("primary", historical.PRIMARY_DIM), ("secondary", historical.SECONDARY_DIM)):
            for field in ("mean", "scale"):
                key = f"{name}_{field}"
                array = payload[key]
                cli.require(array.shape == (width,) and array.dtype == np.float32 and np.isfinite(array).all(),
                            f"Invalid scaler statistics: {key}")
                if field == "scale":
                    cli.require(np.all(array > 0), f"Nonpositive scale: {key}")
                values[key] = array
        return historical.ModalityStandardizer(
            **values, sampled_dataset_names=payload["sampled_dataset_names"],
            sampled_chunk_ids=payload["sampled_chunk_ids"])


def publish_train_scaler(output, scaler, contract, batch_size):
    output = output.resolve()
    metadata = {**contract, "output": str(output), "batch_size": batch_size}
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        staged = Path(tmp) / "scaler.npz"
        scaler.save(staged)
        with zipfile.ZipFile(staged, "a") as archive:
            archive.writestr("provenance.json", json.dumps(metadata, sort_keys=True))
        # Validate the staged contents. The output path is checked again by consumers.
        cli.require(cli.scaler_metadata(staged) == metadata, "Failed to read staged scaler provenance")
        os.link(staged, output)  # Atomic publication without replacing an existing file.
    return metadata



def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare a TRAIN-only scaler, without running a model")
    parser.add_argument("command", choices=("fit-scaler",))
    parser.add_argument("--root", type=Path, default=cli.ROOT)
    parser.add_argument("--label", choices=("original", "global"), required=True)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-full-train", action="store_true",
                        help="explicitly allow streaming all rows in the selected TRAIN view")
    args = parser.parse_args(argv)
    if not args.confirm_full_train:
        parser.error("--confirm-full-train is required; this operation can be I/O intensive")
    root = args.root.resolve()
    output = (root / args.output).resolve()
    if output.exists() or output.suffix != ".npz" or not output.is_relative_to(root / "results/nap_cnb_v2_training"):
        parser.error("--output must be a new .npz path under results/nap_cnb_v2_training")
    if not output.parent.is_dir():
        parser.error("Create the isolated experiment directory before preparing its scaler")
    with OriginalBatches(root, args.label) as reader:
        provenance = cli.scaler_contract(root, args.label, reader.contract)
        scaler, rows = fit_train_scaler(reader, args.batch_size)
        cli.require(rows == provenance["train_rows"], "Scaler TRAIN coverage disagrees")
        cli.require(provenance == cli.scaler_contract(root, args.label, reader.contract),
                    "Scaler input manifests changed during fitting")
    recorded = publish_train_scaler(output, scaler, provenance, args.batch_size)
    print(json.dumps({"scaler": str(output), **recorded}, indent=2))


if __name__ == "__main__":
    main()
