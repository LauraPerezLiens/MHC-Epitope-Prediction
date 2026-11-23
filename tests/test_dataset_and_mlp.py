from types import SimpleNamespace
from unittest import mock
import numpy as np
import torch
from tests.helpers import PipelineCase, dataset
from neural_network.MLP.fit_shuffled_scaler import fit_sequential
from mlp_layernorm_shuffled_ladder100_dualeval import MLP, save_checkpoint


class DatasetTests(PipelineCase):
    def test_synthetic_example_rejects_split_swaps_with_identical_counts(self):
        from examples import synthetic_mlp

        root = self.temp / "synthetic"
        synthetic_mlp.generate(root, 42)
        path = next(root.rglob("chunk_000000_split_id.npy"))
        values = np.load(path)
        values[[40, 46]] = values[[46, 40]]
        np.save(path, values)
        with self.assertRaisesRegex(ValueError, "Synthetic split assignment"):
            synthetic_mlp.check(root, 42)

    def test_separate_and_concatenated_loaders_are_exactly_equivalent(self):
        separate = dataset.discover_datasets(self.root)[0]
        rows = np.array([5, 0, 2, 0], dtype=np.int64)
        before = dataset.load_rows(separate, 0, rows, self.groups[rows], 'primary_secondary', {})
        self.convert()
        joined = dataset.discover_datasets(self.output)[0]
        after = dataset.load_rows(joined, 0, rows, self.groups[rows], 'primary_secondary')
        np.testing.assert_array_equal(before, self.expected[rows])
        np.testing.assert_array_equal(after, before)
        np.testing.assert_array_equal(dataset.load_rows(joined, 0, rows, self.groups[rows], 'primary'), self.x[rows])

    def test_scaler_uses_train_occurrences_including_repeated_groups(self):
        datasets = dataset.discover_datasets(self.root)
        scaler = fit_sequential(datasets, block_rows=2, work_dir=self.temp)
        expected_train = self.expected[self.split == dataset.TRAIN]
        expected_mean = expected_train.mean(axis=0, dtype=np.float64)
        expected_scale = expected_train.std(axis=0, dtype=np.float64)
        mean = np.concatenate((scaler.primary_mean, scaler.secondary_mean))
        scale = np.concatenate((scaler.primary_scale, scaler.secondary_scale))
        np.testing.assert_allclose(mean, expected_mean, rtol=1e-6)
        np.testing.assert_allclose(scale, expected_scale, rtol=1e-6)
        path = self.temp / 'scaler.npz'
        scaler.save(path)
        transformed = dataset.ModalityStandardizer.load(path).transform(self.expected.copy())
        np.testing.assert_allclose(transformed, (self.expected - expected_mean) / expected_scale, atol=1e-6)

    def test_incomplete_dataset_is_not_discovered(self):
        (self.root / 'INCOMPLETE').touch()
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            dataset.discover_datasets(self.root)

    def test_mlp_forward_and_optimizer_step_on_cpu(self):
        threads = torch.get_num_threads()
        self.addCleanup(torch.set_num_threads, threads)
        self.addCleanup(torch.set_rng_state, torch.get_rng_state())
        torch.set_num_threads(2)
        torch.manual_seed(42)
        model = MLP(input_dim=1792).cpu()
        train = self.split == dataset.TRAIN
        inputs = torch.from_numpy(self.expected[train])
        labels = torch.from_numpy(self.y[train].astype(np.float32))
        optimizer = torch.optim.AdamW(model.parameters(), lr=.001)
        before = model.network[0].weight.detach().clone()
        logits = model(inputs)
        self.assertEqual(tuple(logits.shape), (int(train.sum()),))
        loss = torch.nn.BCEWithLogitsLoss()(logits, labels)
        self.assertTrue(torch.isfinite(loss).item())
        loss.backward()
        for name, parameter in model.named_parameters():
            self.assertIsNotNone(parameter.grad, name)
            self.assertTrue(torch.isfinite(parameter.grad).all(), name)
        optimizer.step()
        self.assertFalse(torch.equal(before, model.network[0].weight))

        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimizer, T_0=20, T_mult=1, eta_min=.00001)
        scheduler.step(1)
        path = self.temp / 'checkpoint.pt'
        args = SimpleNamespace(features='primary_secondary', dropout=.30, seed=42)
        with mock.patch.object(torch.cuda, 'is_available', return_value=False):
            save_checkpoint(path, model, optimizer, scheduler, args,
                            epoch_index=0, next_chunk_offset=1,
                            epoch_total_chunks=1, completed_epochs=1)
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        self.assertEqual(checkpoint['completed_epochs'], 1)
        self.assertEqual(checkpoint['next_chunk_offset'], 1)
        self.assertEqual(checkpoint['epoch_total_chunks'], 1)
        self.assertEqual(checkpoint['selection_metric'], 'stage_fixed_50_50_test_loss')
        restored = MLP(input_dim=1792).cpu()
        restored_optimizer = torch.optim.AdamW(restored.parameters(), lr=.001)
        restored_scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            restored_optimizer, T_0=20, T_mult=1, eta_min=.00001)
        restored.load_state_dict(checkpoint['model_state_dict'])
        restored_optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        restored_scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        for key, value in model.state_dict().items():
            self.assertTrue(torch.equal(value, restored.state_dict()[key]), key)
        losses = []
        for network, opt, schedule in [(model, optimizer, scheduler),
                                       (restored, restored_optimizer, restored_scheduler)]:
            torch.set_rng_state(checkpoint['torch_rng_state'])
            opt.zero_grad(set_to_none=True)
            next_loss = torch.nn.BCEWithLogitsLoss()(network(inputs), labels)
            self.assertTrue(torch.isfinite(next_loss).item())
            next_loss.backward()
            opt.step()
            schedule.step(2)
            losses.append(next_loss.item())
        self.assertEqual(losses[0], losses[1])
        self.assertEqual(scheduler.state_dict(), restored_scheduler.state_dict())
        for key, value in model.state_dict().items():
            self.assertTrue(torch.equal(value, restored.state_dict()[key]), key)
        original_state = optimizer.state_dict()
        restored_state = restored_optimizer.state_dict()
        self.assertEqual(original_state["param_groups"], restored_state["param_groups"])
        self.assertEqual(original_state["state"].keys(), restored_state["state"].keys())
        for parameter, state in original_state["state"].items():
            self.assertEqual(state.keys(), restored_state["state"][parameter].keys())
            for field, value in state.items():
                torch.testing.assert_close(value, restored_state["state"][parameter][field], rtol=0, atol=0)
