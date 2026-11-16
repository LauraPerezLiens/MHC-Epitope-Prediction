import os
import subprocess
import sys
import numpy as np
import pandas as pd
from tests.helpers import PipelineCase, PROJECT


class PreparationLauncherTests(PipelineCase):
    def setUp(self):
        super().setUp()
        frame = pd.read_csv(self.primary / 'master_index.csv')
        frame['split_id'] = self.split
        frame.to_csv(self.primary / 'master_split.csv', index=False)
        self.scaler = self.temp / 'scaler.npz'

    def launch(self, root=None):
        env = dict(os.environ, DATA_ROOT=str(root or self.root), SCALER_PATH=str(self.scaler),
                   PYTHON=sys.executable, CUDA_VISIBLE_DEVICES='')
        return subprocess.run(['bash', str(PROJECT / 'neural_network/MLP/run_shuffled_pipeline.sh')],
                              env=env, capture_output=True, text=True, timeout=60)

    def snapshot(self):
        return {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file() and not p.name.endswith('.lock')}

    def test_missing_splits_are_reported_and_never_regenerated(self):
        (self.primary / 'master_split.csv').unlink()
        before = self.snapshot()
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing existing master_split.csv', result.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.scaler.exists())

    def test_missing_metadata_is_reported_and_never_recreated(self):
        (self.metadata / 'chunk_000000_y.npy').unlink()
        before = self.snapshot()
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing existing metadata', result.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.scaler.exists())

    def test_invalid_splits_do_not_trigger_scaler_fitting(self):
        frame = pd.read_csv(self.primary / 'master_split.csv')
        frame.loc[0, 'split_id'] = 9
        frame.to_csv(self.primary / 'master_split.csv', index=False)
        before = self.snapshot()
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.scaler.exists())

    def test_missing_scaler_is_fitted_without_changing_preparation(self):
        before = self.snapshot()
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.scaler.exists())
        self.assertEqual(before, self.snapshot())
        scaler_bytes = self.scaler.read_bytes()
        repeated = self.launch()
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertEqual(scaler_bytes, self.scaler.read_bytes())
        self.assertEqual(before, self.snapshot())

    def test_existing_scaler_does_not_hide_missing_metadata(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        (self.metadata / 'chunk_000000_split_id.npy').unlink()
        before = self.snapshot()
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_existing_scaler_allows_valid_concatenated_input(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.convert()
        before = {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        result = self.launch(root=self.output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()})

    def test_concatenated_input_without_scaler_is_not_refitted(self):
        self.convert()
        result = self.launch(root=self.output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires its existing TRAIN scaler', result.stderr)
        self.assertFalse(self.scaler.exists())

    def test_unprepared_additional_dataset_is_not_silently_ignored(self):
        primary = self.root / 'other' / 'classification_other_ProtT5_chunks'
        primary.mkdir(parents=True)
        np.save(primary / 'chunk_000000_X.npy', self.x)
        before = self.snapshot()
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing existing metadata for feature directory', result.stderr)
        self.assertFalse(self.scaler.exists())
        self.assertEqual(before, self.snapshot())
