import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
from tests.helpers import archive


@unittest.skipUnless(shutil.which('zstd'), 'zstd executable is required for archive checks')
class ArchivingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='archive_test_')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.original = self.root / 'source.txt'
        self.content = b'synthetic archive payload\n' * 20
        self.original.write_bytes(self.content)
        self.target = self.root / 'source.txt.zst'

    def test_round_trip_and_repeated_archival(self):
        record = archive.archive_file(self.original)
        self.assertFalse(self.original.exists())
        self.assertEqual(archive.decompressed_digest(self.target, 'zstd'), record['original_sha256'])
        self.assertEqual(archive.archive_file(self.original), record)

    def test_interruption_during_compression_preserves_original(self):
        with mock.patch.object(archive.subprocess, 'run', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                archive.archive_file(self.original)
        self.assertEqual(self.original.read_bytes(), self.content)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob('*.partial')))

    def test_interruption_after_archive_publication_is_resumable(self):
        with mock.patch.object(archive, 'atomic_json', side_effect=RuntimeError('record interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                archive.archive_file(self.original)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.original.read_bytes(), self.content)
        record = archive.archive_file(self.original)
        self.assertFalse(self.original.exists())
        self.assertEqual(archive.decompressed_digest(self.target, 'zstd'), record['original_sha256'])

    def test_interruption_after_record_before_unlink_is_resumable(self):
        unlink = Path.unlink
        def interrupt(path, *args, **kwargs):
            if path == self.original:
                raise RuntimeError('unlink interrupted')
            return unlink(path, *args, **kwargs)
        with mock.patch.object(Path, 'unlink', new=interrupt):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                archive.archive_file(self.original)
        self.assertTrue((self.root / 'source.txt.archive.json').exists())
        self.assertEqual(self.original.read_bytes(), self.content)
        archive.archive_file(self.original)
        self.assertFalse(self.original.exists())

    def test_source_change_during_compression_is_rejected(self):
        compress = archive.subprocess.run
        def change_source(*args, **kwargs):
            result = compress(*args, **kwargs)
            self.original.write_bytes(self.content + b'changed')
            return result
        with mock.patch.object(archive.subprocess, 'run', side_effect=change_source):
            with self.assertRaisesRegex(ValueError, 'Original changed'):
                archive.archive_file(self.original)
        self.assertEqual(self.original.read_bytes(), self.content + b'changed')
        self.assertFalse(self.target.exists())

    def test_same_size_source_change_after_receipt_preserves_original(self):
        write_receipt = archive.atomic_json
        before = self.original.stat()
        modified = b'x' * len(self.content)

        def change_source(path, record):
            write_receipt(path, record)
            self.original.write_bytes(modified)
            os.utime(self.original, ns=(before.st_atime_ns, before.st_mtime_ns))

        with mock.patch.object(archive, 'atomic_json', side_effect=change_source):
            with self.assertRaisesRegex(ValueError, 'Original changed before removal'):
                archive.archive_file(self.original)
        self.assertEqual(self.original.read_bytes(), modified)
        self.assertTrue(self.target.is_file())
        with self.assertRaisesRegex(ValueError, 'Existing archive differs from original'):
            archive.archive_file(self.original)
        self.assertEqual(self.original.read_bytes(), modified)

    def test_archive_replaced_after_receipt_preserves_original(self):
        write_receipt = archive.atomic_json

        def replace_archive(path, record):
            write_receipt(path, record)
            replacement = self.root / "replacement"
            replacement.write_bytes(b"not a recoverable archive")
            replacement.replace(self.target)

        with mock.patch.object(archive, "atomic_json", side_effect=replace_archive):
            with self.assertRaisesRegex(ValueError, "Archive changed before removal"):
                archive.archive_file(self.original)
        self.assertEqual(self.original.read_bytes(), self.content)

    def test_corrupt_archive_is_rejected_when_original_is_present(self):
        self.target.write_bytes(b'not a zstd archive')
        with self.assertRaisesRegex(RuntimeError, 'decompression failed'):
            archive.archive_file(self.original)
        self.assertEqual(self.original.read_bytes(), self.content)

    def test_checksum_mismatch_is_detected_after_original_removal(self):
        archive.archive_file(self.original)
        data = bytearray(self.target.read_bytes()); data[-1] ^= 1; self.target.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            archive.archive_file(self.original)

    def test_insufficient_space_preserves_original(self):
        with mock.patch.object(archive.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(OSError, 'Insufficient space'):
                archive.archive_file(self.original)
        self.assertEqual(self.original.read_bytes(), self.content)
        self.assertFalse(self.target.exists())

    def test_symlink_is_not_archived(self):
        link = self.root / 'link.txt'; link.symlink_to(self.original)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            archive.archive_file(link)
        self.assertEqual(self.original.read_bytes(), self.content)

    def test_tree_marker_does_not_bypass_archive_checksum_checks(self):
        archive.archive_tree(self.root)
        marker = self.root / 'ARCHIVED.json'
        self.assertTrue(marker.exists())
        data = bytearray(self.target.read_bytes())
        data[-1] ^= 1
        self.target.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            archive.archive_tree(self.root)
