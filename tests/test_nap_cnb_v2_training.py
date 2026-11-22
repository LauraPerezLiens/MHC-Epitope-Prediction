"""Planning tests use manifests and tiny fixtures, without importing trainers."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from data_pipeline import nap_cnb_v2 as cli
from tests import test_nap_cnb_v2_validation as fixtures


class TrainingPlanTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ValidationTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.write, self.invoke = self.fixture.root, self.fixture.write, self.fixture.invoke
        profiles = json.loads(cli.TRAIN_PROFILES.read_text())["profiles"]
        for profile in profiles.values():
            self.write(profile["script"], "raise AssertionError('trainer was launched')")

    def request(self, model, data, label, *extra):
        result = self.invoke("train", "--root", self.root, "--model", model, "--data", data,
                             "--label", label, "--json", *extra)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertIn("DISABLED", report["execution"])
        return report

    @unittest.skipIf(fixtures.pq is None, "PyArrow is unavailable to build fixtures")
    def test_original_labels_embeddings_splits_and_scaler(self):
        self.fixture.catalogs()
        self.fixture.split_report()
        self.fixture.d1_manifest()
        for model in ("lr", "mlp"):
            for label, rows in (("global", 9), ("original", 10)):
                with self.subTest(model=model, label=label):
                    report = self.request(model, "original", label, "--dry-run")
                    self.assertEqual(report["overall"], "INCOMPLETE", report)
                    self.assertEqual(report["dataset"]["label"], "label_" + label)
                    self.assertEqual(report["dataset"]["rows"], rows)
                    self.assertEqual(report["dataset"]["dimensions"]["combined"], 1792)
                    self.assertEqual(sum(row["rows"] for row in report["dataset"]["by_split"].values()), rows)
                    self.assertIsNone(report["dataset"]["scaler"]["path"])
                    self.assertIsNone(report["command_preview"])
                    self.assertFalse(Path(report["output"]).exists())
        # The preflight rejects dimension drift even if the reference paths exist.
        d1 = self.fixture.d1
        d1["embeddings"]["ProtT5"]["dimension"] = 512
        self.write(cli.D1, d1)
        self.assertEqual(self.request("lr", "original", "global")["overall"], "INCOMPATIBLE")

    @unittest.skipIf(fixtures.pq is None, "PyArrow is unavailable to build fixtures")
    def test_preflight_reports_policy_and_rejects_cross_view_scaler(self):
        import zipfile

        self.fixture.catalogs()
        self.fixture.split_report()
        self.fixture.d1_manifest()
        report = self.request("lr", "original", "global")
        policy = report["checkpoint_policy"]
        self.assertEqual((policy["checkpoint_selection"], policy["final_evaluation"]), ("VALIDATION", "TEST"))
        self.assertFalse(policy["test_during_training"])
        scaler = report["dataset"]["scaler"]
        self.assertEqual(scaler["status"], "REQUIRES_TRAIN_FIT")
        path = (self.root / scaler["planned_path"]).resolve()
        path.parent.mkdir(parents=True)
        metadata = cli.scaler_contract(self.root, "global", report["dataset"])
        with zipfile.ZipFile(path, "w") as archive:
            for key in ("primary_mean", "primary_scale", "secondary_mean", "secondary_scale",
                        "sampled_dataset_names", "sampled_chunk_ids"):
                archive.writestr(f"{key}.npy", b"numeric payload deliberately not inspected by preflight")
            archive.writestr("provenance.json", json.dumps(
                {**metadata, "output": str(path), "batch_size": 8192}))
        matched = self.request("lr", "original", "global")
        self.assertEqual(matched["dataset"]["scaler"]["status"], "METADATA_MATCH")
        self.assertEqual(matched["overall"], "INCOMPLETE")
        base_path = path.with_name("base.npz")
        base_path.write_bytes(path.read_bytes())
        rejected = self.request("lr", "original", "original")
        self.assertEqual(rejected["dataset"]["scaler"]["status"], "INCOMPATIBLE")
        self.assertEqual(rejected["overall"], "INCOMPATIBLE")

    def test_historical_layout_is_available_but_not_v2_and_d2_is_absent(self):
        root = cli.HISTORICAL_FEATURES
        self.write(root / "feature_layout.json", {"format": "primary_secondary_float32_v1", "rows": 20, "chunks": 1,
                                                   "primary_dim": 1024, "secondary_dim": 768,
                                                   "normalized": False, "complete": True})
        self.write(root / "reorder_manifest.json", {"rows": 20, "chunks": 1})
        chunk = root / "mixed/classification_mixed_ProtT5_chunks"
        self.write(chunk / "chunk_000000_X.npy", "data must not be read")
        for field in ("y", "split_id", "group_id"):
            self.write(chunk / "chunk_metadata" / f"chunk_000000_{field}.npy", "data must not be read")
        self.write(cli.HISTORICAL_SCALER, "never load this")
        for model in ("lr", "mlp"):
            report = self.request(model, "blosum62", "original")
            self.assertEqual(report["overall"], "INCOMPATIBLE")
            self.assertEqual(report["dataset"]["scaler"]["status"], "HISTORICAL_ONLY")
            self.assertFalse(report["dataset"]["splits"]["v2_independence_verified"])
            report = self.request(model, "blosum62", "global")
            self.assertIn("D2 is not available", report["blockers"][0])
            self.assertNotIn("dataset", report)

    def test_configuration_overrides_and_incompatibility(self):
        config = Path("experiment.json")
        self.write(config, {"schema_version": 1, "profile": "lr_natural", "parameters": {"epochs": 2}})
        result = self.request("lr", "blosum62", "global", "--config", config)
        self.assertEqual(result["overall"], "INCOMPATIBLE")
        self.assertIn("exact 50/50", result["errors"][0]["message"])
        self.write(config, {"schema_version": 1, "profile": "lr_balanced", "parameters": {"epochs": 2}})
        result = self.request("lr", "blosum62", "global", "--config", config)
        self.assertEqual(result["profile"]["parameters"]["epochs"], 2)
        self.assertEqual(self.request("mlp", "original", "global", "--config", config)["overall"], "INCOMPATIBLE")
        self.write(config, {"schema_version": 1, "parameters": {"batch_size": 3}})
        result = self.request("lr", "original", "global", "--config", config)
        self.assertIn("even batch size", result["errors"][0]["message"])
        self.write(config, {"schema_version": 1, "scaler": "unsafe substitution"})
        self.assertEqual(self.request("lr", "original", "global", "--config", config)["overall"], "INCOMPATIBLE")

    def test_planning_without_dry_run_cannot_call_a_subprocess_or_create_output(self):
        args = SimpleNamespace(model="lr", data="blosum62", label="global", config=None,
                               dry_run=False, output=Path("new-trial"))
        before = {p: p.stat().st_mtime_ns for p in self.root.rglob("*")}
        report = {}
        with patch("subprocess.Popen", side_effect=AssertionError("Launched a process")),              patch("pathlib.Path.mkdir", side_effect=AssertionError("Created a directory")):
            self.assertEqual(cli.training_plan(self.root, args, report), 1)
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.root.rglob("*")}, before)
