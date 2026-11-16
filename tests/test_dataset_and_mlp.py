import numpy as np
import torch
from tests.helpers import PipelineCase, dataset
from neural_network.MLP.fit_shuffled_scaler import fit_sequential
from mlp_layernorm_shuffled_ladder100_dualeval import MLP


class DatasetTests(PipelineCase):
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
        torch.set_num_threads(2)
        torch.manual_seed(42)
        model = MLP(input_dim=1792).cpu()
        inputs = torch.from_numpy(self.expected.copy())
        labels = torch.from_numpy(self.y.astype(np.float32))
        optimizer = torch.optim.AdamW(model.parameters(), lr=.001)
        before = model.network[0].weight.detach().clone()
        logits = model(inputs)
        self.assertEqual(tuple(logits.shape), (6,))
        loss = torch.nn.BCEWithLogitsLoss()(logits, labels)
        self.assertTrue(torch.isfinite(loss).item())
        loss.backward()
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None))
        optimizer.step()
        self.assertFalse(torch.equal(before, model.network[0].weight))
