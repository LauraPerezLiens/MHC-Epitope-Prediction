#!/usr/bin/env python3
"""Fit TRAIN-only statistics with sequential Secondary reads and disk-backed counts.

Primary is streamed once. TRAIN occurrences per Secondary group are counted in
an on-disk uint32 array, then each Secondary embedding is read once in manifest
order and contributes with that multiplicity. No balanced sampling is used.
"""
import argparse
import fcntl
import os
from pathlib import Path
import tempfile
import time

import numpy as np
from dataset import (TRAIN, PRIMARY_DIM, SECONDARY_DIM, ModalityStandardizer,
                     SecondaryBERTStore, _RunningMoments, discover_datasets,
                     list_chunk_ids, load_chunk_metadata, _resolve_primary_embedding_file)


class WeightedMoments(_RunningMoments):
    def update_weighted(self, values, weights):
        values = np.asarray(values, dtype=np.float64)
        weights = np.asarray(weights, dtype=np.float64)
        if values.shape != (len(weights), self.dimension):
            raise ValueError('Invalid weighted statistics dimensions')
        if not np.isfinite(values).all() or not np.isfinite(weights).all() or (weights < 0).any():
            raise ValueError('Nonfinite values or invalid weights')
        n = int(weights.sum())
        if not n:
            return
        mean = np.einsum('i,ij->j', weights, values) / n
        centered = values - mean
        m2 = np.einsum('i,ij,ij->j', weights, centered, centered)
        delta = mean - self.mean
        total = self.count + n
        self.m2 += m2 + delta * delta * (self.count * n / total)
        self.mean += delta * (n / total)
        self.count = total


def fit_sequential(datasets, block_rows=2048, work_dir=None):
    if block_rows < 1:
        raise ValueError('block_rows must be positive')
    primary_stats = _RunningMoments(PRIMARY_DIM)
    secondary_stats = WeightedMoments(SECONDARY_DIM)
    names, chunks = [], []
    t0 = time.monotonic()
    for ds in datasets:
        if ds['secondary_path'] is None:
            raise FileNotFoundError(f"No Secondary store for {ds['name']}")
        store = SecondaryBERTStore(ds['secondary_path'], cache_size=1)
        if (len(store.starts) == 0 or store.starts[0] != 0
                or np.any(store.ends <= store.starts)
                or not np.array_equal(store.starts[1:], store.ends[:-1])
                or store.ends[-1] != len(store.global_group_ids)):
            raise ValueError('Secondary manifest has gaps, overlaps or incorrect coverage')
        ids = list_chunk_ids(ds)
        dataset_rows = 0
        with tempfile.TemporaryDirectory(prefix='scaler_counts_', dir=work_dir) as temporary:
            counts = np.lib.format.open_memmap(Path(temporary)/'counts.npy', mode='w+',
                                              dtype=np.uint32, shape=(len(store.global_group_ids),))
            counts[:] = 0
            print(f"{ds['name']}: disk-backed counts {counts.nbytes / 1e6:.1f} MB; block_rows={block_rows}", flush=True)
            for number, cid in enumerate(ids, 1):
                meta = load_chunk_metadata(ds, cid)
                if not np.isin(meta['split_id'], [0, 1, 2]).all():
                    raise ValueError(f'Invalid split IDs in chunk {cid}')
                path = _resolve_primary_embedding_file(Path(ds['primary_path']), cid)
                x = np.load(path, mmap_mode='r')
                if x.ndim != 2 or len(x) != meta['n_rows'] or x.shape[1] not in (PRIMARY_DIM, PRIMARY_DIM+SECONDARY_DIM):
                    raise ValueError(f'{path}: unexpected shape {x.shape}')
                if x.shape[1] != PRIMARY_DIM and not path.with_suffix('.concatenated.json').exists():
                    raise ValueError(f'{path}: concatenated features lack conversion record')
                n_train = 0
                for start in range(0, len(x), block_rows):
                    end = min(start+block_rows, len(x))
                    selected = np.flatnonzero(meta['split_id'][start:end] == TRAIN) + start
                    if not len(selected):
                        continue
                    # Match the training loader's float32 conversion.
                    values = np.asarray(x[selected, :PRIMARY_DIM], dtype=np.float32)
                    if not np.isfinite(values).all():
                        raise ValueError(f'{path}: nonfinite TRAIN features')
                    primary_stats.update(values)
                    gids = np.asarray(meta['group_id'][selected], dtype=np.int64)
                    positions = np.searchsorted(store.global_group_ids, gids)
                    if (positions >= len(store.global_group_ids)).any():
                        raise KeyError(f'{path}: missing Secondary group')
                    if not np.array_equal(store.global_group_ids[positions], gids):
                        raise KeyError(f'{path}: missing Secondary group')
                    unique, multiplicities = np.unique(positions, return_counts=True)
                    updated = counts[unique].astype(np.uint64) + multiplicities.astype(np.uint64)
                    if (updated > np.iinfo(np.uint32).max).any():
                        raise OverflowError('TRAIN group count exceeds uint32')
                    counts[unique] = updated.astype(np.uint32)
                    n_train += len(selected)
                dataset_rows += n_train
                if n_train:
                    names.append(str(ds['name'])); chunks.append(cid)
                del x, meta
                if number <= 5 or number % 25 == 0 or number == len(ids):
                    elapsed = time.monotonic()-t0
                    print(f"PRIMARY {ds['name']}: {number}/{len(ids)} chunks; TRAIN={dataset_rows:,}; elapsed={elapsed:.1f}s", flush=True)
            counts.flush()
            secondary_before = secondary_stats.count
            for number, (start, end, filename) in enumerate(zip(store.starts, store.ends, store.x_files), 1):
                path = Path(filename)
                if not path.is_absolute():
                    path = store.root/path
                x = np.load(path, mmap_mode='r')
                if x.shape != (int(end-start), SECONDARY_DIM):
                    raise ValueError(f'{path}: Secondary/manifest shape mismatch')
                for local in range(0, len(x), block_rows):
                    stop = min(local+block_rows, len(x))
                    weights = np.asarray(counts[int(start)+local:int(start)+stop])
                    used = weights > 0
                    if used.any():
                        secondary_stats.update_weighted(np.asarray(x[local:stop][used], dtype=np.float32), weights[used])
                del x
                if number <= 5 or number % 25 == 0 or number == len(store.starts):
                    print(f"SECONDARY {ds['name']}: {number}/{len(store.starts)} files; elapsed={time.monotonic()-t0:.1f}s", flush=True)
            if secondary_stats.count-secondary_before != dataset_rows:
                raise ValueError('Primary/Secondary TRAIN occurrence counts disagree')
            del counts
    if primary_stats.count != secondary_stats.count:
        raise ValueError('Modality counts disagree')
    p_mean, p_scale = primary_stats.finalize()
    s_mean, s_scale = secondary_stats.finalize()
    print(f'TRAIN rows per modality: {primary_stats.count:,}', flush=True)
    return ModalityStandardizer(p_mean, p_scale, s_mean, s_scale,
                               np.asarray(names), np.asarray(chunks, dtype=np.int64))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--block-rows', type=int, default=2048)
    parser.add_argument('--work-dir', type=Path, help='Directory for temporary disk-backed group counts')
    args = parser.parse_args()
    if args.block_rows < 1:
        parser.error('block-rows must be positive')
    if (args.root / 'INCOMPLETE').exists():
        parser.error('Dataset reordering incomplete')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Shared source lock excludes the concatenator's exclusive conversion lock.
    with (args.root / '.concatenate.lock').open('a') as source_lock, args.output.with_suffix('.lock').open('a') as lock:
        fcntl.flock(source_lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.output.exists():
            parser.error('Output already exists; refusing to replace scaler')
        scaler = fit_sequential(discover_datasets(args.root), args.block_rows, args.work_dir or args.output.parent)
        for array in (scaler.primary_mean, scaler.primary_scale, scaler.secondary_mean, scaler.secondary_scale):
            if not np.isfinite(array).all():
                raise ValueError('Nonfinite scaler statistics')
        temporary = args.output.with_suffix('.partial.npz')
        try:
            scaler.save(temporary)
            with temporary.open('rb') as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, args.output)
        finally:
            temporary.unlink(missing_ok=True)
        print(f'SCALER COMPLETE: {args.output}; TRAIN chunks={len(scaler.sampled_chunk_ids)}', flush=True)


if __name__ == '__main__':
    main()
