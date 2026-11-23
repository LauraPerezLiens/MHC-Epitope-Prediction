"""Exercise the real LR CLI on synthetic concatenated data and recovery."""
import importlib.util
import json
import subprocess
import sys
import unittest

import numpy as np
import torch

from tests.helpers import PipelineCase, PROJECT, dataset

SCRIPT = PROJECT/'neural_network/logistic_regression/train_natural.py'
spec = importlib.util.spec_from_file_location('logistic_regression_train', SCRIPT)
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)


class LogisticRegressionTests(PipelineCase):
    def test_full_cli_coverage_test_isolation_and_resume(self):
        self.convert()
        scaler_path = self.temp/'scaler.npz'
        dataset.ModalityStandardizer(
            np.zeros(1024, np.float32), np.ones(1024, np.float32),
            np.zeros(768, np.float32), np.ones(768, np.float32),
            np.array(['mixed']), np.array([0], np.int64)).save(scaler_path)
        output = self.temp/'lr'
        cmd = [sys.executable, str(SCRIPT), '--root', str(self.output),
               '--scaler', str(scaler_path), '--output', str(output),
               '--epochs', '2', '--batch-size', '3', '--device', 'cpu',
               '--checkpoint-every', '1', '--log-every', '1']
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        progress = [json.loads(line[line.index('{'):]) for line in result.stdout.splitlines()
                    if line.startswith(('TRAIN chunks=', 'VALIDATION chunks=', 'TEST chunks='))]
        self.assertEqual([item['phase'] for item in progress],
                         ['TRAIN', 'VALIDATION', 'TRAIN', 'VALIDATION', 'TEST'])
        self.assertEqual(progress[0]['metrics']['rows'], 4)
        self.assertIn('f1', progress[0]['metrics'])
        self.assertEqual(progress[0]['metrics_scope'], 'cumulative')
        summary = json.loads((output/'summary.json').read_text())
        self.assertEqual(summary['test']['rows'], 1)
        self.assertEqual(summary['validation']['rows'], 1)
        for epoch in (1, 2):
            record = json.loads((output/f'epoch_{epoch:04d}.json').read_text())
            self.assertEqual(record['train_online']['rows'], 4)
        weights = np.load(output/'coefficients.npz')['weight'].copy()
        resumed = subprocess.run(cmd+['--resume'], capture_output=True, text=True)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        np.testing.assert_array_equal(weights, np.load(output/'coefficients.npz')['weight'])
        refused = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('Output already exists', refused.stderr)
        # Changing only TEST features/labels must not affect fitted coefficients.
        features = np.load(self.output/self.input_x.relative_to(self.root), mmap_mode='r+')
        features[5] *= -1
        features.flush()
        labels_path = (self.output / self.input_x.relative_to(self.root)).parent / "chunk_metadata/chunk_000000_y.npy"
        labels = np.load(labels_path)
        labels[5] = 1 - labels[5]
        np.save(labels_path, labels)
        other = self.temp/'lr_other_test'
        other_cmd = list(cmd)
        other_cmd[other_cmd.index('--output')+1] = str(other)
        result = subprocess.run(other_cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        np.testing.assert_array_equal(weights, np.load(other/'coefficients.npz')['weight'])
        # Extending a completed run and changing reporting intervals is safe.
        extended = list(cmd)
        extended[extended.index('--epochs')+1] = '3'
        extended[extended.index('--log-every')+1] = '10'
        extended[extended.index('--checkpoint-every')+1] = '10'
        result = subprocess.run(extended+['--resume'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((output/'epoch_0003.json').is_file())
        self.assertEqual(json.loads((output/'config.json').read_text())['epochs'], 3)
        result = subprocess.run(extended+['--resume', '--lr', '0.2'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Resume configuration changed', result.stderr)

    def test_metrics_match_known_confusion_and_auc(self):
        metrics = lr.Metrics()
        metrics.update(torch.tensor([-3., -1., 1., 3.]), torch.tensor([0., 1., 0., 1.]), 2.)
        result = metrics.result()
        self.assertEqual([result[k] for k in ('tn','fp','fn','tp')], [1,1,1,1])
        self.assertEqual(result['accuracy'], .5)
        self.assertEqual(result['roc_auc_histogram'], .75)
        self.assertAlmostEqual(result['average_precision_histogram'], 5/6)

    def test_histogram_average_precision_accumulates_across_chunks(self):
        metrics = lr.Metrics()
        with self.assertRaisesRegex(ValueError, "no rows"):
            metrics.result()
        metrics.update(torch.tensor([]), torch.tensor([]), 0.0)
        metrics.update(torch.tensor([0.0002]), torch.tensor([1.]), 1.0)
        self.assertEqual(metrics.result()["average_precision_histogram"], 1.0)
        self.assertIsNone(metrics.result()["roc_auc_histogram"])
        metrics.update(torch.tensor([0.0001]), torch.tensor([0.]), 3.0)
        result = metrics.result()
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["loss"], 2.0)
        # The positive has the higher score, so exact AP is 1. Both scores
        # land in the same bin, which treats them as tied and yields AP 1/2.
        self.assertEqual(result["average_precision_histogram"], 0.5)

    @unittest.skipUnless(torch.cuda.device_count() >= 2, 'Requires multiple CUDA GPUs')
    def test_multi_gpu_cli_and_portable_checkpoint(self):
        self.convert()
        scaler_path = self.temp/'scaler.npz'
        dataset.ModalityStandardizer(
            np.zeros(1024, np.float32), np.ones(1024, np.float32),
            np.zeros(768, np.float32), np.ones(768, np.float32),
            np.array(['mixed']), np.array([0], np.int64)).save(scaler_path)
        output = self.temp/'lr_gpu'
        cmd = [sys.executable, str(SCRIPT), '--root', str(self.output),
               '--scaler', str(scaler_path), '--output', str(output),
               '--epochs', '1', '--batch-size', '4', '--device', 'cuda', '--gpus', '0']
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads((output/'summary.json').read_text())
        self.assertEqual(len(summary['gpu_ids']), torch.cuda.device_count())
        self.assertEqual(summary['test']['rows'], 1)
        record = json.loads((output/'epoch_0001.json').read_text())
        self.assertEqual(record['train_online']['rows'], 4)
        checkpoint = torch.load(output/'best.pt', map_location='cpu', weights_only=False)
        portable = torch.nn.Linear(1792, 1)
        portable.load_state_dict(checkpoint['model'])
        self.assertTrue(torch.isfinite(portable.weight).all())
