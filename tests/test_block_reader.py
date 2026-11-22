import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

from data_pipeline.block_reader import Block, BlockReader, RowRange


class BlockReaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "block.npy"
        self.values = np.arange(60, dtype=">i2").reshape(20, 3)
        np.save(self.path, self.values)
        self.block = Block(10, self.path, self.values.shape, ">i2",
                           hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_index_order_dtype_and_bounds(self):
        other = Block(20, self.path, self.values.shape, ">i2")
        spans = [RowRange(20, 8, 5), RowRange(10, 12, 4)]
        with BlockReader([self.block, other], max_bytes=12, max_open=1) as reader:
            parts = list(reader.batches(spans, 15))
            self.assertTrue(all(part.nbytes <= 12 for part in parts))
            self.assertTrue(all(part.dtype.str == ">i2" for part in parts))
            self.assertTrue(all(not part.flags.writeable for part in parts))
            np.testing.assert_array_equal(np.concatenate(parts),
                                          self.values[[8, 9, 10, 11, 12, 12, 13, 14, 15]])
            self.assertEqual(reader.read(RowRange(10, 20, 0)).shape, (0, 3))
            with self.assertLogs("data_pipeline.block_reader", "ERROR"):
                with self.assertRaisesRegex(ValueError, "max_bytes"):
                    reader.read(RowRange(10, 0, 3))

    def test_resume_from_committed_offset(self):
        with BlockReader([self.block], max_bytes=18) as reader:
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                for first in reader.batches([RowRange(10, 0, 20)], 3):
                    raise RuntimeError("interrupted")
        with BlockReader([self.block], max_open=0) as reader:
            rest = list(reader.batches([RowRange(10, len(first), 20 - len(first))], 3))
            np.testing.assert_array_equal(np.concatenate([first, *rest]), self.values)

    def test_invalid_references_and_duplicate_ids(self):
        with self.assertLogs("data_pipeline.block_reader", "ERROR"):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                BlockReader([self.block, self.block])
            with BlockReader([self.block]) as reader:
                for span in (RowRange(5, 0, 1), RowRange(10, -1, 3),
                             RowRange(10, 19, 2), RowRange(10, 0, -1),
                             RowRange(10, 1.5, 1),
                             RowRange(10, np.int64(1), np.int64(2**63 - 1))):
                    with self.assertRaises(ValueError):
                        reader.read(span)

    def test_integrity(self):
        missing = Block(11, self.path.with_suffix(".missing"), (20, 3), ">i2")
        wrong = Block(12, self.path, (20, 4), ">i2")
        wrong_type = Block(13, self.path, (20, 3), "<i2")
        with BlockReader([self.block, missing, wrong, wrong_type]) as reader:
            reader.validate(10, verify_checksum=True)
            with self.assertLogs("data_pipeline.block_reader", "ERROR"):
                with self.assertRaises(FileNotFoundError):
                    reader.validate(11)
                for block_id in (12, 13):
                    with self.assertRaisesRegex(ValueError, "manifest"):
                        reader.validate(block_id)
                with self.path.open("r+b") as file:
                    file.seek(-1, 2)
                    file.write(b"\xff")
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    reader.validate(10, verify_checksum=True)
                with self.path.open("r+b") as file:
                    file.truncate(self.path.stat().st_size - 1)
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    reader.validate(10)

    def test_oversized_header_is_rejected_before_payload_read(self):
        self.path.write_bytes(np.lib.format.magic(2, 0) + (2**30).to_bytes(4, "little"))
        with BlockReader([self.block]) as reader:
            with self.assertLogs("data_pipeline.block_reader", "ERROR"):
                with self.assertRaisesRegex(ValueError, "oversized"):
                    reader.validate(10)
