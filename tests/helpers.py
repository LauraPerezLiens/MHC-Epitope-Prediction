"""Small, separate-modality inputs shared by CPU regression tests."""
from contextlib import redirect_stdout
import csv
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'neural_network' / 'MLP'))
import dataset
from data_pipeline.scripts.embedding_concatenation import concatenate_primary_secondary as concat
from data_pipeline.scripts.data_archiving import archive_inputs as archive


class PipelineCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='pipeline_test_')
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        self.root = self.temp / 'input'
        self.output = self.temp / 'output'
        self.primary = self.root / 'mixed' / 'classification_mixed_ProtT5_chunks'
        self.secondary = self.root / 'mixed' / 'classification_mixed_SecondaryBERT_by_group'
        self.metadata = self.primary / 'chunk_metadata'
        self.metadata.mkdir(parents=True)
        self.secondary.mkdir()
        self.groups = np.array([20, 10, 20, 30, 10, 30], dtype=np.int64)
        self.y = np.array([0, 1, 0, 1, 0, 1], dtype=np.int8)
        self.split = np.array([0, 0, 0, 0, 1, 2], dtype=np.uint8)
        self.x = np.arange(6 * 1024, dtype=np.float32).reshape(6, 1024) / 100
        self.ss = np.arange(3 * 768, dtype=np.float32).reshape(3, 768) / 100
        self.input_x = self.primary / 'chunk_000000_X.npy'
        np.save(self.input_x, self.x)
        np.save(self.secondary / 'group_id.npy', np.array([10, 20, 30], dtype=np.int64))
        np.save(self.secondary / 'ss.npy', self.ss)
        for suffix, values in [('y', self.y), ('group_id', self.groups), ('split_id', self.split)]:
            np.save(self.metadata / f'chunk_000000_{suffix}.npy', values)
        with (self.secondary / 'chunks_manifest.csv').open('w') as handle:
            handle.write('chunk_id,start,end,x_file\n0,0,3,ss.npy\n')
        with (self.primary / 'master_index.csv').open('w') as handle:
            writer = csv.writer(handle)
            writer.writerow(['chunk_id', 'row_idx_in_chunk', 'y', 'group_id', 'protein_group_id'])
            writer.writerows((0, row, int(y), int(group), int(group // 10))
                             for row, (y, group) in enumerate(zip(self.y, self.groups)))
        self.expected = np.concatenate((self.x, self.ss[[1, 0, 1, 2, 0, 2]]), axis=1)

    def convert(self):
        args = SimpleNamespace(root=self.root, output=self.output, archive_sources=False,
                               archive_originals=None, secondary_cache_dir=None, workers=1,
                               archive_threads=1, zstd='zstd', start_chunk=0,
                               max_chunks=None, block_rows=2)
        with redirect_stdout(io.StringIO()):
            concat.run_fast(args)
        return self.output / self.input_x.relative_to(self.root)
