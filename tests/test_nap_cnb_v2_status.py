"""Small, standard-library tests for the metadata-only CLI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from data_pipeline import nap_cnb_v2 as cli


class StatusTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.write(cli.SELECTION.parent / "family.parquet", "fixture")
        self.write(cli.SELECTION.parent / "overlay.parquet", "fixture")
        self.write(cli.SELECTION.parent / "exclusions.parquet", "fixture")
        self.write(cli.SELECTION.parent / "global.parquet", "fixture")
        for directory in ("provenance", "evidence"):
            (self.root / cli.SELECTION.parent / directory).mkdir()
        info = (self.root / cli.SELECTION.parent / "family.parquet").stat()
        self.selection = {
            "schema_version": 1, "join_key": "window_id",
            "totals": {"windows": 14, "excluded": 2, "matched": 8, "recovered": 4,
                       "positive_final": 4, "negative_final": 8},
            "base_families": {"fixture": "family.parquet"}, "structure_overlay": "overlay.parquet",
            "exclusions": "exclusions.parquet", "provenance_directory": "provenance",
            "verified_evidence_directory": "evidence", "global_label_index": "global.parquet",
            "input_signatures": [{"path": "family.parquet", "bytes": info.st_size, "mtime_ns": info.st_mtime_ns}],
            "supplement_sha256": {"overlay.parquet": "recorded", "exclusions.parquet": "recorded"},
        }
        self.write(cli.SELECTION, self.selection)
        self.report = cli.SELECTION.parent / "final_selection_report.md"
        self.write(self.report, "## Integridad y procedencia")
        self.write(cli.SELECTION.parent / "report.md", "Base validada")
        self.write(cli.SELECTION.parent / "completion_report.md", "Structural closure")

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")

    def invoke(self, *args, command=None):
        return subprocess.run(
            [sys.executable, "-B", *(command or ("-m", "data_pipeline.nap_cnb_v2")), *map(str, args)],
            cwd=self.root, env={**os.environ, "PYTHONPATH": str(cli.ROOT)},
            text=True, capture_output=True, check=False,
        )

    def test_help_and_default_root_from_another_directory(self):
        help_result = self.invoke("--help")
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("status", help_result.stdout)
        result = self.invoke("status", "--json")
        self.assertEqual(json.loads(result.stdout)["root"], str(cli.ROOT))

    def test_alternative_root_on_either_side_and_d2_optional(self):
        for arguments in (("--root", self.root, "status"), ("status", "--root", self.root)):
            with self.subTest(arguments=arguments):
                result = self.invoke(*arguments, "--json")
                self.assertEqual(result.returncode, 1)  # The fixture lacks mandatory catalogs.
                payload = json.loads(result.stdout)
                components = payload["components"]
                self.assertEqual(components["selection"]["records"], 12)
                self.assertEqual(components["selection"]["status"], "CERTIFIED")
                self.assertEqual(components["secondary_structures"]["status"], "CERTIFIED")
                self.assertEqual(components["prott5"]["status"], "MISSING")
                self.assertEqual(components["d2"]["status"], "NOT AVAILABLE")
        self.assertIn("metadata-only", self.invoke("status", "--root", self.root).stdout)

    def test_invalid_arguments_and_root(self):
        result = self.invoke("validate-unsupported")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        result = self.invoke("status", "--root", self.root / "does-not-exist", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["errors"][0]["code"], "query_failed")

    def test_missing_present_unknown_and_inconsistent(self):
        def state():
            return cli.status(self.root)["selection"]["status"]

        (self.root / self.report).unlink()
        self.assertEqual(state(), "PRESENT")
        self.write(cli.SELECTION, {})
        self.assertEqual(state(), "UNKNOWN")
        self.write(cli.SELECTION, "{")
        self.assertEqual(state(), "INCONSISTENT")
        self.selection["totals"]["positive_final"] = 50
        self.write(cli.SELECTION, self.selection)
        self.assertEqual(state(), "INCONSISTENT")
        (self.root / cli.SELECTION).unlink()
        self.assertEqual(state(), "MISSING")

    def test_catalog_metadata_checks_size_without_opening_parquet(self):
        name = cli.VIEWS / "global_dataset.parquet"
        self.write(name, "dummy")
        self.write(cli.VIEWS / "metrics.json", {
            "selection_sha256": hashlib.sha256((self.root / cli.SELECTION).read_bytes()).hexdigest(),
            "global_representations": 9, "global_positive_representations": 3,
            "files_bytes": {name.name: 5}, "reopen_validation_seconds": 1,
        })
        result = cli.status(self.root)["global_dataset"]
        self.assertEqual((result["status"], result["records"]), ("CERTIFIED", 9))
        self.write(name, "different size")
        self.assertEqual(cli.status(self.root)["global_dataset"]["status"], "INCONSISTENT")

    def test_selection_stat_signature_scope(self):
        path = self.root / cli.SELECTION.parent / "family.parquet"
        original = path.stat()
        path.write_text("changed")
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000_000))
        self.assertEqual(cli.status(self.root)["selection"]["status"], "INCONSISTENT")
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assertEqual(cli.status(self.root)["selection"]["status"], "CERTIFIED")
        replacement = path.with_suffix(".tmp")
        replacement.write_text("another")
        os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
        replacement.replace(path)
        self.assertNotEqual(path.stat().st_ino, original.st_ino)
        self.assertEqual(cli.status(self.root)["selection"]["status"], "CERTIFIED")

    def test_read_only_with_audit_hook(self):
        guard = """
import os, runpy, sys
def guard(event, args):
    if event in {'subprocess.Popen', 'sqlite3.connect', 'os.mkdir', 'os.remove', 'os.rename'}:
        raise AssertionError(event)
    if event.startswith('socket.'):
        raise AssertionError(event)
    if event == 'import' and args[0].split('.')[0] in {'torch', 'tensorflow', 'transformers', 'pyarrow'}:
        raise AssertionError(args[0])
    if event == 'open':
        path, mode, flags = args
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError((path, mode, flags))
sys.addaudithook(guard)
sys.argv = ['nap_cnb_v2', *sys.argv[1:]]
runpy.run_module('data_pipeline.nap_cnb_v2', run_name='__main__')
"""
        before = {p.relative_to(self.root): p.stat().st_mtime_ns for p in self.root.rglob("*")}
        result = self.invoke("status", "--root", self.root, "--json", command=("-c", guard))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["components"]["selection"]["status"], "CERTIFIED")
        self.assertEqual({p.relative_to(self.root): p.stat().st_mtime_ns for p in self.root.rglob("*")}, before)


if __name__ == "__main__":
    unittest.main()
