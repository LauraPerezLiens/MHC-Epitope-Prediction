#!/usr/bin/env python3
"""Globally shuffle Primary rows into new chunks before running split_data.py.

External shuffle: assign independent uniform bucket IDs, then uniformly permute
each bucket. Every input row is emitted exactly once. RAM holds one source chunk,
one bucket's metadata/permutation, and one output chunk, never all embeddings.
Secondary embeddings remain referenced at their original absolute paths.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'data_splitting'))
from split_data import iter_physical_chunks
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from neural_network.MLP.dataset import (
    _find_secondary_dir, _resolve_primary_embedding_file, SecondaryBERTStore,
)


def reorder(root: Path, output: Path, chunk_rows: int = 100_000,
            buckets: int = 1024, seed: int = 42, read_rows: int = 500_000) -> None:
    root, output = root.resolve(), output.resolve()
    if min(chunk_rows, buckets, read_rows) < 1 or seed < 0:
        raise ValueError('Sizes must be positive and seed nonnegative')
    if output == root or root in output.parents or output in root.parents:
        raise ValueError('Input and output must be separate, non-nested directories')
    sources = sorted(root.rglob('master_index.csv'))
    if not sources:
        raise ValueError(f'No master_index.csv under {root}')
    # Exclusive creation prevents mixing partial runs or overwriting originals.
    output.mkdir(parents=True, exist_ok=False)
    marker = output / 'INCOMPLETE'
    marker.write_text('Do not split or train until shuffle completes.\n')
    stage = output / '_shuffle_work'
    stage.mkdir()
    dataset = output / 'mixed'
    primary = dataset / 'classification_mixed_ProtT5_chunks'
    secondary = dataset / 'classification_mixed_SecondaryBERT_by_group'
    primary.mkdir(parents=True)
    secondary.mkdir()
    rng = np.random.default_rng(seed)
    counts = np.zeros(buckets, dtype=np.int64)
    provenance, manifests, secondary_groups = [], [], []
    group_offset = secondary_offset = manifest_offset = total = 0
    shape = dtype = columns = None
    reserved = {'source_dataset_id', 'source_chunk_id', 'source_row_idx_in_chunk',
                'source_group_id'}
    for sid, source in enumerate(sources):
        sec = _find_secondary_dir(source.parent.parent)
        if sec is None:
            raise ValueError(f'Missing SecondaryBERT store for {source}')
        store = SecondaryBERTStore(sec, cache_size=1)
        gids = store.global_group_ids
        if gids[0] < 0 or int(gids[-1]) > np.iinfo(np.int64).max - group_offset - 1:
            raise ValueError('Invalid or overflowing group identifiers')
        secondary_groups.append(np.asarray(gids) + group_offset)
        manifest = store.manifest[['chunk_id', 'start', 'end', 'x_file']].copy()
        starts, ends = manifest.start.to_numpy(), manifest.end.to_numpy()
        if (starts[0] != 0 or ends[-1] != len(gids)
                or not np.array_equal(starts[1:], ends[:-1]) or (ends <= starts).any()):
            raise ValueError(f'Non-contiguous Secondary manifest: {sec}')
        manifest['chunk_id'] = np.arange(manifest_offset, manifest_offset + len(manifest))
        manifest['start'] += secondary_offset
        manifest['end'] += secondary_offset
        manifest['x_file'] = [str((sec / p).resolve()) for p in manifest.x_file]
        for filename in manifest.x_file:
            if not Path(filename).is_file():
                raise FileNotFoundError(filename)
        manifests.append(manifest)
        provenance.append({'id': sid, 'master_index': str(source),
                           'secondary': str(sec), 'group_id_offset': group_offset})
        for cid, frame in iter_physical_chunks(source, read_rows):
            required = {'chunk_id', 'row_idx_in_chunk', 'y', 'group_id', 'protein_group_id'}
            if not required.issubset(frame) or 'split_id' in frame or reserved.intersection(frame):
                raise ValueError(f'Unexpected input columns in {source}')
            if not np.array_equal(frame.row_idx_in_chunk, np.arange(len(frame))):
                raise ValueError(f'Invalid row indices: {source}, chunk {cid}')
            if not frame.y.isin([0, 1]).all():
                raise ValueError('Labels must be binary')
            positions = np.searchsorted(gids, frame.group_id.to_numpy())
            if (positions >= len(gids)).any() or not np.array_equal(gids[positions], frame.group_id):
                raise ValueError(f'Unknown group_id: {source}, chunk {cid}')
            x = np.load(_resolve_primary_embedding_file(source.parent, cid), mmap_mode='r')
            if x.ndim != 2 or len(x) != len(frame) or x.dtype.hasobject:
                raise ValueError(f'Invalid embedding shape/dtype: {source}, chunk {cid}')
            if shape is None:
                shape, dtype = x.shape[1:], x.dtype
                columns = list(frame.columns)
            if x.shape[1:] != shape or x.dtype != dtype or list(frame.columns) != columns:
                raise ValueError('All sources must share embedding shape/dtype and CSV columns')
            frame['source_dataset_id'] = sid
            frame['source_chunk_id'] = cid
            frame['source_row_idx_in_chunk'] = frame.row_idx_in_chunk
            frame['source_group_id'] = frame.group_id
            frame['group_id'] = frame.group_id + group_offset
            assignments = rng.integers(buckets, size=len(frame))
            order = np.argsort(assignments, kind='stable')
            boundaries = np.r_[0, np.flatnonzero(np.diff(assignments[order])) + 1, len(order)]
            for a, b in zip(boundaries[:-1], boundaries[1:]):
                rows = order[a:b]
                bucket = int(assignments[rows[0]])
                prefix = stage / f'{bucket:06d}'
                frame.iloc[rows].to_csv(prefix.with_suffix('.csv'), mode='a', index=False,
                                       header=counts[bucket] == 0)
                with prefix.with_suffix('.bin').open('ab') as handle:
                    x[rows].tofile(handle)
                counts[bucket] += len(rows)
            total += len(frame)
            print(f'PARTITION source={sid} chunk={cid} total_rows={total:,}', flush=True)
        group_offset += int(gids[-1]) + 1
        secondary_offset += len(gids)
        manifest_offset += len(manifest)
    if not total:
        raise ValueError('No input rows')
    np.save(secondary / 'group_id.npy', np.concatenate(secondary_groups))
    pd.concat(manifests, ignore_index=True).to_csv(secondary / 'chunks_manifest.csv', index=False)
    del secondary_groups, manifests
    pending_x, pending_frames, pending_n = [], [], 0
    out_cid = emitted = 0

    def emit() -> None:
        nonlocal out_cid, emitted, pending_x, pending_frames, pending_n
        frame = pd.concat(pending_frames, ignore_index=True)
        frame['chunk_id'] = out_cid
        frame['row_idx_in_chunk'] = np.arange(len(frame))
        np.save(primary / f'chunk_{out_cid:06d}_X.npy', np.concatenate(pending_x))
        frame.to_csv(primary / 'master_index.csv', mode='a', index=False, header=out_cid == 0)
        emitted += len(frame)
        print(f'WRITE chunk={out_cid} rows={len(frame):,} total={emitted:,}', flush=True)
        out_cid += 1
        pending_x, pending_frames, pending_n = [], [], 0

    for bucket, n in enumerate(counts):
        if not n:
            continue
        prefix = stage / f'{bucket:06d}'
        frame = pd.read_csv(prefix.with_suffix('.csv'))
        if len(frame) != n:
            raise ValueError(f'Bucket {bucket}: metadata count mismatch')
        x = np.memmap(prefix.with_suffix('.bin'), mode='r', dtype=dtype, shape=(int(n), *shape))
        order = rng.permutation(n)
        for start in range(0, int(n), chunk_rows):
            rows = order[start:start + chunk_rows]
            cursor = 0
            while cursor < len(rows):
                take = min(chunk_rows - pending_n, len(rows) - cursor)
                selected = rows[cursor:cursor + take]
                pending_x.append(np.array(x[selected]))
                pending_frames.append(frame.iloc[selected].copy())
                pending_n += take
                cursor += take
                if pending_n == chunk_rows:
                    emit()
        del x, frame, order
        prefix.with_suffix('.bin').unlink()
        prefix.with_suffix('.csv').unlink()
    if pending_n:
        emit()
    if emitted != total:
        raise RuntimeError('Input/output row count mismatch')
    report = {'seed': seed, 'buckets': buckets, 'chunk_rows': chunk_rows,
              'rows': total, 'chunks': out_cid, 'sources': provenance,
              'secondary_storage': 'absolute references to original embeddings'}
    (output / 'reorder_manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    stage.rmdir()
    marker.unlink()
    print(f'COMPLETE: {output}. Now run split_data.py --root {output}', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--chunk-rows', type=int, default=100_000)
    parser.add_argument('--buckets', type=int, default=1024,
                        help='More buckets reduce metadata/permutation RAM, increase disk operations')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--read-rows', type=int, default=500_000)
    parser.add_argument('--resume', action='store_true', help='Audit and resume an existing incomplete output')
    parser.add_argument('--resume-log', type=Path, help='Original PARTITION/WRITE log for legacy recovery')
    args = parser.parse_args()
    if args.resume:
        if args.resume_log is None:
            parser.error('--resume requires --resume-log')
        from resume_reorder_chunks import run
        run(args.root, args.output, args.resume_log, args.chunk_rows, args.buckets, args.seed)
        return
    reorder(args.root, args.output, args.chunk_rows, args.buckets, args.seed, args.read_rows)


if __name__ == '__main__':
    main()
