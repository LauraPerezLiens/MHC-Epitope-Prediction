#!/usr/bin/env python3
"""Compare sampled concatenated Primary/Secondary features with archived sources.

Defaults: 3 distinct groups per source (33 total), spread across at least 3
randomly selected chunks, seed 42. Primary reference is the archived shuffled
Primary chunk; Secondary reference is the original per-group store. This does
not trace Primary back through the pre-shuffle permutation or certify all rows.
Only selected source blocks are decompressed in RAM; no dataset is modified.
"""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def load_source(path):
    """Read one source file, verifying its full original SHA256 when archived."""
    if path.exists():
        return path.read_bytes()
    record = json.loads(Path(str(path) + '.archive.json').read_text())
    raw = subprocess.check_output(['zstd', '-qdc', str(path) + '.zst'])
    if hashlib.sha256(raw).hexdigest() != record['original_sha256']:
        raise ValueError(f'Source checksum mismatch: {path}')
    return raw


def source_array(path):
    return np.load(io.BytesIO(load_source(path)), allow_pickle=False)


def compare(primary, secondary, combined):
    return {'primary_exact': bool(np.array_equal(primary, combined[:1024])),
            'secondary_exact': bool(np.array_equal(secondary, combined[1024:])),
            'primary_max_abs_diff': float(np.max(np.abs(primary - combined[:1024]))),
            'secondary_max_abs_diff': float(np.max(np.abs(secondary - combined[1024:]))),
            'all_values_finite': bool(np.isfinite(primary).all() and np.isfinite(secondary).all()
                                      and np.isfinite(combined).all())}


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / '.run.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    writer = (args.root / '.writer.lock').open('rb')
    fcntl.flock(writer, fcntl.LOCK_SH | fcntl.LOCK_NB)
    manifest = json.loads((args.root / 'reorder_manifest.json').read_text())
    layout = json.loads((args.root / 'feature_layout.json').read_text())
    if layout['primary_dim'] != 1024 or layout['secondary_dim'] != 768:
        raise ValueError('Expected 1024 Primary + 768 Secondary dimensions')
    sources = sorted(manifest['sources'], key=lambda s: s['group_id_offset'])
    offsets = np.array([s['group_id_offset'] for s in sources], dtype=np.int64)
    markers = sorted(args.root.rglob('chunk_*_X.json'))
    if len(markers) != manifest['chunks']:
        raise ValueError('Chunk count does not match manifest')
    rng = np.random.default_rng(args.seed)
    selected = {s['id']: [] for s in sources}
    seen = {s['id']: set() for s in sources}
    scanned = 0
    for index in rng.permutation(len(markers)):
        marker = markers[index]
        stem = marker.name.replace('_X.json', '')
        groups = np.load(marker.parent / 'chunk_metadata' / f'{stem}_group_id.npy', allow_pickle=False)
        assignments = np.searchsorted(offsets, groups, side='right') - 1
        if (assignments < 0).any():
            raise ValueError('Group outside source offsets')
        scanned += 1
        for si, source in enumerate(sources):
            sid = source['id']
            remaining = args.groups_per_source - len(selected[sid])
            if remaining <= 0:
                continue
            positions = np.flatnonzero(assignments == si)
            # Sample distinct groups, avoiding repeated variants of the same group.
            unique, first = np.unique(groups[positions], return_index=True)
            eligible = positions[first[[int(g) not in seen[sid] for g in unique]]]
            if not len(eligible):
                continue
            slots = max(1, args.chunks - scanned + 1)
            n = min(len(eligible), max(1, (remaining + slots - 1) // slots))
            for row in rng.choice(eligible, size=n, replace=False):
                gid = int(groups[row])
                selected[sid].append({'marker': marker, 'chunk': stem,
                                      'row': int(row), 'global_group_id': gid,
                                      'source_group_id': gid - source['group_id_offset']})
                seen[sid].add(gid)
        if all(len(v) == args.groups_per_source for v in selected.values()):
            break
    if any(len(v) != args.groups_per_source for v in selected.values()):
        raise ValueError('Insufficient distinct groups for one or more sources')
    rows = [dict(r, source_dataset_id=s['id']) for s in sources for r in selected[s['id']]]
    print(f'SAMPLED groups={len(rows)} metadata_chunks_scanned={scanned}', flush=True)
    # Read each shuffled Primary archive once and retain only selected vectors.
    for marker in sorted({r['marker'] for r in rows}):
        chosen = [r for r in rows if r['marker'] == marker]
        x = np.load(marker.with_suffix('.npy'), mmap_mode='r', allow_pickle=False)
        reference = Path(layout['source_root']) / marker.relative_to(args.root).with_suffix('.npy')
        primary = source_array(reference)
        if primary.shape != (len(x), 1024) or x.shape[1] != 1792:
            raise ValueError(f'Invalid Primary/combined schema: {marker}')
        for r in chosen:
            r['_combined'] = x[r['row']].copy()
            r['_primary'] = primary[r['row']].copy()
            r['primary_reference'] = str(reference)
        del primary, x
        print(f'PRIMARY {marker.stem} rows={len(chosen)}', flush=True)
    results = []
    for source in sources:
        sid = source['id']
        store = Path(source['secondary'])
        gids = source_array(store / 'group_id.npy')
        if gids.ndim != 1 or not (np.diff(gids) > 0).all():
            raise ValueError(f'Invalid Secondary group index: {store}')
        table = pd.read_csv(io.BytesIO(load_source(store / 'chunks_manifest.csv')))
        starts, ends = table.start.to_numpy(), table.end.to_numpy()
        if starts[0] != 0 or ends[-1] != len(gids) or not np.array_equal(starts[1:], ends[:-1]):
            raise ValueError(f'Invalid Secondary block boundaries: {store}')
        for r in rows:
            if r['source_dataset_id'] != sid:
                continue
            ix = int(np.searchsorted(gids, r['source_group_id']))
            if ix >= len(gids) or gids[ix] != r['source_group_id']:
                raise ValueError(f'Secondary group not found: {r}')
            r['_slot'] = int(np.searchsorted(ends, ix, side='right'))
            r['_secondary_row'] = ix - int(starts[r['_slot']])
        for slot in sorted({r['_slot'] for r in rows if r['source_dataset_id'] == sid}):
            entry = table.iloc[slot]
            reference = Path(entry.x_file)
            if not reference.is_absolute():
                reference = store / reference
            secondary = source_array(reference)
            if secondary.shape != (int(ends[slot] - starts[slot]), 768):
                raise ValueError(f'Invalid Secondary schema: {reference}')
            protein_path = Path(entry.protein_group_id_file)
            if not protein_path.is_absolute():
                protein_path = store / protein_path
            protein_ids = source_array(protein_path)
            group_path = Path(entry.group_id_file)
            if not group_path.is_absolute():
                group_path = store / group_path
            chunk_groups = source_array(group_path)
            for r in rows:
                if r['source_dataset_id'] != sid or r['_slot'] != slot:
                    continue
                ix = r['_secondary_row']
                if int(chunk_groups[ix]) != r['source_group_id']:
                    raise ValueError('Secondary block group ID mismatch')
                result = {k: v for k, v in r.items() if not k.startswith('_') and k != 'marker'}
                result.update(source_family='/'.join(Path(source['master_index']).parts[-5:-2]),
                              protein_group_id=int(protein_ids[ix]),
                              secondary_reference=str(reference), secondary_row=ix,
                              **compare(r['_primary'], secondary[ix], r['_combined']))
                results.append(result)
            del secondary, protein_ids, chunk_groups
            print(f'SECONDARY source={sid} block={slot} checked', flush=True)
        del gids
    failed = [r for r in results if not (r['primary_exact'] and r['secondary_exact'] and r['all_values_finite'])]
    partial = args.output / 'sampled_modalities.csv.partial'
    pd.DataFrame(results).to_csv(partial, index=False)
    os.replace(partial, args.output / 'sampled_modalities.csv')
    summary = {'status': 'failed' if failed else 'passed', 'sampled_groups': len(results),
               'sources': len(sources), 'groups_per_source': args.groups_per_source,
               'sampled_chunks': len({r['chunk'] for r in results}),
               'metadata_chunks_scanned': scanned, 'seed': args.seed,
               'failed_groups': len(failed),
               'primary_reference': 'archived shuffled Primary',
               'secondary_reference': 'original per-group Secondary',
               'scope': 'Sample only; does not check all rows or Primary pre-shuffle provenance.'}
    tmp = args.output / 'summary.json.partial'
    tmp.write_text(json.dumps(summary, indent=2) + '\n')
    os.replace(tmp, args.output / 'summary.json')
    print(json.dumps(summary, indent=2), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'data/data_input_nn_shuffled_concatenate')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/sampled_modalities_check')
    parser.add_argument('--groups-per-source', type=int, default=3)
    parser.add_argument('--chunks', type=int, default=3, help='Target chunks over which to spread the sample')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    if args.groups_per_source <= 0 or args.chunks <= 0:
        parser.error('--groups-per-source and --chunks must be positive')
    run(args)
