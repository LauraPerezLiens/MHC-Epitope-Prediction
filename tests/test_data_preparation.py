import hashlib
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import numpy as np
import pyarrow as pa
from data_pipeline.scripts.data_classification import fetch_parent_proteins_fastas as fetch
from data_pipeline.scripts.data_augmentation.generate_blosum62_variants import build_variants
from data_pipeline.scripts.data_splitting.split_data import assign_row_splits, iter_physical_chunks
from data_pipeline.scripts.data_splitting import prepare_chunk_metadata, split_nap_cnb_v2 as v2
from data_pipeline.scripts.data_shuffling import resume_reorder_chunks
from tests.helpers import PipelineCase


class ReorderRecoveryTests(PipelineCase):
    def test_missing_committed_chunk_does_not_truncate_csv_or_remove_tail(self):
        primary = self.temp / "recovery"
        primary.mkdir()
        master = primary / "master_index.csv"
        csv = b"header\ncommitted\nuncommitted\n"
        master.write_bytes(csv)
        np.save(primary / "chunk_000001_X.npy", np.zeros((1, 1)))
        tail = primary / "chunk_000002_X.npy"
        np.save(tail, np.zeros((1, 1)))
        checkpoint = {"chunks": 2, "csv_bytes": len(b"header\ncommitted\n")}
        with self.assertRaisesRegex(ValueError, "Missing committed"):
            resume_reorder_chunks.restore_checkpoint(primary, checkpoint)
        self.assertEqual(master.read_bytes(), csv)
        self.assertTrue(tail.exists())
        np.save(primary / "chunk_000000_X.npy", np.zeros((1, 1)))
        resume_reorder_chunks.restore_checkpoint(primary, checkpoint)
        self.assertEqual(master.read_bytes(), b"header\ncommitted\n")
        self.assertFalse(tail.exists())


class FastaPublicationTests(PipelineCase):
    def test_interrupted_fasta_export_preserves_previous_csv(self):
        destination = self.temp / "human_parent_protein_fasta.csv"
        destination.write_text("previous complete export\n")

        def interrupted_write(frame, target, **kwargs):
            Path(target).write_text("partial")
            raise InterruptedError("write interrupted")

        with patch.object(fetch, "DATA_INTERMEDIATE", self.temp):
            with patch.object(fetch.pd.DataFrame, "to_csv", interrupted_write):
                with self.assertRaises(InterruptedError):
                    fetch.save_species_outputs("human", [])
            self.assertEqual(destination.read_text(), "previous complete export\n")
            self.assertEqual(list(self.temp.glob("*.partial")), [])
            fetch.save_species_outputs("human", [])
            self.assertIn("protein_url", destination.read_text())


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


class ExactPrimarySplitTests(unittest.TestCase):
    def test_assignment_matches_reference_and_ignores_order_and_slice_offset(self):
        keys = [letter * 25 for letter in "ACDEFGHIKLMNPQRSTVWY"]
        seed = 42
        expected = []
        for key in keys:
            digest = hashlib.blake2b(key.encode(), key=seed.to_bytes(8, "little"), digest_size=8)
            bucket = int.from_bytes(digest.digest(), "little") % 10
            expected.append(0 if bucket < 8 else bucket - 7)
        array = pa.array(["prefix", *keys, keys[0]]).slice(1)
        np.testing.assert_array_equal(v2.assign(array, seed), [*expected, expected[0]])
        np.testing.assert_array_equal(v2.assign(pa.array(keys[::-1]), seed), expected[::-1])
        for batch_size in (1, 7):
            parts = [v2.assign(array.slice(start, batch_size), seed)
                     for start in range(0, len(array), batch_size)]
            observed = np.concatenate(parts)
            self.assertEqual(observed.dtype, np.uint8)
            np.testing.assert_array_equal(observed, [*expected, expected[0]])

    def test_assignment_rejects_null_primary(self):
        with self.assertRaisesRegex(ValueError, "primary"):
            v2.assign(pa.array(["A" * 25, None, "C" * 25]), 42)

    def test_distribution_rejects_nonbinary_labels_before_counting(self):
        with self.assertRaisesRegex(ValueError, "binary"):
            v2.distribution(np.array([0], dtype=np.uint8), np.array([2], dtype=np.uint8))


    def test_distribution_rejects_split_before_uint8_arithmetic(self):
        for split in (3, 128, 255):
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "split"):
                v2.distribution(np.array([split], dtype=np.uint8), np.array([0], dtype=np.uint8))


class SplittingTests(PipelineCase):
    def test_group_overlap_counts_unsigned_split_codes(self):
        from data_pipeline.scripts.check_group_splits import accumulate

        counts = np.zeros((3, 3), dtype=np.uint64)
        accumulate(counts, np.array([1, 1, 2], dtype=np.int64),
                   np.array([0, 2, 1], dtype=np.uint64))
        np.testing.assert_array_equal(counts, [[0, 0, 0], [1, 0, 1], [0, 1, 0]])

    def test_metadata_rejects_codes_that_would_wrap_to_uint8(self):
        master = self.temp / "master_split.csv"
        for label, split in ((256, 0), (0, 256)):
            with self.subTest(label=label, split=split):
                master.write_text(
                    f"chunk_id,row_idx_in_chunk,y,group_id,split_id\n0,0,{label},0,{split}\n"
                )
                with self.assertRaisesRegex(RuntimeError, "invalid (y|split_id)"):
                    prepare_chunk_metadata.process_master_split(master, csv_read_rows=1, force=True)
                self.assertEqual(list((self.temp / "chunk_metadata").glob("*.npy")), [])

    def test_assign_row_splits_rejects_multidimensional_labels(self):
        with self.assertRaisesRegex(ValueError, "one-dimensional"):
            assign_row_splits(np.array([[0], [1]]), seed=42, chunk_id=0)


    def test_master_split_cli_supports_module_and_script_invocation(self):
        root = Path(__file__).resolve().parents[1]
        for entry in (
            ['-m', 'data_pipeline.scripts.data_splitting.check_master_split'],
            ['data_pipeline/scripts/data_splitting/check_master_split.py'],
        ):
            with self.subTest(entry=entry):
                result = subprocess.run([sys.executable, '-B', *entry, '--help'],
                                        cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('--skip-metadata', result.stdout)

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

    def test_small_single_class_chunks_preserve_every_row(self):
        expected = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 0, 1),
                    (3, 0, 1), (4, 0, 1), (5, 1, 0)]
        for label in (0, 1):
            for size, counts in enumerate(expected):
                with self.subTest(label=label, size=size):
                    labels = np.full(size, label, dtype=np.int8)
                    splits = assign_row_splits(labels, seed=42, chunk_id=0)
                    self.assertEqual(len(splits), size)
                    self.assertEqual(tuple(np.bincount(splits, minlength=3)), counts)

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

    def test_epitopes_at_both_window_boundaries_match_exactly(self):
        from data_pipeline.scripts.data_classification.epitope_classification import validate_exact_match
        window = 'ACDEFGHIKLMNPQRSTVWYACDEF'
        self.assertTrue(validate_exact_match(window, 'ACD', 1, 3))
        self.assertTrue(validate_exact_match(window, 'DEF', 23, 25))
        self.assertTrue(validate_exact_match(window, window, 1, 25))

    def test_position_score_is_centered_and_symmetric(self):
        from data_pipeline.scripts.data_classification.epitope_classification import compute_epitope_position_score
        centered = compute_epitope_position_score(1, 25, 10, 16, 25)
        left = compute_epitope_position_score(1, 25, 1, 7, 25)
        right = compute_epitope_position_score(1, 25, 19, 25, 25)
        self.assertEqual(centered, 0)
        self.assertLess(left, 0)
        self.assertAlmostEqual(left, -right)
