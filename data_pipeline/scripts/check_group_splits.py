#!/usr/bin/env python3
"""Count every global group_id's rows in TRAIN=0, VALIDATION=1 and TEST=2.

Reads only compact metadata. Outputs group_splits.csv and summary.json.
No datasets or splits are modified. This checks group overlap, not protein or
sequence similarity leakage. Rerunning starts a new complete metadata scan.
"""
import argparse
import fcntl
import io
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SPLITS = ['train', 'validation', 'test']


def group_bound(source):
    path = Path(source['secondary']) / 'group_id.npy'
    if path.exists():
        ids = np.load(path, mmap_mode='r', allow_pickle=False)
    else:
        raw = subprocess.check_output(['zstd', '-qdc', str(path) + '.zst'])
        ids = np.load(io.BytesIO(raw), allow_pickle=False)
    return int(ids.max()) + source['group_id_offset']


def accumulate(counts, groups, splits):
    if groups.ndim != 1 or splits.shape != groups.shape:
        raise ValueError('Invalid metadata shapes')
    if groups.dtype.kind not in 'iu' or splits.dtype.kind not in 'iu':
        raise ValueError('Metadata IDs must be integers')
    if not np.isin(splits, [0, 1, 2]).all():
        raise ValueError('Invalid split_id')
    if len(groups) and (groups.min() < 0 or groups.max() >= len(counts)):
        raise ValueError('group_id outside manifest bounds')
    keys, n = np.unique(groups.astype(np.int64) * 3 + splits.astype(np.int64), return_counts=True)
    counts[keys // 3, keys % 3] += n.astype(np.uint64)


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / '.run.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    writer = (args.root / '.writer.lock').open('rb')
    fcntl.flock(writer, fcntl.LOCK_SH | fcntl.LOCK_NB)
    manifest = json.loads((args.root / 'reorder_manifest.json').read_text())
    sources = sorted(manifest['sources'], key=lambda s: s['group_id_offset'])
    offsets = np.array([s['group_id_offset'] for s in sources], dtype=np.int64)
    family_names = np.array(['/'.join(Path(s['master_index']).parts[-5:-2]) for s in sources])
    source_ids = np.array([s['id'] for s in sources])
    maximum = max(group_bound(s) for s in sources)
    counts = np.zeros((maximum + 1, 3), dtype=np.uint64)
    files = sorted(args.root.rglob('chunk_*_group_id.npy'))
    if len(files) != manifest['chunks']:
        raise ValueError(f'Expected {manifest["chunks"]} metadata chunks, found {len(files)}')
    rows = 0
    for i, path in enumerate(files, 1):
        g = np.load(path, allow_pickle=False)
        s = np.load(path.with_name(path.name.replace('_group_id', '_split_id')), allow_pickle=False)
        accumulate(counts, g, s)
        rows += len(g)
        if i % 100 == 0 or i == len(files):
            print(f'SCAN chunks={i}/{len(files)} rows={rows:,}', flush=True)
    if rows != manifest['rows']:
        raise ValueError(f'Row total mismatch: {rows} != {manifest["rows"]}')
    total_groups = 0
    overlap = np.zeros(8, dtype=np.int64)
    totals = np.zeros(3, dtype=np.uint64)
    pairwise = {'train_validation': 0, 'train_test': 0, 'validation_test': 0}
    by_source = {str(s['id']): {'groups': 0, 'groups_in_multiple_splits': 0,
                              'rows_by_split': [0, 0, 0]} for s in sources}
    partial = args.output / 'group_splits.csv.partial'
    with partial.open('w') as dst:
        header = True
        for start in range(0, len(counts), 200000):
            block = counts[start:start + 200000]
            observed = np.flatnonzero(block.sum(axis=1))
            block = block[observed]
            gids = observed + start
            if not len(gids):
                continue
            present = block > 0
            mask = (present * np.array([1, 2, 4])).sum(axis=1)
            overlap += np.bincount(mask, minlength=8)
            totals += block.sum(axis=0)
            total_groups += len(gids)
            for name, a, b in [('train_validation', 0, 1), ('train_test', 0, 2), ('validation_test', 1, 2)]:
                pairwise[name] += int((present[:, a] & present[:, b]).sum())
            # A source starts at offset+1; the offset itself is a reserved gap.
            si = np.searchsorted(offsets, gids, side='right') - 1
            frame = pd.DataFrame({'global_group_id': gids,
                                  'source_dataset_id': source_ids[si],
                                  'source_group_id': gids - offsets[si],
                                  'source_family': family_names[si],
                                  'train_rows': block[:, 0], 'validation_rows': block[:, 1],
                                  'test_rows': block[:, 2], 'splits_present': present.sum(axis=1),
                                  'split_mask': mask})
            frame.to_csv(dst, index=False, header=header)
            header = False
            for j in np.unique(si):
                selection = si == j
                record = by_source[str(sources[j]['id'])]
                record['groups'] += int(selection.sum())
                record['groups_in_multiple_splits'] += int((present[selection].sum(axis=1) > 1).sum())
                record['rows_by_split'] = [int(a) + int(b) for a, b in
                                           zip(record['rows_by_split'], block[selection].sum(axis=0))]
    os.replace(partial, args.output / 'group_splits.csv')
    summary = {'status': 'completed', 'rows': rows, 'groups': total_groups,
               'rows_by_split': dict(zip(SPLITS, map(int, totals))),
               'groups_by_split': {name: int(sum(overlap[m] for m in range(8) if m & (1 << i)))
                                   for i, name in enumerate(SPLITS)},
               'groups_in_multiple_splits': int(sum(overlap[m] for m in [3, 5, 6, 7])),
               'groups_in_all_three': int(overlap[7]), 'pairwise_overlap': pairwise,
               'exclusive_split_combinations': {str(i): int(n) for i, n in enumerate(overlap) if i},
               'mask_definition': {'train': 1, 'validation': 2, 'test': 4},
               'by_source': by_source,
               'scope': 'Group overlap only; protein and sequence similarity are not checked.'}
    tmp = args.output / 'summary.json.partial'
    tmp.write_text(json.dumps(summary, indent=2) + '\n')
    os.replace(tmp, args.output / 'summary.json')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'data/data_input_nn_shuffled_concatenate')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/group_split_check')
    run(parser.parse_args())
