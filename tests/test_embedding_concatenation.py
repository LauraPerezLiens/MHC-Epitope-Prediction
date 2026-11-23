import fcntl
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock
import numpy as np
from tests.helpers import PipelineCase, archive, concat, dataset


class ConcatenationTests(PipelineCase):
    def test_repeated_nonconsecutive_groups_and_independent_metadata(self):
        output = self.convert()
        np.testing.assert_array_equal(np.load(output), self.expected)
        concat.verify_completed_output(self.output)
        self.assertFalse((self.output / 'INCOMPLETE').exists())
        np.save(self.metadata / 'chunk_000000_y.npy', 1 - self.y)
        copied = output.parent / 'chunk_metadata/chunk_000000_y.npy'
        np.testing.assert_array_equal(np.load(copied), self.y)

    def test_fast_concatenation_preserves_rows_across_block_sizes_and_memory_order(self):
        primary = self.x.copy(order="F")
        np.save(self.input_x, primary)
        store = dataset.SecondaryBERTStore(self.secondary)
        for block_rows in (1, 4, 10):
            with self.subTest(block_rows=block_rows):
                output = self.temp / f"joined-{block_rows}.npy"
                concat.concatenate_chunk_fast(self.input_x, self.groups, store, output, block_rows, lambda _: None)
                combined = np.load(output)
                self.assertEqual(combined.shape, (6, 1792))
                self.assertEqual(combined.dtype, np.dtype("<f4"))
                np.testing.assert_array_equal(combined[:, :1024], primary)
                np.testing.assert_array_equal(combined[:, 1024:], self.ss[[1, 0, 1, 2, 0, 2]])

    def test_primary_vectors_follow_positions_when_only_payload_rows_are_swapped(self):
        primary = self.x.copy()
        primary[[0, 1]] = primary[[1, 0]]
        np.save(self.input_x, primary)
        output = self.convert()
        combined = np.load(output)
        np.testing.assert_array_equal(combined[:, :1024], primary)
        np.testing.assert_array_equal(combined[:, 1024:], self.expected[:, 1024:])
        np.testing.assert_array_equal(np.load(output.parent / "chunk_metadata/chunk_000000_y.npy"), self.y)
        concat.verify_completed_output(self.output)

    def test_swapped_group_metadata_cannot_swap_secondary_vectors(self):
        gids = self.groups.copy()
        gids[[0, 1]] = gids[[1, 0]]
        np.save(self.metadata / 'chunk_000000_group_id.npy', gids)
        with self.assertRaisesRegex(ValueError, 'group_id.*source index'):
            self.convert()
        self.assertFalse(list(self.output.rglob('chunk_*_X.npy')))

    def test_swapped_labels_and_split_codes_are_rejected(self):
        master = self.primary / 'master_index.csv'
        lines = master.read_text().splitlines()
        split_csv = master.with_name('master_split.csv')
        split_csv.write_text(lines[0] + ',split_id\n' + ''.join(
            f'{line},{code}\n' for line, code in zip(lines[1:], self.split, strict=True)))
        for name, original, positions in (
            ('y', self.y, [0, 1]), ('split_id', self.split, [0, 4]),
        ):
            with self.subTest(field=name):
                changed = original.copy()
                changed[positions] = changed[positions[::-1]]
                path = self.metadata / f'chunk_000000_{name}.npy'
                np.save(path, changed)
                with self.assertRaisesRegex(ValueError, f'{name}.*source index'):
                    self.convert()
                self.assertFalse(list(self.output.rglob('chunk_*_X.npy')))
                np.save(path, original)

    def test_nonfinite_features_are_rejected_in_either_modality(self):
        for path, original, invalid in (
            (self.input_x, self.x, np.nan),
            (self.secondary / 'ss.npy', self.ss, np.inf),
        ):
            with self.subTest(path=path):
                modified = original.copy()
                modified[0, 0] = invalid
                np.save(path, modified)
                with self.assertRaisesRegex(ValueError, 'Nonfinite'):
                    self.convert()
                self.assertFalse(list(self.output.rglob('chunk_*_X.npy')))
                np.save(path, original)

    def test_missing_group_does_not_publish_output(self):
        gids = self.groups.copy(); gids[0] = 99
        np.save(self.metadata / 'chunk_000000_group_id.npy', gids)
        master = self.primary / 'master_index.csv'
        header, row, tail = master.read_text().split("\n", 2)
        fields = row.split(",")
        fields[header.split(",").index("group_id")] = "99"
        master.write_text(f"{header}\n{','.join(fields)}\n{tail}")
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

    def test_completed_shortcut_should_detect_corrupt_features(self):
        output = self.convert()
        values = np.load(output, mmap_mode='r+'); values[0, 0] += 1; values.flush(); del values
        with self.assertRaises(ValueError):
            self.convert()

    def test_completed_verification_should_detect_changed_label_content(self):
        output = self.convert()
        path = output.parent / 'chunk_metadata/chunk_000000_y.npy'
        np.save(path, 1 - self.y)
        with self.assertRaises(ValueError):
            concat.verify_completed_output(self.output)

    def test_all_metadata_arrays_are_checksummed_and_verified(self):
        output = self.convert()
        record = json.loads(output.with_suffix('.json').read_text())
        self.assertEqual(set(record['metadata_sha256']), {'y', 'group_id', 'split_id'})
        for suffix in ('y', 'group_id', 'split_id'):
            with self.subTest(suffix=suffix):
                path = output.parent / 'chunk_metadata' / f'chunk_000000_{suffix}.npy'
                original = path.read_bytes()
                self.assertEqual(concat.file_digest(path), record['metadata_sha256'][suffix])
                values = np.load(path).copy()
                values[0] = (int(values[0]) + 1) % 3
                np.save(path, values)
                with self.assertRaisesRegex(ValueError, 'Metadata checksum mismatch'):
                    self.convert()
                path.write_bytes(original)

    def test_new_metadata_records_are_independent_of_source_files(self):
        self.convert()
        for source in self.metadata.glob('*.npy'):
            source.unlink()
        concat.verify_completed_output(self.output)
        self.convert()

    def test_verification_does_not_modify_output_files(self):
        self.convert()
        before = {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        concat.verify_completed_output(self.output)
        self.assertEqual(before, {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()})

    def legacy_marker(self, output):
        marker = output.with_suffix('.json')
        record = json.loads(marker.read_text())
        del record['metadata_sha256']
        record.pop('output_mtime_ns', None)
        marker.write_text(json.dumps(record))

    def test_legacy_records_verify_against_source_metadata(self):
        output = self.convert()
        self.legacy_marker(output)
        concat.verify_completed_output(self.output)
        path = output.parent / 'chunk_metadata/chunk_000000_y.npy'
        np.save(path, 1 - self.y)
        with self.assertRaisesRegex(ValueError, 'Metadata checksum mismatch'):
            concat.verify_completed_output(self.output)

    @unittest.skipUnless(shutil.which('zstd'), 'zstd is required for legacy archive checks')
    def test_legacy_records_verify_against_archived_metadata(self):
        output = self.convert()
        self.legacy_marker(output)
        for path in self.metadata.glob('*.npy'):
            archive.archive_file(path)
        concat.verify_completed_output(self.output)
        self.convert()
        path = output.parent / 'chunk_metadata/chunk_000000_y.npy'
        np.save(path, 1 - self.y)
        with self.assertRaisesRegex(ValueError, 'Metadata checksum mismatch'):
            concat.verify_completed_output(self.output)

    def test_missing_legacy_evidence_is_not_treated_as_verified(self):
        output = self.convert()
        self.legacy_marker(output)
        for path in self.metadata.glob('*.npy'):
            path.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing recorded metadata checksum'):
            concat.verify_completed_output(self.output)

    def test_incomplete_checksum_record_is_rejected(self):
        output = self.convert()
        marker = output.with_suffix('.json')
        record = json.loads(marker.read_text())
        del record['metadata_sha256']['y']
        marker.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'Missing recorded metadata checksum'):
            concat.verify_completed_output(self.output)

    def test_legacy_output_cannot_serve_as_its_own_source_evidence(self):
        output = self.convert()
        self.legacy_marker(output)
        layout_path = self.output / 'feature_layout.json'
        layout = json.loads(layout_path.read_text())
        layout['source_root'] = str(self.output)
        layout_path.write_text(json.dumps(layout))
        with self.assertRaisesRegex(ValueError, 'Missing recorded metadata checksum'):
            concat.verify_completed_output(self.output)

    def test_quick_check_does_not_hash_unchanged_feature_payloads(self):
        output = self.convert()
        hashed = []
        digest = concat.file_digest
        def track(path):
            hashed.append(path)
            return digest(path)
        with mock.patch.object(concat, 'file_digest', side_effect=track):
            self.convert()
        self.assertNotIn(output, hashed)
        self.assertEqual(len(hashed), 3)  # Every metadata array is still hashed.

    def test_full_mode_detects_same_size_corruption_with_preserved_mtime(self):
        output = self.convert()
        stat = output.stat()
        values = np.load(output, mmap_mode='r+')
        values[0, 0] += 1
        values.flush()
        del values
        os.utime(output, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        # Quick checks deliberately do not claim cryptographic feature integrity.
        concat.verify_completed_output(self.output, full=False)
        with self.assertRaisesRegex(ValueError, 'Corrupt completed output'):
            concat.verify_completed_output(self.output)

    def test_verify_only_cli_is_read_only_and_does_not_require_sources(self):
        self.convert()
        for path in self.metadata.glob('*.npy'):
            path.unlink()
        before = {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        result = subprocess.run([sys.executable, concat.__file__, '--verify-only',
                                 '--output', str(self.output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('SHA-256 verification passed', result.stdout)
        self.assertEqual(before, {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()})

    def test_verify_only_rejects_archival_before_any_write(self):
        result = subprocess.run([sys.executable, concat.__file__, '--verify-only',
                                 '--output', str(self.output), '--archive-sources'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('without conversion or archival', result.stderr)
        self.assertFalse(self.output.exists())

    def test_verify_only_respects_an_active_writer(self):
        self.convert()
        with (self.output / '.writer.lock').open('rb') as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run([sys.executable, concat.__file__, '--verify-only',
                                     '--output', str(self.output)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Verification failed:', result.stderr)

    def test_quick_check_rejects_missing_feature_checksum(self):
        output = self.convert()
        marker = output.with_suffix('.json')
        record = json.loads(marker.read_text())
        del record['sha256']
        marker.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'Missing recorded feature checksum'):
            concat.verify_completed_output(self.output, full=False)

    def test_verify_only_corruption_returns_a_clear_error_without_writes(self):
        output = self.convert()
        values = np.load(output, mmap_mode='r+')
        values[0, 0] += 1
        values.flush()
        del values
        before = {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        result = subprocess.run([sys.executable, concat.__file__, '--verify-only',
                                 '--output', str(self.output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Verification failed: Corrupt completed output', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(before, {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()})

    def test_verify_only_without_lock_refuses_before_payload_reads(self):
        self.convert()
        (self.output / '.writer.lock').unlink()
        before = {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        args = [concat.__file__, '--verify-only', '--output', str(self.output)]
        with mock.patch.object(sys, 'argv', args), mock.patch.object(concat, 'verify_completed_output') as verify:
            with self.assertRaises(SystemExit) as exit_code:
                concat.main()
        self.assertEqual(exit_code.exception.code, 1)
        verify.assert_not_called()
        self.assertFalse((self.output / '.writer.lock').exists())
        self.assertEqual(before, {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()})

    def test_missing_lock_cannot_bypass_a_new_incompatible_writer(self):
        self.convert()
        lock_path = self.output / '.writer.lock'
        lock_path.unlink()
        with lock_path.open('a') as writer:
            fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run([sys.executable, concat.__file__, '--verify-only',
                                     '--output', str(self.output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Verification failed:', result.stderr)
        self.assertNotIn('verification passed', result.stdout)
