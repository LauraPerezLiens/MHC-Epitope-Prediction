"""Durability and identity checks using synthetic embeddings."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pyarrow as pa

from data_pipeline.scripts.embeddings.primary_structure.prott5_v2 import Store, input_sequence


class StubEncoder:
    def __init__(self):
        self.calls = []

    def embed(self, keys):
        self.calls.extend(keys)
        return np.asarray([[ord(key[0])] * 1024 for key in keys], dtype=np.float32), 0, 0


class ProtT5StoreTest(unittest.TestCase):
    def test_resume_and_detect_modified_committed_bytes(self):
        keys = pa.chunked_array([["A" * 25, "C" * 25, "E" * 25, "F" * 25, "G" * 25]])
        cfg = {"batch_size": 2}
        encoder = StubEncoder()
        # This temporary fixture is synthetic, with no project data or real embeddings.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = Store(root, keys, range(5), cfg)
            try:
                self.assertEqual(first.generate(encoder, 1), 2)
                self.assertEqual(first.verify(), 2)
            finally:
                first.close()
            second = Store(root, keys, range(5), cfg)
            try:
                self.assertEqual(second.generate(encoder, 0), 3)
                self.assertEqual(second.generate(encoder, 0), 0)
                self.assertEqual(encoder.calls, keys.to_pylist())
                self.assertEqual(second.verify(), 5)
                _, values = second.matrix(0, 5, create=True)
                values[0, 0] += 1
                values.flush()
                with self.assertRaisesRegex(ValueError, "Committed batch corrupt"):
                    second.verify()
            finally:
                second.close()

    def test_explicit_transform_does_not_define_original_identity(self):
        self.assertEqual(input_sequence("U" + "A" * 24), input_sequence("X" + "A" * 24))
        for sequence in ("J" * 25, "A" * 24, "a" * 25):
            with self.assertRaises(ValueError):
                input_sequence(sequence)


if __name__ == "__main__":
    unittest.main()
