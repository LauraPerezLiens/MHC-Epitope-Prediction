import fcntl
import json
from unittest import expectedFailure, mock
import numpy as np
from tests.helpers import PipelineCase, concat, dataset


class ConcatenationTests(PipelineCase):
    def test_repeated_nonconsecutive_groups_and_independent_metadata(self):
        output = self.convert()
        np.testing.assert_array_equal(np.load(output), self.expected)
        concat.verify_completed_output(self.output)
        self.assertFalse((self.output / 'INCOMPLETE').exists())
        np.save(self.metadata / 'chunk_000000_y.npy', 1 - self.y)
        copied = output.parent / 'chunk_metadata/chunk_000000_y.npy'
        np.testing.assert_array_equal(np.load(copied), self.y)

    def test_missing_group_does_not_publish_output(self):
        gids = self.groups.copy(); gids[0] = 99
        np.save(self.metadata / 'chunk_000000_group_id.npy', gids)
        with self.assertRaisesRegex(KeyError, 'absent'):
            self.convert()
        self.assertFalse((self.output / 'feature_layout.json').exists())
        self.assertFalse(list(self.output.rglob('chunk_*_X.npy')))
        self.assertTrue((self.output / 'INCOMPLETE').exists())
        self.assertTrue(self.input_x.exists())

    def test_incorrect_dimensions_are_rejected(self):
        np.save(self.input_x, self.x[:, :-1])
        with self.assertRaises(ValueError):
            self.convert()
        self.assertFalse(list(self.output.rglob('chunk_*_X.npy')))

    def test_metadata_row_count_mismatch_is_rejected(self):
        np.save(self.metadata / 'chunk_000000_y.npy', self.y[:-1])
        with self.assertRaisesRegex(ValueError, 'Inconsistent metadata'):
            self.convert()
        self.assertFalse(list(self.output.rglob('chunk_*_X.npy')))

    def test_interruption_before_publication_preserves_source_and_retries(self):
        store = dataset.SecondaryBERTStore(self.secondary)
        output = self.temp / 'joined.npy'
        def interrupt(_):
            raise RuntimeError('injected interruption')
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            concat.concatenate_chunk(self.input_x, self.groups, store, output, 2, interrupt)
        self.assertFalse(output.exists())
        np.testing.assert_array_equal(np.load(self.input_x), self.x)
        concat.concatenate_chunk(self.input_x, self.groups, store, output, 2)
        np.testing.assert_array_equal(np.load(output), self.expected)

    def test_resume_after_chunk_publication_does_not_duplicate_rows(self):
        write_marker = concat.write_marker
        def interrupt_layout(path, record):
            if path.name == 'feature_layout.json':
                raise RuntimeError('interrupted before final layout')
            return write_marker(path, record)
        with mock.patch.object(concat, 'write_marker', side_effect=interrupt_layout):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                self.convert()
        self.assertTrue((self.output / 'INCOMPLETE').exists())
        output = self.convert()
        np.testing.assert_array_equal(np.load(output), self.expected)
        self.assertEqual(json.loads((self.output / 'feature_layout.json').read_text())['rows'], 6)
        self.assertEqual(len(list(self.output.rglob('chunk_*_X.npy'))), 1)

    def test_feature_checksum_corruption_is_detected(self):
        output = self.convert()
        values = np.load(output, mmap_mode='r+'); values[0, 0] += 1; values.flush(); del values
        with self.assertRaisesRegex(ValueError, 'Corrupt completed output'):
            concat.verify_completed_output(self.output)

    def test_second_writer_is_rejected(self):
        self.output.mkdir()
        with (self.output / '.writer.lock').open('a') as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.convert()
        self.assertTrue(self.input_x.exists())

    @expectedFailure
    def test_completed_shortcut_should_detect_corrupt_features(self):
        """Known gap: run_fast skips hashing completed output without archival."""
        output = self.convert()
        values = np.load(output, mmap_mode='r+'); values[0, 0] += 1; values.flush(); del values
        with self.assertRaises(ValueError):
            self.convert()

    @expectedFailure
    def test_completed_verification_should_detect_changed_label_content(self):
        """Known gap: completed metadata validation checks shape, not content."""
        output = self.convert()
        path = output.parent / 'chunk_metadata/chunk_000000_y.npy'
        np.save(path, 1 - self.y)
        with self.assertRaises(ValueError):
            concat.verify_completed_output(self.output)
