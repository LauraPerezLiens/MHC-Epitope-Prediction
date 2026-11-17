#!/usr/bin/env python3
"""Validate existing splits, metadata and an optional scaler without changing them."""
import argparse
import csv
from pathlib import Path
import sys

import numpy as np

from dataset import (PRIMARY_DIM, SECONDARY_DIM, ModalityStandardizer,
                     discover_datasets, load_chunk_metadata, _resolve_primary_embedding_file)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'data_pipeline/scripts/data_splitting'))
from check_master_split import REQUIRED, validate_dataset


def validate_preparation(root, scaler_path, check_source_csv=False):
    root, scaler_path = Path(root), Path(scaler_path)
    compare_source_csv = check_source_csv or not scaler_path.is_file()
    datasets = discover_datasets(root)
    prepared = {Path(ds['primary_path']).resolve() for ds in datasets}
    for path in root.rglob('chunk_*_X*.npy'):
        if not path.name.endswith(('_X.npy', '_X_primary.npy')):
            continue
        primary = path.parent.parent if path.parent.name == 'chunks' else path.parent
        if primary.resolve() not in prepared:
            raise FileNotFoundError(f'Missing existing metadata for feature directory: {primary}')
    expected = set()
    for ds in datasets:
        primary = Path(ds['primary_path'])
        files = sorted(p for folder in (primary, primary / 'chunks')
                       for pattern in ('chunk_*_X.npy', 'chunk_*_X_primary.npy')
                       for p in folder.glob(pattern))
        if not files:
            raise ValueError(f'No feature chunks found: {primary}')
        chunk_ids = [int(p.name.split('_')[1]) for p in files]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError(f'Ambiguous feature chunks: {primary}')
        for cid in chunk_ids:
            for suffix in ('y', 'group_id', 'split_id'):
                path = Path(ds['metadata_path']) / f'chunk_{cid:06d}_{suffix}.npy'
                if not path.is_file():
                    raise FileNotFoundError(f'Missing existing metadata: {path}; restore or prepare it explicitly')
            meta = load_chunk_metadata(ds, cid)
            features = np.load(_resolve_primary_embedding_file(primary, cid), mmap_mode='r')
            dimension = PRIMARY_DIM + SECONDARY_DIM if ds['concatenated'] else PRIMARY_DIM
            if features.shape != (meta['n_rows'], dimension):
                raise ValueError(f'Feature/metadata row or dimension mismatch: {primary}, chunk {cid}')
            if (not np.isin(meta['y'], [0, 1]).all()
                    or not np.isin(meta['split_id'], [0, 1, 2]).all()
                    or meta['group_id'].dtype.kind not in 'iu'
                    or np.any(meta['group_id'] < 0)):
                raise ValueError(f'Invalid labels, groups or split IDs: {primary}, chunk {cid}')
            expected.add((str(ds['name']), cid))
        if not ds['concatenated']:
            for name in ('master_index.csv', 'master_split.csv'):
                if not (primary / name).is_file():
                    raise FileNotFoundError(f'Missing existing {name}: {primary}; no split will be regenerated')
                with (primary / name).open(newline='') as handle:
                    header = next(csv.reader(handle), [])
                required = set(REQUIRED) | ({'split_id'} if name == 'master_split.csv' else set())
                if not required.issubset(header):
                    raise ValueError(f'{primary / name}: missing required columns {sorted(required - set(header))}')
            if compare_source_csv:
                validate_dataset(primary / 'master_split.csv')
            else:
                print(f'CSV headers checked: {primary}; full CSV comparison skipped '
                      '(existing scaler; request --check-source-csv to compare all source rows).', flush=True)
        elif not scaler_path.is_file():
            raise ValueError('A concatenated-only dataset requires its existing TRAIN scaler; '
                             'this launcher fits only from separate modalities')
        if not scaler_path.exists() and ds['secondary_path'] is None:
            raise FileNotFoundError(f'Scaler fitting requires the separate Secondary store: {ds["name"]}')
    if scaler_path.exists():
        scaler = ModalityStandardizer.load(scaler_path)
        for mean, scale, dimension in [(scaler.primary_mean, scaler.primary_scale, PRIMARY_DIM),
                                       (scaler.secondary_mean, scaler.secondary_scale, SECONDARY_DIM)]:
            if (mean.shape != (dimension,) or scale.shape != (dimension,)
                    or not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale <= 0)):
                raise ValueError('Existing scaler has invalid dimensions or values')
        if (scaler.sampled_dataset_names.ndim != 1 or scaler.sampled_chunk_ids.ndim != 1
                or len(scaler.sampled_dataset_names) != len(scaler.sampled_chunk_ids)):
            raise ValueError('Existing scaler manifest has inconsistent identifier arrays')
        actual = list(zip(map(str, scaler.sampled_dataset_names), map(int, scaler.sampled_chunk_ids)))
        if set(actual) != expected or len(actual) != len(expected):
            raise ValueError('Existing scaler manifest does not match the prepared chunk set')
    return len(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--scaler-path', type=Path, required=True)
    parser.add_argument('--check-source-csv', action='store_true',
                        help='Compare all source CSV rows with metadata, even when a scaler already exists')
    args = parser.parse_args()
    try:
        chunks = validate_preparation(args.root, args.scaler_path, args.check_source_csv)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        parser.error(f'Existing preparation is required; no splits or metadata were changed: {exc}')
    print(f'PREPARATION VALID: {chunks} chunks; existing splits and metadata preserved.', flush=True)


if __name__ == '__main__':
    main()
