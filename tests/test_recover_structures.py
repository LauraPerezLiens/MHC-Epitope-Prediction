import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.scripts.rebuild_iedb import recover_structures as recovery

from data_pipeline.scripts.rebuild_iedb.recover_structures import decide, recover_window


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.sequence = "ACDEFGHIKLMNPQRSTVWYACDEFGH"
        self.structure = "CHE" * 9
        self.gap = dict(url="example.test/P12345.2", sha256="sha", accession="P12345.2",
                        version="2", structure_status="missing_prediction", sequence=self.sequence)
        self.prediction = dict(source_url="example.test/P67890", sequence=self.sequence,
                               structure=self.structure, prediction_id="prediction")

    def test_exact_alias_is_accepted_and_conflicting_predictions_are_rejected(self):
        status, predictions = decide([self.gap], [self.prediction], [])
        self.assertEqual((status, predictions), ("recovered", [self.prediction]))
        conflict = dict(self.prediction, structure="C" * len(self.sequence))
        self.assertEqual(decide([self.gap], [self.prediction, conflict], [])[0], "ambiguous_prediction")

    def test_full_sequence_and_structure_length_are_required(self):
        mismatch = dict(self.prediction, source_url=self.gap["url"], sequence="M" + self.sequence[1:])
        self.assertEqual(decide([self.gap], [mismatch], [mismatch])[0], "incompatible_full_sequence")
        short = dict(self.prediction, structure=self.structure[:-1])
        self.assertEqual(decide([self.gap], [short], [])[0], "incompatible_length")

    def test_window_uses_original_interval_and_preserves_previous_predictions(self):
        url = self.gap["url"]
        row = dict(window_id=f"HLA-A|{url}|2", family="HLA-A", parent_url=url, parent_sha256="sha",
                   parent_accession="P12345.2", parent_version="2", window_start=2, window_end=26,
                   sequence=self.sequence[1:26], secondary_structure=None, structure_status="missing_prediction")
        result = recover_window(row, self.gap, self.prediction, "exact_full_sequence_other_identifier")
        self.assertEqual(result["secondary_structure"], self.structure[1:26])
        self.assertEqual(result["window_id"], row["window_id"])
        with self.assertRaises(ValueError):
            recover_window(dict(row, sequence=self.sequence[:25]), self.gap, self.prediction, "alias")
        with self.assertRaises(ValueError):
            recover_window(dict(row, secondary_structure="C" * 25), self.gap, self.prediction, "alias")

    def test_no_gaps_publishes_an_empty_overlay_and_headers(self):
        with TemporaryDirectory() as scratch:
            parent = Path(scratch)
            root = parent / "input"
            root.mkdir()
            output = parent / "output"
            fasta = parent / "reference.csv"
            fasta.touch()
            for name in ("global_index.parquet", "structure_gaps.tsv"):
                (root / name).touch()
            (root / "config.json").write_text(json.dumps({
                "scope": [], "structure_inputs": {}, "fasta": [recovery.signature(fasta)],
            }))
            (root / "summary.json").write_text(json.dumps({
                "status": "validated", "scope": "full", "global_index": {"observations": 1},
                "validation": {"fixture": {"structural_windows_matched": 1}},
            }))
            with patch.object(recovery, "load_archived", return_value={}), \
                    patch.object(recovery, "scan_archives", return_value=({}, {}, [])):
                with patch.object(recovery, "write_report", side_effect=InterruptedError("fixture")):
                    with self.assertRaisesRegex(InterruptedError, "fixture"):
                        recovery.run(root, output)
                self.assertFalse(output.exists())
                self.assertEqual(list(parent.glob(".structure_recovery_*")), [])
                recovery.run(root, output)
            self.assertEqual(pq.read_table(output / "window_structures.parquet").num_rows, 0)
            self.assertTrue((output / "proteins.tsv").read_text().startswith("parent_accession\t"))
            metrics = json.loads((output / "metrics.json").read_text())
            self.assertEqual(metrics["matched_after"], 1)
            self.assertEqual(metrics["remaining_windows"], 0)

    def test_overlay_allows_sparse_original_positions_but_checks_expected_count(self):
        gap = {**self.gap, "binary_windows": 2}
        rows = [
            dict(window_id=f"HLA-A|{gap['url']}|{start}", family="HLA-A", parent_url=gap["url"],
                 parent_sha256=gap["sha256"], parent_accession=gap["accession"], parent_version=gap["version"],
                 window_start=start, window_end=start + 24, sequence=self.sequence[start - 1:start + 24],
                 secondary_structure=None, structure_status=gap["structure_status"])
            for start in (3, 1)
        ]
        recovered = {"HLA-A": {gap["url"]: (gap, self.prediction, "alias")}}
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "families").mkdir()
            path = root / "families/HLA-A.parquet"
            table = pa.Table.from_pylist(rows)
            pq.write_table(table, path)
            recovery.write_overlay(root, root, recovered)
            output = pq.read_table(root / "window_structures.parquet").to_pylist()
            self.assertEqual([row["window_id"] for row in output], [row["window_id"] for row in rows])
            self.assertEqual([row["secondary_structure"] for row in output],
                             [self.structure[2:27], self.structure[:25]])
            pq.write_table(table.slice(0, 1), path)
            with self.assertRaisesRegex(ValueError, "Incomplete recovery"):
                recovery.write_overlay(root, root, recovered)


            replacement = dict(rows[1], window_id=f"HLA-A|{gap['url']}|2",
                               window_start=2, window_end=26, sequence=self.sequence[1:26])
            pq.write_table(pa.Table.from_pylist([rows[0], replacement]), path)
            recovery.write_overlay(root, root, recovered)
            substituted = pq.read_table(root / "window_structures.parquet").to_pylist()
            self.assertEqual([row["window_id"] for row in substituted],
                             [rows[0]["window_id"], replacement["window_id"]])
