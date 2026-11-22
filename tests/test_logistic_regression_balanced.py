"""Balanced LR must use the same sampler and evaluation engine as MLP."""
import json
import shutil
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np
import torch

from tests.helpers import PipelineCase, PROJECT, dataset
from mlp_layernorm_shuffled_ladder100_dualeval import (
    LogisticRegression, build_chunk_jobs, iter_balanced_chunk_batches,
)

SCRIPT = PROJECT/'neural_network/logistic_regression/train.py'


class BalancedLogisticRegressionTests(PipelineCase):
    def prepare(self, chunks=1):
        features = self.convert()
        metadata = features.parent/'chunk_metadata'
        np.save(metadata/'chunk_000000_y.npy', np.array([0, 1, 0, 0, 0, 1], np.int8))
        np.save(metadata/'chunk_000000_split_id.npy', np.array([0, 0, 0, 0, 2, 2], np.uint8))
        for cid in range(1, chunks):
            shutil.copyfile(features, features.with_name(f'chunk_{cid:06d}_X.npy'))
            for suffix in ('y', 'group_id', 'split_id'):
                shutil.copyfile(metadata/f'chunk_000000_{suffix}.npy',
                                metadata/f'chunk_{cid:06d}_{suffix}.npy')
        scaler = self.temp/'scaler.npz'
        dataset.ModalityStandardizer(
            np.zeros(1024, np.float32), np.ones(1024, np.float32),
            np.zeros(768, np.float32), np.ones(768, np.float32),
            np.array(['mixed']*chunks), np.arange(chunks)).save(scaler)
        return scaler

    def test_sampler_covers_source_rows_and_is_exactly_balanced(self):
        self.prepare()
        datasets = dataset.discover_datasets(self.output)
        jobs = build_chunk_jobs(datasets)
        batches = list(iter_balanced_chunk_batches(
            datasets[0], 0, dataset.TRAIN, 'primary_secondary', 4,
            42, 0, 0, 1, {}, datasets, jobs))
        self.assertEqual(len(batches), 2)
        seen = []
        for x, y in batches:
            self.assertEqual(int(y.sum()), 2)
            self.assertEqual(len(y), 4)
            seen.extend(x[:, 0])
        for row in range(4):
            self.assertIn(self.x[row, 0], seen)
        model = LogisticRegression(1792)
        self.assertEqual(sum(p.numel() for p in model.parameters()), 1793)
        self.assertEqual(sum(isinstance(m, torch.nn.Linear) for m in model.modules()), 1)
        self.assertEqual(tuple(model(torch.zeros(4, 1792)).shape), (4,))

    def test_cli_ten_chunk_reports_balanced_eval_and_resume(self):
        scaler = self.prepare(chunks=11)
        out = self.temp/'balanced_run'
        cmd = [sys.executable, str(SCRIPT), '--root', str(self.output),
               '--scaler', str(scaler), '--output', str(out), '--device', 'cpu',
               '--epochs', '2', '--batch-size', '8', '--eval-target-per-class', '22']
        # The shared engine uses CUDA if visible; this subprocess is CPU-only.
        import os
        env = dict(os.environ, CUDA_VISIBLE_DEVICES='', WORLD_SIZE='1')
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr+'\n'+result.stdout)
        records = [json.loads(line) for line in (out/'monitor_history.jsonl').read_text().splitlines()]
        self.assertEqual([(r['epoch'], r['chunk_offset']) for r in records],
                         [(1, 10), (1, 11), (2, 10), (2, 11)])
        for record in records:
            for key in ('train_online', 'train_eval_stage', 'test_eval_stage',
                        'train_eval_all', 'test_eval_all'):
                m = record[key]
                self.assertEqual(m['tp']+m['fn'], m['tn']+m['fp'])
        state = torch.load(out/'last_lr_primary_secondary.pt', map_location='cpu', weights_only=False)
        self.assertEqual(state['model_type'], 'logistic')
        self.assertEqual(state['selection_metric'], 'stage_fixed_50_50_test_loss')
        self.assertEqual(state['completed_epochs'], 2)
        self.assertEqual(state['optimizer_state_dict']['param_groups'][0]['weight_decay'], .0001)
        self.assertEqual(state['scheduler_state_dict']['T_0'], 20)
        self.assertEqual(tuple(state['model_state_dict']['network.0.weight'].shape), (1, 1792))
        cmd[cmd.index('--epochs')+1] = '3'
        resumed = subprocess.run(cmd+['--resume'], capture_output=True, text=True, env=env)
        self.assertEqual(resumed.returncode, 0, resumed.stderr+'\n'+resumed.stdout)
        state = torch.load(out/'last_lr_primary_secondary.pt', map_location='cpu', weights_only=False)
        self.assertEqual(state['completed_epochs'], 3)
        refused = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('Output already exists', refused.stderr)

    def test_single_class_chunk_uses_train_donor(self):
        self.prepare(chunks=2)
        datasets = dataset.discover_datasets(self.output)
        meta = Path(datasets[0]['metadata_path'])
        np.save(meta/'chunk_000000_y.npy', np.array([0, 0, 0, 0, 0, 1], np.int8))
        jobs = build_chunk_jobs(datasets)
        batches = list(iter_balanced_chunk_batches(
            datasets[0], 0, dataset.TRAIN, 'primary_secondary', 4,
            42, 0, 0, 1, {}, datasets, jobs))
        self.assertEqual(len(batches), 2)
        for _, y in batches:
            self.assertEqual(list(sorted(y)), [0, 0, 1, 1])

    @unittest.skipUnless(torch.cuda.is_available(), 'Requires a CUDA GPU')
    def test_single_gpu_cli(self):
        scaler = self.prepare()
        out = self.temp/'gpu'
        result = subprocess.run(
            [sys.executable, str(SCRIPT), '--root', str(self.output),
             '--scaler', str(scaler), '--output', str(out), '--epochs', '1',
             '--batch-size', '4', '--device', 'cuda', '--eval-target-per-class', '2'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr+'\n'+result.stdout)
        state = torch.load(out/'last_lr_primary_secondary.pt', map_location='cpu', weights_only=False)
        self.assertEqual(state['model_type'], 'logistic')
        self.assertTrue(torch.isfinite(state['model_state_dict']['network.0.weight']).all())
