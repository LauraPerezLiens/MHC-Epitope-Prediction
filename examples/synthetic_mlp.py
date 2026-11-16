#!/usr/bin/env python3
"""Generate 100 synthetic embedding rows and check the real loader and MLP on CPU."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import torch

MLP_DIR = Path(__file__).resolve().parents[1] / 'neural_network' / 'MLP'
sys.path.insert(0, str(MLP_DIR))
from dataset import (  # noqa: E402
    PRIMARY_DIM, SECONDARY_DIM, TRAIN, VALIDATION, TEST,
    ModalityStandardizer, discover_datasets, list_chunk_ids,
    load_chunk_metadata, load_rows,
)
from mlp_layernorm_shuffled_ladder100_dualeval import MLP  # noqa: E402


ROWS = 100
CHUNK_ROWS = 50
FEATURES = PRIMARY_DIM + SECONDARY_DIM


def generate(root: Path, seed: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError(f'Output directory must be empty: {root}')
    primary = root / 'mixed' / 'classification_mixed_ProtT5_chunks'
    metadata = primary / 'chunk_metadata'
    metadata.mkdir(parents=True)
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(ROWS, FEATURES)).astype(np.float32)
    groups = np.arange(ROWS, dtype=np.int64)
    features[:, 0] = groups  # Synthetic row marker for checking metadata alignment.
    labels = (groups % 2).astype(np.int8)
    splits = np.concatenate((
        np.repeat([TRAIN, VALIDATION, TEST], [40, 5, 5]),
        np.repeat([TRAIN, TEST, VALIDATION], [40, 5, 5]),
    )).astype(np.uint8)
    (root / 'INCOMPLETE').touch()
    for chunk, start in enumerate(range(0, ROWS, CHUNK_ROWS)):
        section = slice(start, start + CHUNK_ROWS)
        prefix = f'chunk_{chunk:06d}'
        np.save(primary / f'{prefix}_X.npy', features[section])
        for name, values in [('y', labels), ('group_id', groups), ('split_id', splits)]:
            np.save(metadata / f'{prefix}_{name}.npy', values[section])
    layout = dict(format='primary_secondary_float32_v1', primary_dim=PRIMARY_DIM,
                  secondary_dim=SECONDARY_DIM, normalized=False, complete=True,
                  chunks=ROWS // CHUNK_ROWS, rows=ROWS, synthetic=True, seed=seed)
    (root / 'feature_layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    (root / 'INCOMPLETE').unlink()


def check(root: Path, seed: int) -> None:
    datasets = discover_datasets(root)
    if len(datasets) != 1 or not datasets[0]['concatenated']:
        raise ValueError('Expected one synthetic concatenated dataset')
    dataset = datasets[0]
    chunks = list_chunk_ids(dataset)
    if chunks != [0, 1]:
        raise ValueError(f'Unexpected chunk IDs: {chunks}')
    features, labels, groups, splits = [], [], [], []
    rng = np.random.default_rng(seed)
    for chunk in chunks:
        meta = load_chunk_metadata(dataset, chunk)
        rows = rng.permutation(meta['n_rows'])
        group_ids = np.asarray(meta['group_id'][rows])
        x = load_rows(dataset, chunk, rows, group_ids, 'primary_secondary')
        y = np.asarray(meta['y'][rows])
        if not np.array_equal(x[:, 0], group_ids) or not np.array_equal(y, group_ids % 2):
            raise ValueError(f'Feature/label/identifier mismatch in chunk {chunk}')
        features.append(x)
        labels.append(y)
        groups.append(group_ids)
        splits.append(np.asarray(meta['split_id'][rows]))
    x, y, group_ids, split = map(np.concatenate, (features, labels, groups, splits))
    if x.shape != (ROWS, FEATURES) or x.dtype != np.float32 or not np.isfinite(x).all():
        raise ValueError('Unexpected feature shape, dtype or nonfinite values')
    if not np.array_equal(np.sort(group_ids), np.arange(ROWS)):
        raise ValueError('Missing or duplicated synthetic rows')
    for split_id, expected in [(TRAIN, 80), (VALIDATION, 10), (TEST, 10)]:
        selected = y[split == split_id]
        if len(selected) != expected or np.count_nonzero(selected == 1) != expected // 2:
            raise ValueError(f'Incorrect split/class counts for split {split_id}')

    train = x[split == TRAIN]
    mean = train.mean(axis=0, dtype=np.float64).astype(np.float32)
    scale = train.std(axis=0, dtype=np.float64).astype(np.float32)
    scale[scale < 1e-12] = 1
    scaler = ModalityStandardizer(mean[:PRIMARY_DIM], scale[:PRIMARY_DIM],
                                 mean[PRIMARY_DIM:], scale[PRIMARY_DIM:],
                                 np.asarray([dataset['name']] * len(chunks)),
                                 np.asarray(chunks, dtype=np.int64))
    scaler_path = root / 'synthetic_scaler.npz'
    scaler.save(scaler_path)
    normalized = ModalityStandardizer.load(scaler_path).transform(x.copy())
    normalized_train = normalized[split == TRAIN]
    if not (np.allclose(normalized_train.mean(axis=0), 0, atol=1e-5)
            and np.allclose(normalized_train.std(axis=0), 1, atol=1e-5)):
        raise ValueError('TRAIN normalization failed')
    # Marker mean is known independently; validation/test rows must not enter the fit.
    if not np.isclose(scaler.primary_mean[0], 44.5):
        raise ValueError('Scaler does not use exactly the synthetic TRAIN rows')

    torch.set_num_threads(2)
    torch.manual_seed(seed)
    model = MLP(input_dim=FEATURES).cpu().eval()
    with torch.inference_mode():
        probabilities = torch.sigmoid(model(torch.from_numpy(normalized)))
    if probabilities.shape != (ROWS,) or not torch.isfinite(probabilities).all():
        raise ValueError('Invalid MLP inference output')
    print('PASS: 2 chunks, 100 float32 rows, 1,792 features; feature/label alignment.')
    print('PASS: TRAIN=80, VALIDATION=10, TEST=10; balanced classes in each split.')
    print('PASS: TRAIN-only scaler saved, reloaded and checked.')
    print('PASS: CPU inference with the real MLP architecture; 100 finite probabilities.')
    print('Weights are randomly initialized. This example does not measure model quality.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', type=Path, help='Keep generated data in a new directory')
    args = parser.parse_args()
    if args.seed < 0:
        parser.error('--seed must be nonnegative')
    if args.output is not None:
        output = args.output.expanduser().resolve()
        if output.exists():
            parser.error('--output must be a new directory')
        generate(output, args.seed)
        check(output, args.seed)
        print(f'Synthetic files retained in {output}')
    else:
        with tempfile.TemporaryDirectory(prefix='synthetic_mlp_') as temporary:
            root = Path(temporary)
            generate(root, args.seed)
            check(root, args.seed)


if __name__ == '__main__':
    main()
