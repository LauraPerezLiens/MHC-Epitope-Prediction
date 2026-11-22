import unittest

from data_pipeline.scripts.iedb_download_audit.audit import compare_record, conditions, windows
from data_pipeline.scripts.iedb_download_audit.live import check_pages


class IedbDownloadAuditTests(unittest.TestCase):
    def event(self, **values):
        return {
            "epitope__name": "ACDEFGHIK",
            "epitope__starting_position": "2",
            "epitope__ending_position": "10",
            "epitope__source_molecule_iri": "https://db/P1.2",
            "epitope__molecule_parent_iri": "http://db/P1",
            "assay_id__iedb_iri": "http://www.iedb.org/assay/1",
            "epitope__epitope_iri": "http://www.iedb.org/epitope/2",
            **values,
        }

    def test_plain_sequence_preserves_a_versioned_source_and_parent(self):
        old, new, change, reasons, seq, _, _, assay = compare_record(self.event())
        self.assertEqual(change, "unchanged")
        self.assertEqual(new[:5], old)
        self.assertEqual(new[3:5], ("https://db/P1.2", "http://db/P1"))
        self.assertEqual(seq, "ACDEFGHIK")
        self.assertFalse(reasons)
        self.assertTrue(assay.endswith("/1"))

    def test_missing_coordinates_are_retained_and_ambiguous_names_are_not_truncated(self):
        old, new, change, reasons, *_ = compare_record(self.event(epitope__ending_position=""))
        self.assertIsNone(old)
        self.assertEqual(change, "added")
        self.assertIn("missing_coordinates", reasons)
        self.assertEqual(new[-1], "http://www.iedb.org/epitope/2")
        old, _, change, reasons, seq, legacy, *_ = compare_record(
            self.event(epitope__name="N-acetyl ACDEFGHIK")
        )
        self.assertEqual(old[0], legacy)
        self.assertEqual(legacy, "N")
        self.assertEqual(change, "modified")
        self.assertEqual(seq, "")
        self.assertIn("sequence_requires_review", reasons)

    def test_alternative_differs_in_a_single_filter(self):
        row = {"host__name": "Homo sapiens (human)", "epitope__source_organism": "Homo sapiens",
               "epitope__object_type": "Linear peptide", "mhc_restriction__class": "II",
               "mhc_restriction__name": "HLA-DQA1*01:01/DQB1*05:01",
               "assay__qualitative_measurement": "Not positive"}
        old, new = conditions(row, "human", "mhc-II", "HLA-DQ")
        self.assertTrue(all(old.values()))
        self.assertEqual([k for k in new if old[k] != new[k]], ["positive"])

    def test_window_bounds_and_truncated_page(self):
        self.assertEqual(list(windows(2, 9, 26)), [1, 2])
        pages = {0: ([{"id": 1}], "0-0/*"), 1: ([{"id": 2}], "1-1/*")}
        rows, _ = check_pages(lambda offset, size: pages[offset], 2, 10)
        self.assertEqual(len(rows), 2)
        with self.assertRaisesRegex(ValueError, "Repeated payload"):
            check_pages(lambda offset, size: ([{"id": 1}], f"{offset}-{offset}/*"), 2, 10)
        with self.assertRaisesRegex(ValueError, "Unexpected pagination"):
            check_pages(lambda offset, size: ([], "*/*"), 1, 10)


if __name__ == "__main__":
    unittest.main()
