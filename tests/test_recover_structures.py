import unittest

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
