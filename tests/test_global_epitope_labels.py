import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.scripts.global_epitope_labels import build, validate


class GlobalEpitopeLabelTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sources = self.root / "source"
        self.output = self.root / "output"
        self.shared = "A" * 25
        self.multi = "C" * 25
        self.unlabeled = "D" * 25
        self.case_variant = "a" * 25
        self.multi_four = "E" * 25
        rows = {
            "HLA-A": [(self.shared, 1), (self.shared, 0), (self.multi, 1),
                      (self.unlabeled, 0), (self.case_variant, 0), (self.multi_four, 1)],
            "HLA-B": [(self.shared, 0), (self.multi, 1), (self.unlabeled, 0), (self.multi_four, 1)],
            "HLA-C": [(self.multi_four, 1)],
            "HLA-DP": [(self.multi_four, 1)],
        }
        for organism, mhc_class, family in build.FAMILIES:
            folder = self.sources / organism / mhc_class / family
            folder.mkdir(parents=True)
            path = folder / f"classification_{organism}_{mhc_class}_{family}.csv"
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["25aa_seq", "contains_epitope", "protein_group_id", "group_id",
                                 "selected_epitope", "epitope_pos_score", "extra"])
                for i, (sequence, label) in enumerate(rows.get(family, [(self.unlabeled, 0)])):
                    writer.writerow([sequence, label, "0007", f"{i:03d}", "NA" if label else "",
                                     "0.0100", "context, original"])
        self.originals = {p: p.read_bytes() for p in self.sources.rglob("*.csv")}

    def test_build_preserves_context_and_aggregates_exact_evidence(self):
        summary = build.build(self.output, self.sources, batch_rows=2)
        unique = {record["original_seq"]: record
                  for record in pq.read_table(self.output / "sequences.parquet").to_pylist()}
        self.assertEqual(len(unique), 5)
        self.assertEqual(unique[self.shared]["global_positive_families"], ["HLA-A"])
        self.assertEqual(unique[self.shared]["global_positive_evidence_count"], 1)
        self.assertEqual(unique[self.multi]["global_positive_families"], ["HLA-A", "HLA-B"])
        self.assertEqual(unique[self.multi]["global_positive_evidence_count"], 2)
        for seq in (self.unlabeled, self.case_variant):
            self.assertEqual(unique[seq]["global_contains_epitope"], 0)
            self.assertEqual(unique[seq]["global_label_status"], "unlabeled")
            self.assertEqual(unique[seq]["global_positive_families"], [])
        self.assertEqual(unique[self.multi_four]["global_positive_family_count"], 4)
        self.assertEqual(summary["mixed_label_sequences"], 1)
        self.assertEqual(summary["mixed_label_rows"], 3)
        self.assertEqual(summary["rows_changed"], 2)
        self.assertEqual(summary["cross_family_evidence"],
                         {"exactly_1": 1, "exactly_2": 1, "exactly_3": 0, "more_than_3": 1})
        rows = pq.read_table(self.output / "rows/human_mhc-I_HLA-B.parquet").to_pylist()
        self.assertEqual([r["source_row_index"] for r in rows], [0, 1, 2, 3])
        self.assertEqual(rows[0]["source_file"], "human/mhc-I/HLA-B/classification_human_mhc-I_HLA-B.csv")
        self.assertEqual(rows[0]["contains_epitope"], 0)
        self.assertEqual(rows[0]["global_contains_epitope"], 1)
        self.assertEqual(rows[0]["protein_group_id"], rows[1]["protein_group_id"])
        self.assertEqual(rows[0]["protein_group_id"], "0007")
        self.assertEqual(rows[1]["selected_epitope"], "NA")
        self.assertEqual(rows[0]["epitope_pos_score"], "0.0100")
        self.assertEqual(rows[0]["extra"], "context, original")
        self.assertEqual({p: p.read_bytes() for p in self.originals}, self.originals)

    def test_resume_and_audit_detect_tampering(self):
        with patch.object(build, "export_unique", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                build.build(self.output, self.sources, batch_rows=2)
        summary = build.build(self.output, self.sources, batch_rows=2)
        self.assertEqual(summary["original_rows"], 19)
        row_file = self.output / "rows/human_mhc-I_HLA-A.parquet"
        table = pq.read_table(row_file)
        index = table.schema.get_field_index("group_id")
        table = table.set_column(index, table.schema.field(index), pa.array(["bad"] * len(table)))
        pq.write_table(table, row_file, row_group_size=2)
        config = build.input_config(self.sources, 2, None)
        with self.assertRaisesRegex(ValueError, "Source values"):
            validate.validate_locked(self.output, config)

    def test_resume_rolls_back_an_interrupted_index_batch(self):
        add = build.add_counts
        calls = 0

        def interrupt_after_write(db, sequences, labels, family_index):
            nonlocal calls
            calls += 1
            add(db, sequences, labels, family_index)
            if calls == 2:
                raise KeyboardInterrupt

        with patch.object(build, "add_counts", side_effect=interrupt_after_write):
            with self.assertRaises(KeyboardInterrupt):
                build.build(self.output, self.sources, batch_rows=2)
        summary = build.build(self.output, self.sources, batch_rows=2)
        self.assertEqual(summary["original_rows"], 19)
        self.assertEqual(summary["original_positive_rows"], 7)
        self.assertEqual(summary["rows_changed"], 2)

    def test_ram_index_resumes_from_disk_without_duplicate_counts(self):
        add = build.add_counts
        calls = 0

        def interrupt_during_second_family(db, sequences, labels, family_index):
            nonlocal calls
            calls += 1
            add(db, sequences, labels, family_index)
            if calls == 4:
                raise KeyboardInterrupt

        with patch.object(build, "add_counts", side_effect=interrupt_during_second_family):
            with self.assertRaises(KeyboardInterrupt):
                build.build(self.output, self.sources, batch_rows=2, ram_index=True)
        summary = build.build(self.output, self.sources, batch_rows=2, ram_index=True)
        self.assertEqual(summary["original_rows"], 19)
        self.assertEqual(summary["original_positive_rows"], 7)
        self.assertEqual(summary["rows_changed"], 2)

    def test_sample_limits_each_source_and_refuses_scope_change(self):
        summary = build.build(self.output, self.sources, batch_rows=1, rows_per_family=1)
        self.assertEqual(summary["original_rows"], 11)
        self.assertEqual(summary["rows_per_family"], 1)
        self.assertIsNone(summary["historical_comparison"])
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            build.build(self.output, self.sources, batch_rows=1, rows_per_family=2)

    def test_refuses_to_write_inside_sources(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            build.build(self.sources / "results", self.sources, rows_per_family=1)


if __name__ == "__main__":
    unittest.main()
