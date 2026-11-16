import unittest
import numpy as np
from data_pipeline.scripts.data_augmentation.generate_blosum62_variants import build_variants
from data_pipeline.scripts.data_splitting.split_data import assign_row_splits, iter_physical_chunks
from tests.helpers import PipelineCase


class AugmentationTests(unittest.TestCase):
    def test_known_highest_scoring_blosum_substitutions(self):
        self.assertEqual(build_variants('ADW'), ['ADW', 'SDW', 'AEW', 'ADY'])

    def test_one_substitution_per_position_and_original_first(self):
        sequence = 'ACDEFGHIKLMNPQRSTVWYACDEF'
        variants = build_variants(sequence)
        self.assertEqual(len(variants), 26)
        self.assertEqual(variants[0], sequence)
        for position, variant in enumerate(variants[1:]):
            self.assertEqual([i for i, (a, b) in enumerate(zip(sequence, variant)) if a != b], [position])
            self.assertEqual(len(variant), 25)
            self.assertTrue(set(variant) <= set('ACDEFGHIKLMNPQRSTVWY'))


class SplittingTests(PipelineCase):
    def test_stratified_counts_seed_and_row_coverage(self):
        labels = np.tile([0, 1], 50)
        splits = assign_row_splits(labels, seed=42, chunk_id=0)
        np.testing.assert_array_equal(splits, assign_row_splits(labels, 42, 0))
        self.assertFalse(np.array_equal(splits, assign_row_splits(labels, 43, 0)))
        for label in (0, 1):
            self.assertEqual(np.bincount(splits[labels == label], minlength=3).tolist(), [40, 5, 5])

    def test_invalid_labels_and_ratios_are_rejected(self):
        for kwargs in [{'labels': [0, 2]}, {'labels': [0, 1], 'train': .9, 'validation': .2}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                assign_row_splits(seed=42, chunk_id=0, **kwargs)

    def test_csv_read_blocks_do_not_split_a_physical_chunk(self):
        chunks = list(iter_physical_chunks(self.primary / 'master_index.csv', read_rows=2))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0][0], 0)
        self.assertEqual(chunks[0][1]['row_idx_in_chunk'].tolist(), list(range(6)))


class ClassificationTests(unittest.TestCase):
    def test_epitope_match_uses_one_based_exact_coordinates(self):
        from data_pipeline.scripts.data_classification.epitope_classification import validate_exact_match
        protein = 'ACDEFGHIKLMNPQRSTVWY'
        self.assertTrue(validate_exact_match(protein, 'DEF', 3, 5))
        for start, end in [(4, 6), (0, 2), (19, 21)]:
            self.assertFalse(validate_exact_match(protein, 'DEF', start, end))

    def test_position_score_is_centered_and_symmetric(self):
        from data_pipeline.scripts.data_classification.epitope_classification import compute_epitope_position_score
        centered = compute_epitope_position_score(1, 25, 10, 16, 25)
        left = compute_epitope_position_score(1, 25, 1, 7, 25)
        right = compute_epitope_position_score(1, 25, 19, 25, 25)
        self.assertEqual(centered, 0)
        self.assertLess(left, 0)
        self.assertAlmostEqual(left, -right)
