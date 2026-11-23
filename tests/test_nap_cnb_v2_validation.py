"""Metadata fixtures for the quick validation commands."""
import hashlib
import json
import unittest
from unittest.mock import patch

from data_pipeline import nap_cnb_v2 as cli
from tests import test_nap_cnb_v2_status as status_tests

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    pa = pq = None


class ValidationTest(unittest.TestCase):
    @unittest.skipIf(pq is None, "PyArrow is unavailable to build fixtures")
    def test_parquet_footer_rejects_duplicate_columns(self):
        path = self.root / "duplicate.parquet"
        pq.write_table(pa.Table.from_arrays([pa.array(["first"]), pa.array(["second"])],
                                          names=["sequence", "sequence"]), path)
        with self.assertRaisesRegex(ValueError, "Duplicate Parquet column"):
            cli.footer_contract(cli.Component(self.root, path), path, ("sequence", {}),
                                1, path.stat().st_size)

    @unittest.skipIf(pq is None, "PyArrow is unavailable to build fixtures")
    def test_parquet_footer_rejects_invalid_leading_magic(self):
        relative = cli.VIEWS / "fixture.parquet"
        size = self.footer(relative, ("sequence", {}), 2)
        path = self.root / relative
        original = path.read_bytes()
        path.write_bytes(b"FAIL" + original[4:])
        self.assertEqual(path.stat().st_size, size)
        with self.assertRaisesRegex(ValueError, "Invalid Parquet header"):
            cli.read_footer(cli.Component(self.root, relative), relative)

    def test_selection_rejects_noninteger_schema_version(self):
        for version in (True, 1.0):
            with self.subTest(version=version):
                self.write(cli.SELECTION, {**self.selection, "schema_version": version})
                self.assert_outcome("validate-selection", "FAIL")

    @unittest.skipIf(pq is None, "PyArrow is unavailable to build fixtures")
    def test_footer_scope_with_content_and_schema_mutations(self):
        relative = cli.VIEWS / "fixture.parquet"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        component = cli.Component(self.root, relative)
        schema = ("id", {"label": "int8", "split": "uint8"})
        valid = pa.table({"id": ["a", "b"], "label": pa.array([0, 1], type=pa.int8()),
                          "split": pa.array([0, 2], type=pa.uint8())})
        for name, table in {
            "exchanged rows": valid.take([1, 0]),
            "duplicate row": valid.take([0, 0]),
            "identifier": valid.set_column(0, "id", pa.array(["a", "c"])),
            "label": valid.set_column(1, "label", pa.array([0, 3], type=pa.int8())),
            "split": valid.set_column(2, "split", pa.array([0, 3], type=pa.uint8())),
            "null label": valid.set_column(1, "label", pa.array([0, None], type=pa.int8())),
            "column order": valid.select(["split", "id", "label"]),
        }.items():
            with self.subTest(name=name):
                pq.write_table(table, path, row_group_size=1)
                self.assertEqual(pq.read_metadata(path).num_row_groups, 2)
                footer = cli.footer_contract(component, relative, schema, 2, path.stat().st_size)
                self.assertEqual(footer["footer_rows"], 2)
        for name, table in {
            "missing": valid.drop(["id"]),
            "additional": valid.append_column("extra", pa.array([0, 0])),
            "boolean": valid.set_column(1, "label", pa.array([True, False])),
            "float": valid.set_column(2, "split", pa.array([0., 2.])),
            "negative signed": valid.set_column(2, "split", pa.array([-1, 0], type=pa.int8())),
        }.items():
            with self.subTest(name=name):
                pq.write_table(table, path)
                with self.assertRaisesRegex(ValueError, "Incompatible Parquet schema"):
                    cli.footer_contract(component, relative, schema, 2, path.stat().st_size)
        pq.write_table(valid.slice(0, 1), path)
        with self.assertRaisesRegex(ValueError, "Footer rows"):
            cli.footer_contract(component, relative, schema, 2, path.stat().st_size)
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "Invalid Parquet trailer"):
            cli.read_footer(component, relative)

    def setUp(self):
        fixture = status_tests.StatusTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root, self.write, self.invoke = fixture.root, fixture.write, fixture.invoke
        self.selection = fixture.selection
        self.selection["totals"].update(positive_windows=4, excluded_positive=0, excluded_negative=2)
        self.selection["counts_by_family"] = {
            "fixture": {k: v for k, v in self.selection["totals"].items() if k != "excluded_positive"}
        }
        self.selection["supplement_sha256"] = {
            name: self.sha(cli.SELECTION.parent / name) for name in self.selection["supplement_sha256"]
        }
        self.write(cli.SELECTION, self.selection)

    def sha(self, name):
        return hashlib.sha256((self.root / name).read_bytes()).hexdigest()

    def check(self, command):
        result = self.invoke(command, "--root", self.root, "--json")
        self.assertFalse(result.stderr, result.stderr)
        return result.returncode, json.loads(result.stdout)

    def footer(self, path, schema, rows, override=None):
        strings, types = schema
        fields = {**dict.fromkeys(strings.split(), "string"), **types, **(override or {})}
        arrays = {key: pa.array([{"string": "x", "bool": False}.get(dtype, 0)] * rows, type=pa.type_for_alias(dtype))
                  for key, dtype in fields.items()}
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table(arrays), self.root / path)
        return (self.root / path).stat().st_size

    def catalogs(self):
        self.rows = dict(zip(cli.DATASET_SCHEMAS, (10, 8, 9, 12, 3)))
        self.metrics = {
            "selection_sha256": self.sha(cli.SELECTION),
            "families": {"fixture": {"original": 12, "original_positive": 4, "base": 10,
                                     "base_positive": 4, "removed": 2, "legacy_links": 3}},
            "global_sequences": 8, "global_positive": 3, "global_representations": 9,
            "global_positive_representations": 4, "files_bytes": {},
        }
        for name, schema in cli.DATASET_SCHEMAS.items():
            self.metrics["files_bytes"][name] = self.footer(cli.VIEWS / name, schema, self.rows[name])
        self.write(cli.METRICS, self.metrics)

    def frame(self, rows, positive):
        return {key: {"rows": n, "positive": p, "negative": n - p}
                for key, n, p in zip(cli.SPLIT_NAMES, rows, positive)}

    def split_report(self):
        size = self.footer(cli.ASSIGNMENTS, ("effective_group_id", {"split_id": "uint8"}), 8)
        self.splits = {
            "seed": 42, "version": "primary-blake2b-mod10-v1", "selection_sha256": self.sha(cli.SELECTION),
            "split_ids": dict(zip(("0", "1", "2"), cli.SPLIT_NAMES)),
            "effective_groups": 8, "effective_groups_by_split": dict(zip(cli.SPLIT_NAMES, (6, 1, 1))),
            "assignment_sha256": self.sha(cli.ASSIGNMENTS), "assignment_bytes": size,
            "global": self.frame((7, 1, 1), (3, 1, 0)), "base": self.frame((8, 1, 1), (3, 1, 0)),
            "verified_cross_primary_historical_edges": 0,
            "catalog_sha256": {name: self.sha(cli.VIEWS / f"{name}.parquet")
                               for name in ("base_dataset", "global_labels", "global_dataset")},
        }
        self.write(cli.SPLITS, self.splits)

    def d1_manifest(self):
        primary = {"inventory": str(cli.VIEWS / "inventory.parquet"),
                   "manifest": str(cli.PRIMARY / "manifest.json"),
                   "progress": str(cli.PRIMARY / "progress.sqlite"),
                   "shards": str(cli.PRIMARY / "shard-*.npy"), "key": "sequence", "dimension": 1024, "dtype": "float32"}
        secondary = {"index": str(cli.SECONDARY / "index.sqlite"),
                     "evidence": str(cli.SECONDARY / "secondarybert_report.md"),
                     "dimension": 768, "key": "secondary_structure", "dtype": "float32"}
        for path in (primary["inventory"], primary["progress"], secondary["index"], secondary["evidence"],
                     cli.PRIMARY / "shard-0000.npy"):
            self.write(path, "fixture: payload is not read")
        self.write(primary["manifest"], {"dimension": 1024, "sample_ordinals": None, "inventory": primary["inventory"],
                                         "selection_sha256": self.sha(cli.SELECTION),
                                         "inventory_sha256": self.sha(primary["inventory"])})
        self.write(cli.SECONDARY / "pilot.json", {"shape": [1, 768]})
        self.write(secondary["evidence"], "**2 estructuras C/H/E exactas**")
        sources = [cli.SELECTION, cli.ASSIGNMENTS, cli.SPLITS, cli.VIEWS / "global_labels.parquet",
                   cli.VIEWS / "global_dataset.parquet", *(primary[k] for k in ("manifest", "inventory", "progress")),
                   *[secondary[k] for k in ("index", "evidence")]]
        self.d1 = {
            "schema_version": 1, "id": "D1", "path_base": "repository_root", "status": "validated",
            "dataset": {"path": str(cli.VIEWS / "global_dataset.parquet"), "key": ["sequence", "secondary_structure"],
                        "label": "label_global", "augmentation": "none"},
            "splits": {"path": str(cli.ASSIGNMENTS), "validation": str(cli.SPLITS), "field": "split_id",
                       "join": {"sequence": "effective_group_id"}, "seed": 42,
                       "version": self.splits["version"], "codes": self.splits["split_ids"]},
            "embeddings": {"ProtT5": primary, "SecondaryBERT": secondary},
            "inputs_sha256": {str(p): self.sha(p) for p in sources}, "observations": 9,
            "by_split": self.splits["global"],
            "validation": {"unique_representations": 9, "unique_primary_keys": 8, "unique_secondary_keys": 2,
                           "confirmed_prott5_shards": 1,
                           "reproduced_all_split_assignments": True},
        }
        self.write(cli.D1, self.d1)

    def assert_outcome(self, command, expected):
        code, result = self.check(command)
        self.assertEqual((code, result["overall"]), (int(expected != "PASS"), expected), result)
        return result

    def test_selection_passes_and_omits_exhaustive_checks(self):
        result = self.assert_outcome("validate-selection", "PASS")
        self.assertEqual(result["checks"][0]["details"]["declared_rows"], 12)
        self.assertTrue(any(check["result"] == "SKIPPED" for check in result["checks"]))

    def test_selection_missing_manifest_or_reference(self):
        overlay = self.root / cli.SELECTION.parent / "overlay.parquet"
        overlay.unlink()
        self.assert_outcome("validate-selection", "FAIL")
        (self.root / cli.SELECTION).unlink()
        self.assert_outcome("validate-selection", "FAIL")

    def test_selection_incomplete_and_inconsistent(self):
        self.selection["counts_by_family"]["fixture"]["positive_final"] = 9
        self.write(cli.SELECTION, self.selection)
        self.assert_outcome("validate-selection", "FAIL")
        del self.selection["counts_by_family"]
        self.write(cli.SELECTION, self.selection)
        self.assert_outcome("validate-selection", "INCOMPLETE")

    @unittest.skipIf(pq is None, "PyArrow is not installed")
    def test_datasets_footer_and_missing_provenance(self):
        self.catalogs()
        old = pq.read_metadata

        def check_buffer(source):
            self.assertIsInstance(source, pa.BufferReader)
            return old(source)

        with patch.object(pq, "read_metadata", side_effect=check_buffer) as read,              patch.object(pq, "read_table", side_effect=AssertionError("Unexpected row read")):
            state, checks = cli.validate(self.root, "validate-datasets")
        self.assertEqual(state, "PASS", checks)
        self.assertEqual(read.call_count, 5)
        (self.root / cli.VIEWS / "window_provenance.parquet").unlink()
        self.assert_outcome("validate-datasets", "FAIL")

    @unittest.skipIf(pq is None, "PyArrow is not installed")
    def test_datasets_footer_schema_and_count_mismatches(self):
        self.catalogs()
        name = "global_dataset.parquet"
        for rows, override in ((8, None), (9, {"label_global": "int64"})):
            self.metrics["files_bytes"][name] = self.footer(cli.VIEWS / name, cli.DATASET_SCHEMAS[name],
                                                            rows, override)
            self.write(cli.METRICS, self.metrics)
            self.assert_outcome("validate-datasets", "FAIL")

    @unittest.skipIf(pq is None, "PyArrow is not installed")
    def test_splits_seed_counts_and_missing_report(self):
        self.catalogs()
        self.split_report()
        self.assert_outcome("validate-splits", "PASS")
        self.splits["seed"] = 43
        self.write(cli.SPLITS, self.splits)
        self.assert_outcome("validate-splits", "FAIL")
        self.splits["seed"] = 42
        self.splits["effective_groups_by_split"]["test"] = 2
        self.write(cli.SPLITS, self.splits)
        self.assert_outcome("validate-splits", "FAIL")
        (self.root / cli.SPLITS).unlink()
        self.assert_outcome("validate-splits", "FAIL")

    @unittest.skipIf(pq is None, "PyArrow is not installed")
    def test_d1_counts_dimensions_version_and_missing_embeddings(self):
        self.catalogs()
        self.split_report()
        self.d1_manifest()
        result = self.assert_outcome("validate-d1", "PASS")
        self.assertEqual(result["checks"][0]["details"]["dimensions"]["combined"], 1792)
        for change in ({"schema_version": 2}, {"schema_version": True}, {"schema_version": 1.0},
                       {"observations": 10},
                       {"embeddings": {**self.d1["embeddings"], "ProtT5": {
                           **self.d1["embeddings"]["ProtT5"], "dimension": 512}}}):
            self.write(cli.D1, {**self.d1, **change})
            self.assert_outcome("validate-d1", "FAIL")
        self.write(cli.D1, self.d1)
        (self.root / cli.SECONDARY / "index.sqlite").unlink()
        self.assert_outcome("validate-d1", "FAIL")

    def test_cli_help_root_exit_codes_and_no_fixture_changes(self):
        help_result = self.invoke("--help")
        self.assertIn("validate-d1", help_result.stdout)
        before = {p.relative_to(self.root): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.root.rglob("*")}
        result = self.invoke("--root", self.root, "validate-selection", "--json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["overall"], "PASS")
        invalid = self.invoke("validate-selection", "--root", self.root / "absent", "--json")
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual({p.relative_to(self.root): (p.stat().st_size, p.stat().st_mtime_ns)
                          for p in self.root.rglob("*")}, before)


if __name__ == "__main__":
    unittest.main()
