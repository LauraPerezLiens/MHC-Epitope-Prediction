from contextlib import redirect_stdout
import io
from unittest import mock

import numpy as np
import pandas as pd

from tests.helpers import PipelineCase
from neural_network.MLP import check_preparation as preparation
from neural_network.MLP.fit_shuffled_scaler import fit_sequential


class PreparationValidationTests(PipelineCase):
    def setUp(self):
        super().setUp()
        frame = pd.read_csv(self.primary / 'master_index.csv')
        frame['split_id'] = self.split
        frame.to_csv(self.primary / 'master_split.csv', index=False)
        self.scaler = self.temp / 'scaler.npz'

    def existing_scaler(self):
        with redirect_stdout(io.StringIO()):
            scaler = fit_sequential(preparation.discover_datasets(self.root), block_rows=2, work_dir=self.temp)
        scaler.save(self.scaler)

    def test_existing_scaler_skips_full_csv_comparison(self):
        self.existing_scaler()
        with mock.patch.object(preparation, 'validate_dataset') as exhaustive:
            self.assertEqual(preparation.validate_preparation(self.root, self.scaler), 1)
        exhaustive.assert_not_called()

    def test_explicit_csv_check_still_compares_all_source_rows(self):
        self.existing_scaler()
        with mock.patch.object(preparation, 'validate_dataset', wraps=preparation.validate_dataset) as exhaustive:
            preparation.validate_preparation(self.root, self.scaler, check_source_csv=True)
        exhaustive.assert_called_once_with(self.primary / 'master_split.csv')

    def test_missing_scaler_requires_full_csv_validation(self):
        with mock.patch.object(preparation, 'validate_dataset', wraps=preparation.validate_dataset) as exhaustive:
            preparation.validate_preparation(self.root, self.scaler)
        exhaustive.assert_called_once_with(self.primary / 'master_split.csv')
        self.assertFalse(self.scaler.exists())  # The validator never fits it itself.

    def test_default_mode_checks_all_metadata_values_not_just_a_sample(self):
        self.existing_scaler()
        values = self.split.copy()
        values[-1] = 9
        np.save(self.metadata / 'chunk_000000_split_id.npy', values)
        with self.assertRaisesRegex(ValueError, 'Invalid labels, groups or split IDs'):
            preparation.validate_preparation(self.root, self.scaler)

    def test_missing_split_csv_is_rejected_even_with_scaler(self):
        self.existing_scaler()
        (self.primary / 'master_split.csv').unlink()
        with self.assertRaisesRegex(FileNotFoundError, 'Missing existing master_split.csv'):
            preparation.validate_preparation(self.root, self.scaler)
        self.assertFalse((self.primary / 'master_split.csv').exists())

    def test_invalid_csv_header_is_rejected_without_full_scan(self):
        self.existing_scaler()
        (self.primary / 'master_split.csv').write_text('wrong,columns\n1,2\n')
        with self.assertRaisesRegex(ValueError, 'missing required columns'):
            preparation.validate_preparation(self.root, self.scaler)

    def test_optional_csv_comparison_detects_stale_source_values(self):
        self.existing_scaler()
        frame = pd.read_csv(self.primary / 'master_split.csv')
        frame.loc[0, 'y'] = 1 - frame.loc[0, 'y']
        frame.to_csv(self.primary / 'master_split.csv', index=False)
        with self.assertRaisesRegex(ValueError, 'Source rows differ'):
            preparation.validate_preparation(self.root, self.scaler, check_source_csv=True)

    def test_scaler_manifest_rejects_unequal_identifier_array_lengths(self):
        self.existing_scaler()
        with np.load(self.scaler) as record:
            arrays = {name: record[name].copy() for name in record.files}
        arrays['sampled_dataset_names'] = np.append(arrays['sampled_dataset_names'], 'unexpected')
        np.savez(self.scaler, **arrays)
        before = self.scaler.read_bytes()
        with self.assertRaisesRegex(ValueError, 'scaler manifest'):
            preparation.validate_preparation(self.root, self.scaler)
        self.assertEqual(before, self.scaler.read_bytes())

    def test_noninteger_group_id_arrays_are_rejected(self):
        self.existing_scaler()
        path = self.metadata / 'chunk_000000_group_id.npy'
        for invalid in (np.nan, 20.5):
            with self.subTest(value=invalid):
                groups = self.groups.astype(np.float64)
                groups[0] = invalid
                np.save(path, groups)
                before = path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'Invalid labels, groups or split IDs'):
                    preparation.validate_preparation(self.root, self.scaler)
                self.assertEqual(before, path.read_bytes())
