"""Balanced LR must use the same sampler and evaluation engine as MLP."""
from argparse import Namespace
import json
import shutil
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import torch

from tests.helpers import PipelineCase, PROJECT, dataset
from mlp_layernorm_shuffled_ladder100_dualeval import (
    DiskBinaryMetrics, LogisticRegression, StreamingBinaryMetrics, build_chunk_jobs,
    build_monitor_cache, iter_balanced_chunk_batches,
)

SCRIPT = PROJECT/'neural_network/logistic_regression/train.py'


class SharedBinaryMetricsTests(unittest.TestCase):
    def test_loss_weights_observations_and_confusion_uses_zero_logit(self):
        metrics = StreamingBinaryMetrics()
        metrics.update_arrays(np.array([0.0]), np.array([0], dtype=np.uint8), 1.0)
        metrics.update_arrays(np.array([-1.0, 2.0, -2.0]), np.array([0, 1, 1], dtype=np.uint8), 9.0)
        result = metrics.compute()
        for key, expected in {
            "n": 4, "loss": 2.5, "tp": 1, "tn": 1, "fp": 1, "fn": 1,
            "accuracy": 0.5, "balanced_accuracy": 0.5, "precision": 0.5,
            "recall": 0.5, "f1": 0.5, "roc_auc": 0.5,
        }.items():
            with self.subTest(metric=key):
                self.assertEqual(result[key], expected)

    def test_global_auc_includes_cross_chunk_pairs_and_signed_zero_ties(self):
        chunks = (
            (torch.tensor([0.0, 1.0]), torch.tensor([0.0, 1.0])),
            (torch.tensor([-1.0, -0.0]), torch.tensor([0.0, 1.0])),
        )
        global_metrics = StreamingBinaryMetrics()
        per_chunk = []
        with TemporaryDirectory() as tmp:
            disk = DiskBinaryMetrics(directory=tmp)
            try:
                for logits, labels in chunks:
                    local = StreamingBinaryMetrics()
                    local.update(logits, labels, 2.0)
                    per_chunk.append(local.roc_auc())
                    global_metrics.merge(local)
                    disk.update(logits, labels, 2.0)
                self.assertEqual(np.mean(per_chunk), 1.0)
                self.assertEqual(global_metrics.roc_auc(), 0.875)
                self.assertEqual(disk.roc_auc(), 0.875)
            finally:
                disk.close(remove=True)

    def test_single_class_without_predicted_positives_marks_undefined_metrics(self):
        metrics = StreamingBinaryMetrics()
        metrics.update_arrays(np.array([-1.0, -2.0]), np.zeros(2, dtype=np.uint8), 0.4)
        result = metrics.compute()
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["accuracy"], 1.0)
        for key in ("roc_auc", "precision", "recall", "balanced_accuracy"):
            self.assertTrue(np.isnan(result[key]), key)


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

    def test_historical_test_monitor_is_fixed_and_balanced_without_replacement(self):
        scaler = self.prepare(chunks=2)
        datasets = dataset.discover_datasets(self.output)
        jobs = build_chunk_jobs(datasets)
        manifests = []
        for name in ("monitor_a", "monitor_b"):
            root = self.temp / name
            root.mkdir()
            args = Namespace(eval_target_per_class=2, seed=42, output_dir=root,
                             features="primary_secondary", scaler_path=scaler, secondary_cache_size=1)
            cache = build_monitor_cache(datasets, jobs, dataset.TEST, args,
                                        dataset.ModalityStandardizer.load(scaler))
            manifest = json.loads((root / "monitor_rows_split_2.json").read_text())
            manifests.append(manifest)
            labels = []
            for job, entry in zip(jobs, manifest, strict=True):
                rows = entry["rows"]
                self.assertEqual(len(rows), len(set(rows)))
                meta = dataset.load_chunk_metadata(datasets[job.dataset_index], job.chunk_id)
                self.assertTrue(np.all(meta["split_id"][rows] == dataset.TEST))
                labels.extend(meta["y"][rows])
            self.assertEqual(np.bincount(labels).tolist(), [2, 2])
            self.assertEqual(json.loads(cache.with_suffix(".ready.json").read_text())["n"], 4)
        self.assertEqual(*manifests)

    def test_sampler_covers_source_rows_and_is_exactly_balanced(self):
        self.prepare()
        datasets = dataset.discover_datasets(self.output)
        jobs = build_chunk_jobs(datasets)
        batches = list(iter_balanced_chunk_batches(
            datasets[0], 0, dataset.TRAIN, 'primary_secondary', 4,
            42, 0, 0, 1, {}, datasets, jobs))
        self.assertEqual(len(batches), 2)
        expected_labels = dict(zip(self.x[:4, 0], (0, 1, 0, 0)))
        seen = set()
        for x, y in batches:
            self.assertEqual(int(y.sum()), 2)
            self.assertEqual(len(y), 4)
            for feature, label in zip(x[:, 0], y, strict=True):
                self.assertIn(feature, expected_labels)
                self.assertEqual(label, expected_labels[feature])
                seen.add(feature)
        self.assertEqual(seen, expected_labels.keys())
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
