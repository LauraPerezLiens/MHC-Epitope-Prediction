import unittest

import numpy as np

from data_pipeline.scripts.source_audits.investigate_embedding_cases import distances
from data_pipeline.scripts.source_audits.recover_epitope_coordinates import (
    coordinate_state, coordinates, occurrences,
)


class FollowupAuditTests(unittest.TestCase):
    def test_occurrences_use_inclusive_coordinates_and_include_overlap(self):
        self.assertEqual(list(occurrences("BAAAB", "AA")), [(2, 3), (3, 4)])
        self.assertEqual(list(occurrences("BAAAB", "AAA")), [(2, 4)])
        self.assertEqual(list(occurrences("BAAAB", "ABC")), [])

    def test_coordinate_formats_do_not_round_nonintegral_values(self):
        self.assertEqual(coordinates("3.0", "11"), (3, 11))
        self.assertEqual(coordinates("3.4", "11"), (0, 0))
        self.assertEqual(coordinate_state("", "NaN"), "both_absent")
        self.assertEqual(coordinate_state("1", ""), "partially_absent")
        self.assertEqual(coordinate_state("1", "2"), "contradictory_or_invalid")

    def test_metrics_preserve_exact_equality_boundary(self):
        values = np.array([3, 4], dtype=np.float32)
        different = np.array([0, 4], dtype=np.float32)
        result = distances(values, different)
        self.assertFalse(result["exact"])
        self.assertEqual(result["max_abs"], 3)
        self.assertEqual(result["euclidean"], 3)
        self.assertAlmostEqual(result["cosine"], 0.8)
        self.assertTrue(distances(values, values.copy())["exact"])
        zero = np.array([0, 0], dtype=np.float32)
        self.assertIsNone(distances(values, zero)["cosine"])


if __name__ == "__main__":
    unittest.main()
