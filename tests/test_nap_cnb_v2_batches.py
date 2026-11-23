"""Tiny CPU fixtures for exact-key access, scaling, and historical engine parity."""
from argparse import Namespace
from contextlib import closing
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    from data_pipeline import nap_cnb_v2_batches as batches
except ImportError:
    batches = None


@unittest.skipIf(batches is None, "NumPy/PyArrow unavailable")
class BatchTest(unittest.TestCase):
    def test_standalone_secondary_reader_checks_archive_offsets(self):
        if shutil.which("zstd") is None:
            self.skipTest("Zstandard is unavailable")
        arrays = {"full.npy": np.arange(2 * 768, dtype="<f4").reshape(2, 768),
                  "empty.npy": np.empty((0, 768), dtype="<f4")}
        for name, matrix in arrays.items():
            path = self.root / name
            np.save(path, matrix)
            data = path.read_bytes()
            Path(str(path) + ".zst").write_bytes(subprocess.check_output(["zstd", "-q", "-c", str(path)]))
            Path(str(path) + ".archive.json").write_text(json.dumps(
                dict(original_bytes=len(data), original_sha256=hashlib.sha256(data).hexdigest())))
        with closing(sqlite3.connect(":memory:")) as db:
            db.executescript("""
                CREATE TABLE shard (id INTEGER PRIMARY KEY, path TEXT);
                CREATE TABLE inventory (structure TEXT PRIMARY KEY, shard INTEGER, row_offset INTEGER);
                CREATE TABLE embedding (structure TEXT PRIMARY KEY, vector BLOB, checksum BLOB);
                INSERT INTO shard VALUES (1, 'full.npy'), (2, 'empty.npy'), (3, 'missing.npy');
                INSERT INTO inventory VALUES ('valid', 1, 1), ('empty', 2, 0), ('missing', 3, 0),
                    ('dangling', 4, 0);
            """)
            read = batches.read_secondary_embeddings
            np.testing.assert_array_equal(read(db, ["valid", "valid"], root=self.root),
                                          arrays["full.npy"][[1, 1]])
            for offset in (-1, -3, 2, 5):
                with self.subTest(offset=offset):
                    db.execute("UPDATE inventory SET row_offset=? WHERE structure='valid'", (offset,))
                    with self.assertRaisesRegex(ValueError, "Invalid historical row offset"):
                        read(db, ["valid"], root=self.root)
            with self.assertRaisesRegex(ValueError, "Invalid historical row offset"):
                read(db, ["empty"], root=self.root)
            with self.assertRaises(FileNotFoundError):
                read(db, ["missing"], root=self.root)
            with self.assertRaisesRegex(ValueError, "Missing SecondaryBERT shard"):
                read(db, ["dangling"], root=self.root)

    def test_cache_capacity_requires_integer(self):
        for kwargs in ({"secondary_cache": 1.5}, {"primary_cache": 2.5},
                       {"secondary_cache": True}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "Cache sizes"):
                self.reader("global", **kwargs)

    def test_secondary_cache_eviction_and_archive_corruption(self):
        name = "sample.npy"
        archive = self.root / f"{name}.zst"
        receipt = self.root / f"{name}.archive.json"
        compressed, metadata = archive.read_bytes(), receipt.read_bytes()

        def copy_archive(other_name, value):
            path = self.root / other_name
            np.save(path, np.full((1, 768), value, dtype="<f4"))
            raw = path.read_bytes()
            path.with_suffix(".npy.zst").write_bytes(subprocess.check_output(["zstd", "-q", "-c", str(path)]))
            path.with_suffix(".npy.archive.json").write_text(json.dumps(
                {"original_bytes": len(raw), "original_sha256": hashlib.sha256(raw).hexdigest()}))

        copy_archive("other.npy", 42)
        with closing(sqlite3.connect(self.root / "secondary.sqlite")) as db, db:
            db.execute("INSERT INTO shard VALUES(2, 'other.npy')")
            db.execute("UPDATE inventory SET shard=2,row_offset=0 WHERE structure=?", (self.ss[1],))

        with self.reader("global") as reader, patch.object(
            reader, "historical_archive", wraps=reader.historical_archive
        ) as load:
            np.testing.assert_array_equal(reader.features(0, [0])[0, -768:], 10)
            archive.write_bytes(compressed[:-1])
            np.testing.assert_array_equal(reader.features(0, [0])[0, -768:], 10)
            self.assertEqual(load.call_count, 1)
            np.testing.assert_array_equal(reader.features(0, [1])[0, -768:], 42)
            self.assertEqual(list(reader.secondary_cache), ["other.npy"])
            for data, message in ((compressed[:-1], "length"), (b"?" * len(compressed), "length"),
                                  ((self.root / "other.npy.zst").read_bytes(), "checksum")):
                archive.write_bytes(data)
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    reader.features(0, [0])
                self.assertNotIn(name, reader.secondary_cache)
            archive.write_bytes(compressed)
            declared = json.loads(metadata)
            for length in (declared["original_bytes"] + 1, declared["original_bytes"] - 1):
                receipt.write_text(json.dumps({**declared, "original_bytes": length}))
                with self.assertRaisesRegex(ValueError, "length"):
                    reader.features(0, [0])
            receipt.write_text(json.dumps({**declared, "original_bytes": True}))
            with self.assertRaisesRegex(ValueError, "Invalid count"):
                reader.features(0, [0])
            receipt.write_bytes(metadata)
            np.testing.assert_array_equal(reader.features(0, [0])[0, -768:], 10)
            self.assertEqual(list(reader.secondary_cache), [name])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.keys = ["A" * 25, "C" * 25, "D" * 25, "E" * 25, "F" * 25, "G" * 25]
        self.ss = [tone * 24 + "C" for tone in "CHE"] + [tone * 24 + "H" for tone in "CHE"]
        self.split = [0, 0, 1, 1, 2, 2]
        self.base_y = [0, 1, 0, 1, 1, 0]
        self.global_y = [1, 0, 1, 0, 0, 1]
        order = [1, 4, 2, 0, 5, 3]
        pq.write_table(pa.table({"sequence": [self.keys[i] for i in order]}), self.root / "inventory.parquet")
        pq.write_table(pa.table({"effective_group_id": self.keys,
                                 "split_id": pa.array(self.split, type=pa.uint8())}), self.root / "assign.parquet")
        p = np.stack([np.full(1024, value, dtype="<f4") for value in (2, 4, 50, 70, 110, 130)])
        p[:, 10] = 3  # Constant, including across both TRAIN rows.
        s = np.stack([np.full(768, value, dtype="<f4") for value in (10, 20, 250, 300, 400, 500)])
        self.expected = np.concatenate((p, s), axis=1)
        np.save(self.root / "shard-0000.npy", p[order[:3]])
        np.save(self.root / "shard-0001.npy", p[order[3:]])
        (self.root / "manifest.json").write_text(json.dumps({"shard_rows": 3}))
        legacy = self.root / "sample.npy"
        if shutil.which("zstd") is None:
            self.skipTest("zstd unavailable")
        np.save(legacy, s[:1])
        raw = legacy.read_bytes()
        (self.root / "sample.npy.zst").write_bytes(subprocess.check_output(["zstd", "-c", str(legacy)]))
        (self.root / "sample.npy.archive.json").write_text(json.dumps({
            "original_bytes": len(raw), "original_sha256": hashlib.sha256(raw).hexdigest()}))
        with closing(sqlite3.connect(self.root / "secondary.sqlite")) as db, db:
            db.executescript("""
            CREATE TABLE shard(id INTEGER PRIMARY KEY, path TEXT);
            CREATE TABLE inventory(structure TEXT PRIMARY KEY, shard INTEGER, row_offset INTEGER);
            CREATE TABLE embedding(structure TEXT PRIMARY KEY,vector BLOB,checksum BLOB);
            INSERT INTO shard VALUES(1,'sample.npy');
            """)
            for i, key in enumerate(self.ss):
                db.execute("INSERT INTO inventory VALUES(?,?,?)", (key, 1 if i == 0 else None, 0 if i == 0 else None))
                if i:
                    raw = s[i].tobytes()
                    db.execute("INSERT INTO embedding VALUES(?,?,?)",
                               (key, raw, hashlib.sha256(key.encode() + raw).digest()))
        for label, values in (("original", self.base_y), ("global", self.global_y)):
            data = {"sequence": self.keys, "secondary_structure": self.ss,
                    f"label_{label}": pa.array(values, type=pa.int8())}
            if label == "original":
                data["base_id"] = [f"window-{i}" for i in range(6)]
            pq.write_table(pa.table(data), self.root / f"{label}.parquet")

    def test_reader_rejects_signed_negative_and_floating_split_codes(self):
        path = self.root / "assign.parquet"
        for values, dtype in (([-1, *self.split[1:]], pa.int8()), (self.split, pa.float64())):
            with self.subTest(dtype=dtype):
                pq.write_table(pa.table({
                    "effective_group_id": self.keys, "split_id": pa.array(values, type=dtype),
                }), path)
                with self.assertRaisesRegex(ValueError, "uint8"):
                    with self.reader("global"):
                        pass

    def reader(self, label, **options):
        contract = {"rows": 6, "path": f"{label}.parquet", "label": f"label_{label}",
                    "splits": {"path": "assign.parquet"},
                    "embeddings": {"ProtT5": {"manifest": "manifest.json", "inventory": "inventory.parquet"},
                                   "SecondaryBERT": {"index": "secondary.sqlite"}}}
        with patch.object(batches.cli, "original_training_data", return_value=contract):
            return batches.OriginalBatches(self.root, label, **options)

    def test_labels_keys_splits_order_and_partial_batch(self):
        for label, labels in (("original", self.base_y), ("global", self.global_y)):
            with self.subTest(label=label), self.reader(label) as reader:
                for split in range(3):
                    (batch,) = list(reader.batches(split, batch_size=3))
                    rows = slice(2 * split, 2 * split + 2)
                    self.assertEqual(batch.primary, tuple(self.keys[rows]))
                    np.testing.assert_array_equal(batch.X, self.expected[rows])
                    np.testing.assert_array_equal(batch.y, labels[rows])
                    self.assertEqual(batch.X.shape, (2, 1792))
                    self.assertEqual(batch.X.dtype, np.float32)
                    self.assertEqual(batch.y.dtype, np.float32)
                    self.assertTrue(np.isfinite(batch.X).all())
                first = [b.identifiers for b in reader.batches(0, 1, shuffle_seed=42)]
                self.assertEqual(first, [b.identifiers for b in reader.batches(0, 1, shuffle_seed=42)])
                np.testing.assert_array_equal(reader.features(0, np.array([5, 0, 5])), self.expected[[5, 0, 5]])

    def test_reader_rejects_non_int8_label_columns(self):
        path = self.root / "global.parquet"
        table = pq.read_table(path)
        for dtype, values in ((pa.bool_(), [bool(v) for v in self.global_y]),
                              (pa.float64(), self.global_y), (pa.int64(), self.global_y)):
            with self.subTest(dtype=dtype):
                pq.write_table(table.set_column(2, "label_global", pa.array(values, type=dtype)), path)
                with self.reader("global") as reader:
                    with self.assertRaisesRegex(ValueError, "int8"):
                        reader.load_group(0)

    def test_view_mutations_and_retained_batches(self):
        path = self.root / "original.parquet"
        table = pq.read_table(path)
        changed = table.set_column(2, "label_original", pa.array([1, *self.base_y[1:]], type=pa.int8()))
        changed = changed.set_column(3, "base_id", pa.array(["edited", *table["base_id"].to_pylist()[1:]]))
        pq.write_table(changed.take([1, 0, 2, 3, 4, 0]), path, row_group_size=2)
        with self.reader("original") as reader:
            iterator = reader.batches(0, 1)
            first = next(iterator)
            remaining = list(iterator)
            self.assertEqual([b.identifiers for b in [first, *remaining]],
                             [("window-1",), ("edited",), ("edited",)])
            np.testing.assert_array_equal(first.X, self.expected[[1]])
            np.testing.assert_array_equal(remaining[-1].X, self.expected[[0]])
            np.testing.assert_array_equal(remaining[-1].y, [1])
            self.assertFalse(np.shares_memory(first.X, remaining[-1].X))
            self.assertFalse(np.shares_memory(first.y, remaining[-1].y))
        pq.write_table(table.slice(0, 5), path)
        with self.assertRaisesRegex(ValueError, "row count"):
            with self.reader("original"):
                pass

    def test_primary_cache_snapshot_and_mutations(self):
        path = self.root / "shard-0000.npy"
        original = np.load(path)
        info = path.stat()
        with self.reader("global") as reader:
            np.testing.assert_array_equal(reader.features(0, [1]), self.expected[[1]])
            mapped = np.load(path, mmap_mode="r+")
            mapped[0, 0] = 999
            mapped.flush()
            del mapped
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
            self.assertEqual(reader.features(0, [1])[0, 0], 999)
            replacement = path.with_name("replacement.npy")
            np.save(replacement, original[[1, 0, 2]])
            os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
            replacement.replace(path)
            self.assertEqual(path.stat().st_size, info.st_size)
            self.assertNotEqual(path.stat().st_ino, info.st_ino)
            self.assertEqual(reader.features(0, [1])[0, 0], 999)
        with self.reader("global") as reader:
            self.assertEqual(reader.features(0, [1])[0, 0], original[1, 0])
            for positions in ([-1], [0.5], [True], [6]):
                with self.subTest(positions=positions), self.assertRaisesRegex(ValueError, "positions"):
                    reader.features(0, positions)
        for value in (np.nan, np.inf):
            matrix = original.copy()
            matrix[0, 0] = value
            np.save(path, matrix)
            with self.reader("global") as reader:
                with self.assertRaisesRegex(ValueError, "Nonfinite"):
                    reader.features(0, [1])
        for matrix, message, position in ((original[:, :-1], "dimension", 1),
                                           (original[:1], "offset", 4)):
            np.save(path, matrix)
            with self.reader("global") as reader:
                with self.assertRaisesRegex(ValueError, message):
                    reader.features(0, [position])
        path.write_bytes(path.read_bytes()[:-1])
        with self.reader("global") as reader:
            with self.assertRaisesRegex(ValueError, "size"):
                reader.features(0, [1])

    def test_fit_only_train_and_transform_held_out(self):
        with self.reader("global") as reader:
            scaler, count = batches.fit_train_scaler(reader, batch_size=1)
            self.assertEqual(count, 2)
            mean = self.expected[:2].mean(axis=0)
            scale = self.expected[:2].std(axis=0)
            scale[scale == 0] = 1
            for split in (1, 2):
                (held_out,) = list(reader.batches(split, batch_size=4))
                indices = slice(2 * split, 2 * split + 2)
                np.testing.assert_allclose(scaler.transform(held_out.X), (self.expected[indices] - mean) / scale)

    def test_scaler_persistence_and_train_provenance_without_model(self):
        with self.reader("global") as reader:
            scaler, rows = batches.fit_train_scaler(reader, batch_size=1)
            repeated, _ = batches.fit_train_scaler(reader, batch_size=1)
            for key in ("primary_mean", "primary_scale", "secondary_mean", "secondary_scale"):
                np.testing.assert_array_equal(getattr(scaler, key), getattr(repeated, key))
            path = self.root / "fixture-scaler.npz"
            expected = {"schema_version": 1, "label": "label_global", "view": "global.parquet",
                        "split": "TRAIN", "train_rows": rows}
            recorded = batches.publish_train_scaler(path, scaler, expected, batch_size=1)
            self.assertEqual(recorded["output"], str(path))
            self.assertEqual(recorded["train_rows"], 2)
            restored = batches.load_train_scaler(path, expected)
            for split in (1, 2):
                (batch,) = list(reader.batches(split, batch_size=4))
                np.testing.assert_array_equal(restored.transform(batch.X.copy()), scaler.transform(batch.X))
            with self.assertRaisesRegex(ValueError, "provenance"):
                batches.load_train_scaler(path, {**expected, "label": "label_original"})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                batches.publish_train_scaler(path, scaler, expected, batch_size=1)
            self.assertEqual(path.read_bytes(), before)

    def release_fixture(self):
        from tests.test_nap_cnb_v2_validation import ValidationTest

        release = ValidationTest()
        release.setUp()
        self.addCleanup(release.doCleanups)
        release.catalogs()
        release.split_report()
        release.d1_manifest()
        cli = batches.cli
        for name in ("sample.npy.zst", "sample.npy.archive.json"):
            shutil.copyfile(self.root / name, release.root / name)
        shutil.copyfile(self.root / "secondary.sqlite", release.root / cli.SECONDARY / "index.sqlite")
        primary = release.d1["embeddings"]["ProtT5"]
        for name in ("shard-0000.npy", "shard-0001.npy"):
            shutil.copyfile(self.root / name, release.root / cli.PRIMARY / name)
        shutil.copyfile(self.root / "inventory.parquet", release.root / primary["inventory"])
        manifest = json.loads((release.root / primary["manifest"]).read_text())
        manifest.update(shard_rows=3, inventory_sha256=release.sha(primary["inventory"]))
        release.write(primary["manifest"], manifest)
        shutil.copyfile(self.root / "assign.parquet", release.root / cli.ASSIGNMENTS)
        for label, filename, extras in (
            ("original", "base_dataset.parquet", (2, 5)),
            ("global", "global_dataset.parquet", (3, 4)),
        ):
            data = pq.read_table(self.root / f"{label}.parquet").to_pydict()
            for index in extras:
                data["sequence"].append(self.keys[index])
                data["secondary_structure"].append(self.ss[0])
                data[f"label_{label}"].append(0)
                if label == "original":
                    data["base_id"].append(f"extra-{index}")
            data[f"label_{label}"] = pa.array(data[f"label_{label}"], type=pa.int8())
            pq.write_table(pa.table(data), release.root / cli.VIEWS / filename)
            release.metrics["files_bytes"][filename] = (release.root / cli.VIEWS / filename).stat().st_size
        release.metrics["families"]["fixture"].update(base=8, removed=4, base_positive=3)
        release.metrics.update(global_sequences=6, global_representations=8, global_positive_representations=3)
        release.write(cli.METRICS, release.metrics)
        release.splits.update(
            effective_groups=6, assignment_sha256=release.sha(cli.ASSIGNMENTS),
            assignment_bytes=(release.root / cli.ASSIGNMENTS).stat().st_size,
            base=release.frame((2, 3, 3), (1, 1, 1)),
            global_=release.frame((2, 3, 3), (1, 1, 1)),
        )
        release.splits["global"] = release.splits.pop("global_")
        for name in ("base_dataset", "global_dataset"):
            release.splits["catalog_sha256"][name] = release.sha(cli.VIEWS / f"{name}.parquet")
        release.write(cli.SPLITS, release.splits)
        release.d1.update(observations=8, by_split=release.splits["global"])
        release.d1["validation"].update(unique_representations=8, unique_primary_keys=6, confirmed_prott5_shards=2)
        release.d1["inputs_sha256"] = {file: release.sha(file) for file in release.d1["inputs_sha256"]}
        release.write(cli.D1, release.d1)
        return release

    def test_v2_rejects_checkpoint_options_before_reading_source_or_state(self):
        try:
            import torch
        except ImportError:
            self.skipTest("PyTorch unavailable")
        directory = str(Path(__file__).resolve().parents[1] / "neural_network/MLP")
        sys.path.insert(0, directory)
        try:
            engine = importlib.import_module("neural_network.MLP.mlp_layernorm_shuffled_ladder100_dualeval")
        finally:
            sys.path.remove(directory)

        output = self.root / "existing-output"
        output.mkdir()
        checkpoint = output / "checkpoint.pt"
        with patch.object(torch, "load", side_effect=AssertionError("checkpoint opened")):
            for content in (None, b"corrupt", {}):
                if isinstance(content, bytes):
                    checkpoint.write_bytes(content)
                elif content is not None:
                    torch.save(content, checkpoint)
                for option in ("--resume", "--init-checkpoint"):
                    for model, size in (("logistic", "2"), ("mlp", "4")):
                        with self.subTest(content=content, option=option, model=model, batch_size=size):
                            args = engine.parse_args([option, str(checkpoint), "--model-type", model,
                                                      "--batch-size", size, "--output-dir", str(output)])
                            with self.assertRaisesRegex(ValueError, "v2 expects a new run"):
                                engine.main(args, data_source=object())

            class Source:
                def training_contract(self):
                    return {"sampling": "exact_50_50", "model": "logistic", "seed": 42}

            args = engine.parse_args(["--model-type", "logistic", "--output-dir", str(output)])
            previous = checkpoint.read_bytes()
            cpu = (False, 0, 0, 1, torch.device("cpu"))
            with patch.object(engine, "distributed_setup", return_value=cpu):
                with self.assertRaises(FileExistsError):
                    engine.main(args, data_source=Source())
            self.assertEqual(checkpoint.read_bytes(), previous)

    def test_balanced_v2_engine_end_to_end_without_patching_readers(self):
        try:
            import torch
        except ImportError:
            self.skipTest("PyTorch unavailable")
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "" and torch.cuda.is_available():
            self.skipTest("Run this CPU fixture with CUDA_VISIBLE_DEVICES empty")
        from contextlib import redirect_stdout
        from io import StringIO

        release = self.release_fixture()
        directory = str(Path(__file__).resolve().parents[1] / "neural_network/MLP")
        sys.path.insert(0, directory)
        try:
            engine = importlib.import_module("neural_network.MLP.mlp_layernorm_shuffled_ladder100_dualeval")
        finally:
            sys.path.remove(directory)

        class ObservedSource(batches.BalancedTrainingSource):
            feature_splits = None

            def load_rows(self, dataset, chunk_id, row_indices, group_ids, feature_mode, **kwargs):
                _, metadata = self.reader.load_group(chunk_id)
                self.feature_splits.extend(metadata["split_id"][row_indices].tolist())
                return super().load_rows(dataset, chunk_id, row_indices, group_ids, feature_mode, **kwargs)

        for label in ("original", "global"):
            with batches.OriginalBatches(release.root, label) as reader:
                scaler, rows = batches.fit_train_scaler(reader, batch_size=2)
                self.assertEqual(rows, 2)
                path = release.root / f"{label}.npz"
                contract = batches.cli.scaler_contract(release.root, label, reader.contract)
                batches.publish_train_scaler(path, scaler, contract, 2)
                for model, profile, tag in (("logistic", "lr_balanced", "lr"), ("mlp", "mlp_historical", "mlp")):
                    with self.subTest(label=label, model=model):
                        source = ObservedSource(reader, path, model, profile, 42)
                        source.feature_splits = []
                        output = release.root / f"run-{label}-{tag}"
                        args = engine.parse_args(["--epochs", "2", "--batch-size", "2", "--eval-batch-size", "2",
                                                  "--model-type", model, "--output-dir", str(output)])
                        with redirect_stdout(StringIO()):
                            engine.main(args, data_source=source)
                        history = output / f"history_{tag}_primary_secondary.jsonl"
                        records = [json.loads(line) for line in history.read_text().splitlines()]
                        self.assertEqual([record["type"] for record in records], ["epoch_end", "epoch_end", "final_test"])
                        for record in records[:-1]:
                            self.assertNotIn("test", record)
                            self.assertEqual(record["train"]["n"], 2)
                            self.assertEqual(record["validation"]["n"], 3)
                            self.assertEqual(record["validation"]["tp"] + record["validation"]["fn"], 1)
                        final = records[-1]
                        self.assertEqual(final["test"]["n"], 3)
                        self.assertEqual(final["test"]["tp"] + final["test"]["fn"], 1)
                        self.assertEqual(source.feature_splits, [0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 2, 2, 2])
                        best = torch.load(output / final["checkpoint"], map_location="cpu", weights_only=False)
                        self.assertEqual((best["selection_split"], best["selection_metric"]),
                                         ("VALIDATION", "validation_loss"))
                        self.assertEqual(best["v2_contract"]["profile"], profile)
                        self.assertEqual(best["v2_contract"]["sampling"], "exact_50_50")
                        self.assertEqual(best["best_val_loss"], min(r["validation"]["loss"] for r in records[:-1]))
                        self.assertEqual(best["best_epoch"], final["best_epoch"])
                        self.assertFalse((output / "eval_stage").exists())
                        steps = [state["step"].item() for state in best["optimizer_state_dict"]["state"].values()]
                        self.assertTrue(steps and all(step > 0 for step in steps))

    def test_historical_lr_and_mlp_consume_adapter_rows_on_cpu(self):
        try:
            import torch
        except ImportError:
            self.skipTest("PyTorch unavailable")
        torch.set_num_threads(1)
        directory = Path(__file__).resolve().parents[1] / "neural_network/MLP"
        with patch.object(sys, "path", [str(directory), *sys.path]):
            engine = importlib.import_module("neural_network.MLP.mlp_layernorm_shuffled_ladder100_dualeval")
        for model_type, label in (("logistic", "original"), ("logistic", "global"),
                                  ("mlp", "original"), ("mlp", "global")):
            with self.subTest(model=model_type), self.reader(label) as reader:
                scaler, _ = batches.fit_train_scaler(reader, batch_size=2)
                bridge = batches.LegacyRowAdapter(reader)
                dropout = 0.0 if model_type == "logistic" else 0.30
                args = Namespace(auc_bins=128, features="primary_secondary", batch_size=2,
                                 seed=42, secondary_cache_size=1, eval_batch_size=2, dropout=dropout,
                                 model_type=model_type)
                torch.manual_seed(42)
                model = (engine.LogisticRegression(1792) if model_type == "logistic" else engine.MLP(1792, 0.30))
                device = torch.device("cpu")
                optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.0001)
                scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(optimizer, 20, 1, 1e-5)
                criterion = torch.nn.BCEWithLogitsLoss()
                jobs = [engine.ChunkJob(0, 0)]
                before = [p.detach().clone() for p in model.parameters()]
                with patch.object(engine, "load_chunk_metadata", bridge.load_chunk_metadata),                      patch.object(engine, "load_rows", bridge.load_rows),                      patch.object(torch.cuda, "is_available", return_value=False):
                    meta = bridge.load_chunk_metadata({}, 0)
                    selected = np.array([1, 0], dtype=np.int64)
                    X, y = engine._load_chunk_rows({}, 0, meta, selected, args.features, 1, {})
                    np.testing.assert_array_equal(X, self.expected[selected])
                    np.testing.assert_array_equal(y, meta["y"][selected])
                    training = engine.train_block(model, optimizer, criterion, scaler, [{}], jobs, jobs,
                                                  args, 0, False, 0, 1, device)
                    self.assertTrue(any(not torch.equal(a, b) for a, b in zip(before, model.parameters())))
                    self.assertTrue(np.isfinite(training.compute()["loss"]))
                    result = engine.evaluate_split(model, criterion, scaler, [{}], jobs, 1, args,
                                                   False, 0, 1, device, {jobs[0]: np.array([2, 3])})
                    self.assertTrue(np.isfinite(result["loss"]))
                    checkpoint = self.root / f"{model_type}.pt"
                    engine.save_checkpoint(checkpoint, model, optimizer, scheduler, args, 0, 1, 1, 1)
                    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
                    model.load_state_dict(state["model_state_dict"])
                    optimizer.load_state_dict(state["optimizer_state_dict"])
                    scheduler.load_state_dict(state["scheduler_state_dict"])
                    self.assertEqual(state["completed_epochs"], 1)
