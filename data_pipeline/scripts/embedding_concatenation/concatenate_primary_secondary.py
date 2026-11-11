#!/usr/bin/env python3
"""Stream raw float32 [ProtT5 | SecondaryBERT] chunks without loading full chunks.

Reads master_index.csv independently of split preparation. Labels/splits remain
in the source tree. Sources must be complete and immutable during conversion. --in-place replaces
Primary files after full blockwise verification; do not train during conversion. Resume skips files
with a matching completion marker; interrupted chunks are regenerated.
"""
import argparse
import hashlib
import fcntl
import json
import os
import shutil
import tempfile
import mmap
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'neural_network' / 'MLP'))
from dataset import PRIMARY_DIM, SECONDARY_DIM, SecondaryBERTStore, _find_secondary_dir, _resolve_primary_embedding_file
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'data_splitting'))
from split_data import iter_physical_chunks


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_marker(path, record):
    temporary = path.with_suffix('.json.partial')
    with temporary.open('w') as handle:
        json.dump(record, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    sync_directory(path.parent)


def input_signature(paths):
    return [[str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns] for p in paths]


def validate_secondary(store, root, block_rows):
    """Independently check merged offsets, manifests and original row IDs."""
    if store.global_group_ids.ndim != 1 or store.global_group_ids.dtype.kind not in 'iu':
        raise ValueError('Secondary group IDs must be a 1-D integer array')
    if (len(store.starts) == 0 or store.starts[0] != 0
            or np.any(store.ends <= store.starts)
            or not np.array_equal(store.starts[1:], store.ends[:-1])
            or store.ends[-1] != len(store.global_group_ids)):
        raise ValueError('Secondary manifest must cover the global index exactly, without gaps/overlaps')
    dependencies = [store.root / 'group_id.npy', store.root / 'chunks_manifest.csv']
    for start, end, filename in zip(store.starts, store.ends, store.x_files):
        path = Path(filename)
        if not path.is_absolute():
            path = store.root / path
        x = np.load(path, mmap_mode='r')
        if x.shape != (int(end-start), SECONDARY_DIM) or x.dtype.kind != 'f' or x.dtype.itemsize > 4:
            raise ValueError(f'{path}: invalid shape or lossy conversion to float32')
        dependencies.append(path)
    provenance = root / 'reorder_manifest.json'
    if provenance.exists():
        dependencies.append(provenance)
        sources = json.loads(provenance.read_text())['sources']
    else:
        sources = [{'secondary': str(store.root), 'group_id_offset': 0}]
    cursor = manifest_cursor = 0
    for source in sources:
        source_root = Path(source['secondary'])
        ids_path = source_root / 'group_id.npy'
        manifest_path = source_root / 'chunks_manifest.csv'
        dependencies.extend([ids_path, manifest_path])
        ids = np.load(ids_path, mmap_mode='r')
        import pandas as pd
        manifest = pd.read_csv(manifest_path)
        offset = int(source['group_id_offset'])
        if cursor + len(ids) > len(store.global_group_ids):
            raise ValueError('Original Secondary indexes exceed merged index')
        for start in range(0, len(ids), block_rows):
            end = min(start + block_rows, len(ids))
            if not np.array_equal(store.global_group_ids[cursor+start:cursor+end], ids[start:end] + offset):
                raise ValueError(f'{source_root}: incorrect merged group offsets')
        for row in manifest.itertuples():
            if manifest_cursor >= len(store.starts):
                raise ValueError('Missing merged manifest entry')
            x_path = Path(row.x_file)
            if not x_path.is_absolute():
                x_path = source_root / x_path
            merged_path = Path(store.x_files[manifest_cursor])
            if not merged_path.is_absolute():
                merged_path = store.root / merged_path
            if (store.starts[manifest_cursor] != cursor + row.start
                    or store.ends[manifest_cursor] != cursor + row.end
                    or merged_path.resolve() != x_path.resolve()):
                raise ValueError('Merged manifest does not match original Secondary manifest')
            if row.start < 0 or row.end <= row.start or row.end > len(ids):
                raise ValueError('Invalid original Secondary range')
            if hasattr(row, 'group_id_file'):
                local_path = Path(row.group_id_file)
                if not local_path.is_absolute():
                    local_path = source_root / local_path
                dependencies.append(local_path)
                local = np.load(local_path, mmap_mode='r')
                if local.shape != (row.end-row.start,):
                    raise ValueError(f'{local_path}: incorrect row count')
                for start in range(0, len(local), block_rows):
                    end = min(start + block_rows, len(local))
                    if not np.array_equal(local[start:end], ids[row.start+start:row.start+end]):
                        raise ValueError(f'{local_path}: local/global Secondary IDs disagree')
            elif provenance.exists():
                raise ValueError(f'{manifest_path}: missing independent group_id_file mapping')
            manifest_cursor += 1
        cursor += len(ids)
    if cursor != len(store.global_group_ids) or manifest_cursor != len(store.starts):
        raise ValueError('Original and merged Secondary coverage disagree')
    return list(dict.fromkeys(dependencies))


def reject_active_readers(root):
    # Best-effort guard for this pipeline's known readers; no cross-process
    # protection can prevent an unrelated reader starting after this check.
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().split(b'\0')
            names = [Path(os.fsdecode(arg)).name for arg in args if arg]
            if ('fit_shuffled_scaler.py' in names
                    or 'mlp_layernorm_shuffled_ladder100_dualeval.py' in names):
                raise RuntimeError(f'Reader PID {entry.name} is active; finish/stop it before in-place conversion')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue


def release_pages(array):
    """Drop this process's mapped pages; the OS may keep its shared disk cache."""
    mapping = getattr(array, '_mmap', None)
    if mapping is not None and hasattr(mapping, 'madvise'):
        mapping.madvise(mmap.MADV_DONTNEED)


def stage_secondary(group_ids, store, target, block_rows):
    # Sorted unique groups map to increasing global positions and manifest rows.
    # Consequently each original Secondary file is visited once per Primary chunk.
    unique, inverse = np.unique(group_ids, return_inverse=True)
    with target.open('wb') as handle:
        np.lib.format.write_array_header_1_0(handle, {
            'descr': np.dtype('<f4').str, 'fortran_order': False,
            'shape': (len(unique), SECONDARY_DIM),
        })
        for start in range(0, len(unique), block_rows):
            store.get(unique[start:start+block_rows]).astype('<f4', copy=False).tofile(handle)
            release_pages(store.global_group_ids)
            for array in store._cache.values():
                release_pages(array)
    return inverse


def copy_verified(source, target):
    """Make independent metadata copies with bounded buffers and full hashes."""
    expected = file_digest(source)
    if target.exists():
        if file_digest(target) != expected:
            raise ValueError(f'Metadata differs: {target}')
        return
    temporary = target.with_name(target.name + '.partial')
    with source.open('rb') as src, temporary.open('wb') as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if file_digest(temporary) != expected or file_digest(source) != expected:
        raise ValueError(f'Metadata copy verification failed: {source}')
    os.replace(temporary, target)


def concatenate_chunk(primary_file, group_ids, store, output, block_rows=1024,
                      before_replace=None):
    if block_rows < 1:
        raise ValueError('block_rows must be positive')
    group_ids = np.asarray(group_ids)
    if group_ids.ndim != 1 or group_ids.dtype.kind not in 'iu':
        raise ValueError('group_ids must be a 1-D integer array')
    primary = np.load(primary_file, mmap_mode='r')
    if primary.dtype.kind != 'f' or primary.dtype.itemsize > 4:
        raise ValueError(f'{primary_file}: refusing lossy conversion to float32')
    required = len(group_ids) * (PRIMARY_DIM + SECONDARY_DIM) * 4 + 4096
    if shutil.disk_usage(output.parent).free < required:
        raise OSError('Insufficient disk space for temporary concatenated chunk')
    if primary.shape != (len(group_ids), PRIMARY_DIM):
        raise ValueError(f'{primary_file}: unexpected shape {primary.shape}')
    temporary = output.with_suffix('.npy.partial')
    stage = output.with_suffix('.secondary.partial.npy')
    try:
        inverse = stage_secondary(group_ids, store, stage, block_rows)
        secondary = np.load(stage, mmap_mode='r')
        with temporary.open('wb') as handle:
            np.lib.format.write_array_header_1_0(handle, {
                'descr': np.dtype('<f4').str, 'fortran_order': False,
                'shape': (len(group_ids), PRIMARY_DIM + SECONDARY_DIM),
            })
            for start in range(0, len(group_ids), block_rows):
                end = min(start + block_rows, len(group_ids))
                block = np.empty((end-start, PRIMARY_DIM + SECONDARY_DIM), dtype='<f4')
                block[:, :PRIMARY_DIM] = primary[start:end]
                block[:, PRIMARY_DIM:] = secondary[inverse[start:end]]
                if not np.isfinite(block).all():
                    raise ValueError(f'{primary_file}: non-finite features at row {start}')
                block.tofile(handle)
                del block
                release_pages(primary)
                release_pages(secondary)
            handle.flush()
            os.fsync(handle.fileno())
        # Reopen the serialized NPY and compare EVERY value before replacement.
        check = np.load(temporary, mmap_mode='r')
        if check.shape != (len(group_ids), PRIMARY_DIM + SECONDARY_DIM) or check.dtype != np.dtype('<f4'):
            raise ValueError(f'{temporary}: invalid serialized shape/dtype')
        for start in range(0, len(group_ids), block_rows):
            end = min(start + block_rows, len(group_ids))
            if not np.array_equal(check[start:end, :PRIMARY_DIM], np.asarray(primary[start:end], dtype='<f4')):
                raise ValueError(f'{temporary}: Primary verification failed at {start}')
            if not np.array_equal(check[start:end, PRIMARY_DIM:], secondary[inverse[start:end]]):
                raise ValueError(f'{temporary}: Secondary verification failed at {start}')
            release_pages(primary)
            release_pages(secondary)
            release_pages(check)
        del check, secondary
        # Persist proof before replacement, so a crash after rename is resumable.
        if before_replace is not None:
            before_replace(temporary)
        del primary
        os.replace(temporary, output)
        sync_directory(output.parent)
    finally:
        temporary.unlink(missing_ok=True)
        stage.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3] / 'data' / 'data_input_nn_shuffled')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--in-place', action='store_true', help='Verify then atomically replace each original Primary NPY')
    parser.add_argument('--block-rows', type=int, default=1024)
    parser.add_argument('--max-chunks', type=int, help='Limit chunks per dataset for a trial run')
    args = parser.parse_args()
    if args.block_rows < 1 or (args.max_chunks is not None and args.max_chunks < 1):
        parser.error('block-rows and max-chunks must be positive')
    root = args.root.resolve()
    output_root = root if args.in_place else args.output.resolve()
    if not args.in_place and (root == output_root or root in output_root.parents or output_root in root.parents):
        parser.error('--output must be separate from the input tree')
    if (root / 'INCOMPLETE').exists():
        parser.error('Source reordering is incomplete')
    sources = sorted(root.rglob('master_index.csv'))
    if not sources:
        parser.error(f'No master_index.csv under {root}')
    if args.in_place:
        reject_active_readers(root)
    output_root.mkdir(parents=True, exist_ok=True)
    # Lock the input tree even for separate outputs to prevent concurrent conversions.
    with (root / '.concatenate.lock').open('a') as lock:
        fcntl.flock(lock, (fcntl.LOCK_EX if args.in_place else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        # Separate outputs can coexist with read-only scaler jobs, but only one
        # writer may operate on a given output directory.
        output_lock = (output_root / '.writer.lock').open('a')
        fcntl.flock(output_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not args.in_place:
            (output_root / 'INCOMPLETE').write_text('Concatenation or metadata copying not yet complete.\n')
        for master in sources:
            secondary = _find_secondary_dir(master.parent.parent)
            if secondary is None:
                raise FileNotFoundError(f'No Secondary store for {master}')
            store = SecondaryBERTStore(secondary, cache_size=1)
            target = output_root / master.parent.relative_to(root)
            target.mkdir(parents=True, exist_ok=True)
            print(f'AUDIT Secondary mapping: {secondary}', flush=True)
            dependencies = [master] + validate_secondary(store, root, args.block_rows)
            source_signature = input_signature(dependencies)
            release_pages(store.global_group_ids)
            expected_chunks = processed_chunks = 0
            metadata_target = target / 'chunk_metadata'
            if not args.in_place:
                metadata_target.mkdir(exist_ok=True)
            for number, (cid, frame) in enumerate(iter_physical_chunks(master, args.block_rows)):
                if args.max_chunks is not None and number >= args.max_chunks:
                    break
                processed_chunks += 1
                if not args.in_place:
                    for suffix in ('y', 'group_id', 'split_id'):
                        filename = f'chunk_{cid:06d}_{suffix}.npy'
                        copy_verified(master.parent / 'chunk_metadata' / filename, metadata_target / filename)
                if not np.array_equal(frame.row_idx_in_chunk, np.arange(len(frame))):
                    raise ValueError(f'{master}, chunk {cid}: invalid row order')
                if frame.group_id.dtype.kind not in 'iu' or (frame.group_id < 0).any():
                    raise ValueError('Primary group IDs must be nonnegative integers')
                primary = _resolve_primary_embedding_file(master.parent, cid)
                if primary.is_symlink():
                    raise ValueError(f'Refusing to replace/read symlink Primary: {primary}')
                output = primary if args.in_place else target / f'chunk_{cid:06d}_X.npy'
                marker = output.with_suffix('.concatenated.json' if args.in_place else '.json')
                signature = {
                    'format': 'primary_secondary_float32_v1', 'rows': len(frame),
                    'inputs': source_signature,
                    'primary': [str(primary.resolve()), primary.stat().st_size, primary.stat().st_mtime_ns],
                }
                if args.in_place:
                    signature.pop('primary')
                    shape = np.load(primary, mmap_mode='r').shape
                    if shape == (len(frame), PRIMARY_DIM + SECONDARY_DIM):
                        if not marker.exists():
                            raise ValueError(f'{primary}: concatenated file without verification record')
                        previous = json.loads(marker.read_text())
                        if previous.get('signature') != signature or previous.get('sha256') != file_digest(primary):
                            raise ValueError(f'{primary}: verification record mismatch')
                        print(f'SKIP verified {primary}', flush=True)
                        continue
                    if shape != (len(frame), PRIMARY_DIM):
                        raise ValueError(f'{primary}: unsupported shape {shape}')
                    original_signature = input_signature([primary])
                    original_digest = file_digest(primary)
                    def record_verified(temporary):
                        reject_active_readers(root)
                        if input_signature(dependencies) != source_signature or input_signature([primary]) != original_signature:
                            raise ValueError('Inputs changed during conversion; original preserved')
                        write_marker(marker, {'signature': signature, 'sha256': file_digest(temporary),
                                              'bytes': temporary.stat().st_size, 'original_sha256': original_digest,
                                              'original_primary': original_signature})
                    print(f'CONVERT + VERIFY + REPLACE {primary} rows={len(frame):,}', flush=True)
                    concatenate_chunk(primary, frame.group_id.to_numpy(dtype=np.int64), store,
                                      primary, args.block_rows, before_replace=record_verified)
                    continue
                if input_signature(dependencies) != source_signature:
                    raise ValueError('Inputs changed during conversion')
                if output.exists() and not marker.exists():
                    raise ValueError(f'Untracked output exists: {output}; refusing overwrite')
                if output.exists() and marker.exists():
                    previous = json.loads(marker.read_text())
                    if previous.get('signature') != signature or previous.get('bytes') != output.stat().st_size or previous.get('sha256') != file_digest(output):
                        raise ValueError(f'Stale output: {output}; use a new output directory')
                    print(f'SKIP {output}', flush=True)
                    continue
                print(f'WRITE {output} rows={len(frame):,}', flush=True)
                def record_output(temporary):
                    if input_signature(dependencies) != source_signature or signature['primary'] != input_signature([primary])[0]:
                        raise ValueError('Inputs changed during conversion')
                    write_marker(marker, {'signature': signature, 'bytes': temporary.stat().st_size,
                                          'sha256': file_digest(temporary)})
                concatenate_chunk(primary, frame.group_id.to_numpy(dtype=np.int64), store,
                                  output, args.block_rows, before_replace=record_output)
            if not args.in_place and args.max_chunks is None:
                print(f'COPY + VERIFY INDEXES {master.parent}', flush=True)
                for filename in ('master_index.csv', 'master_split.csv'):
                    copy_verified(master.parent / filename, target / filename)
            print(f'DONE {master.parent}; chunks={processed_chunks}', flush=True)
        if not args.in_place and args.max_chunks is None:
            for filename in ('reorder_manifest.json',):
                if (root / filename).exists():
                    copy_verified(root / filename, output_root / filename)
            write_marker(output_root / 'feature_layout.json', {
                'format': 'primary_secondary_float32_v1', 'primary_dim': PRIMARY_DIM,
                'secondary_dim': SECONDARY_DIM, 'source_root': str(root),
                'normalized': False, 'complete': True,
            })
            (output_root / 'INCOMPLETE').unlink()
            sync_directory(output_root)
            print('ALL CONCATENATED CHUNKS AND METADATA VERIFIED; COMPLETE', flush=True)


if __name__ == '__main__':
    main()
