#!/usr/bin/env python3
"""Stream raw float32 [ProtT5 | SecondaryBERT] chunks without loading full chunks.

Separate-output mode uses prepared metadata, concurrent CPU/I/O workers and
independent training arrays. Optional archival verifies before removing inputs.
The legacy --in-place mode replaces
Primary files after full blockwise verification; do not train during conversion. Resume skips files
with a matching completion marker; interrupted chunks are regenerated.
"""
import argparse
import hashlib
import fcntl
from itertools import repeat, zip_longest
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
        return expected
    temporary = target.with_name(target.name + '.partial')
    with source.open('rb') as src, temporary.open('wb') as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if file_digest(temporary) != expected or file_digest(source) != expected:
        raise ValueError(f'Metadata copy verification failed: {source}')
    os.replace(temporary, target)
    return expected


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
    parser.add_argument('--block-rows', type=int, default=16384)
    parser.add_argument('--max-chunks', type=int, help='Limit chunks per dataset for a trial run')
    parser.add_argument('--archive-sources', action='store_true', help='Compress and verify each consumed shuffled Primary before removing it')
    parser.add_argument('--archive-originals', type=Path, help='After all outputs complete, archive this original dataset tree as well')
    parser.add_argument('--zstd', default=shutil.which('zstd') or 'zstd')
    parser.add_argument('--archive-threads', type=int, default=1)
    parser.add_argument('--workers', type=int, default=4, help='Bounded CPU/I/O conversion workers; no GPU required')
    parser.add_argument('--secondary-cache-dir', type=Path, help='Optional local SSD cache for immutable Secondary embeddings')
    parser.add_argument('--start-chunk', type=int, default=0, help='Benchmark only; nonzero leaves output INCOMPLETE')
    parser.add_argument('--verify-only', action='store_true', help='Read-only full SHA-256 verification of a completed --output dataset')
    args = parser.parse_args()
    if args.verify_only:
        if (args.in_place or args.archive_sources or args.archive_originals
                or args.secondary_cache_dir or args.max_chunks is not None or args.start_chunk):
            parser.error('--verify-only requires --output without conversion or archival options')
        output_root = args.output.resolve()
        writer_lock = output_root / '.writer.lock'
        try:
            with writer_lock.open('rb') as lock:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                verify_completed_output(output_root)
        except FileNotFoundError as exc:
            if exc.filename == str(writer_lock):
                parser.exit(1, 'Verification failed: missing .writer.lock; cannot synchronize with writers. '
                               'Read-only verification refused without creating a lock.\n')
            parser.exit(1, f'Verification failed: {exc}\n')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.exit(1, f'Verification failed: {exc}\n')
        print('Full feature and metadata SHA-256 verification passed; no files changed.', flush=True)
        return
    if args.block_rows < 1 or (args.max_chunks is not None and args.max_chunks < 1):
        parser.error('block-rows and max-chunks must be positive')
    if args.archive_threads < 1 or args.start_chunk < 0 or args.workers < 1:
        parser.error('archive-threads must be positive; start-chunk nonnegative')
    if args.archive_originals and not args.archive_sources:
        parser.error('--archive-originals requires --archive-sources')
    if args.in_place and (args.archive_sources or args.start_chunk):
        parser.error('Archiving and trial offsets require separate output mode')
    if not args.in_place:
        return run_fast(args)
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



def concatenate_chunk_fast(primary_file, group_ids, store, output, block_rows, before_replace):
    """One group lookup per chunk, RAM staging and sequential verified output."""
    primary = np.load(primary_file, mmap_mode='r')
    if primary.shape != (len(group_ids), PRIMARY_DIM) or primary.dtype != np.dtype('<f4'):
        raise ValueError(f'Invalid Primary shape/dtype: {primary_file}')
    required = len(group_ids) * (PRIMARY_DIM + SECONDARY_DIM) * 4 + 4096
    if shutil.disk_usage(output.parent).free < required:
        raise OSError('Insufficient space for concatenated chunk')
    secondary = store.get(group_ids)
    temporary = output.with_suffix('.npy.partial')
    try:
        with temporary.open('wb') as handle:
            np.lib.format.write_array_header_1_0(handle, {
                'descr': '<f4', 'fortran_order': False,
                'shape': (len(group_ids), PRIMARY_DIM + SECONDARY_DIM)})
            for start in range(0, len(group_ids), block_rows):
                end = min(start + block_rows, len(group_ids))
                block = np.empty((end-start, PRIMARY_DIM + SECONDARY_DIM), dtype='<f4')
                block[:, :PRIMARY_DIM] = primary[start:end]
                block[:, PRIMARY_DIM:] = secondary[start:end]
                if not np.isfinite(block).all():
                    raise ValueError(f'Nonfinite features in {primary_file}')
                block.tofile(handle)
            handle.flush()
            os.fsync(handle.fileno())
        check = np.load(temporary, mmap_mode='r')
        if check.shape != (len(group_ids), PRIMARY_DIM + SECONDARY_DIM) or check.dtype != np.dtype('<f4'):
            raise ValueError(f'Invalid serialized output: {temporary}')
        for start in range(0, len(group_ids), block_rows):
            end = min(start + block_rows, len(group_ids))
            if not np.array_equal(check[start:end, :PRIMARY_DIM], primary[start:end]):
                raise ValueError('Primary verification failed')
            if not np.array_equal(check[start:end, PRIMARY_DIM:], secondary[start:end]):
                raise ValueError('Secondary verification failed')
        del check, primary, secondary
        before_replace(temporary)
        os.replace(temporary, output)
        sync_directory(output.parent)
    finally:
        temporary.unlink(missing_ok=True)
        release_pages(store.global_group_ids)
        for array in store._cache.values():
            release_pages(array)



def cache_secondary_files(store, directory, workers):
    """Stage immutable Secondary files on a local SSD; original signatures stay authoritative."""
    from concurrent.futures import ThreadPoolExecutor
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    owner_path = directory / '.cache_owner.json'
    owner = {'secondary_root': str(store.root.resolve())}
    if owner_path.exists():
        if json.loads(owner_path.read_text()) != owner:
            raise ValueError('Secondary cache belongs to another dataset')
    elif any(directory.iterdir()):
        raise ValueError('Secondary cache must be empty or owned by this dataset')
    else:
        write_marker(owner_path, owner)
    sources = []
    for filename in store.x_files:
        p = Path(filename)
        sources.append(p if p.is_absolute() else store.root / p)
    required = sum(p.stat().st_size for p in sources)
    existing = sum(p.stat().st_size for p in directory.glob('*.npy'))
    if shutil.disk_usage(directory).free < max(0, required-existing) + 10 * 1024**3:
        raise OSError('Insufficient local space for Secondary SSD cache plus 10 GiB reserve')
    def stage(source):
        target = directory / (hashlib.sha256(str(source.resolve()).encode()).hexdigest() + '.npy')
        marker = target.with_suffix('.json')
        source_sig = input_signature([source])[0]
        if target.exists() and marker.exists():
            rec = json.loads(marker.read_text())
            if rec.get('source') == source_sig and rec.get('sha256') == file_digest(target):
                return str(source), str(target)
            raise ValueError(f'Stale Secondary cache: {target}')
        tmp = target.with_suffix('.npy.partial')
        h = hashlib.sha256()
        try:
            with source.open('rb') as src, tmp.open('wb') as dst:
                for block in iter(lambda: src.read(8 * 1024 * 1024), b''):
                    h.update(block)
                    dst.write(block)
                dst.flush()
                os.fsync(dst.fileno())
            if input_signature([source])[0] != source_sig or file_digest(tmp) != h.hexdigest():
                raise ValueError(f'Secondary cache verification failed: {source}')
            os.replace(tmp, target)
            write_marker(marker, {'source': source_sig, 'sha256': h.hexdigest(), 'bytes': target.stat().st_size})
            return str(source), str(target)
        finally:
            tmp.unlink(missing_ok=True)
    print(f'SSD CACHE staging {len(sources)} files, {required/1024**3:.1f} GiB to {directory}', flush=True)
    result = {}
    # Cache writer lock also protects an interrupted cache from another run.
    with (directory / '.writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, (source, target) in enumerate(pool.map(stage, sources), 1):
                result[source] = target
                if i % 10 == 0 or i == len(sources):
                    print(f'SSD CACHE verified {i}/{len(sources)}', flush=True)
    return result


_worker_state = None


def process_fast_job(job):
    """Independent thread-local Secondary mappings; only verified outputs publish."""
    import threading
    import time
    global _worker_state
    # Initialized before worker threads are launched by run_fast.
    started = time.monotonic()
    primary, output, gids, signature_inputs, inputs_digest, dependencies, secondary_root, block_rows, cache_paths, metadata_digests = job
    marker = output.with_suffix('.json')
    previous = json.loads(marker.read_text()) if marker.exists() else None
    n = len(gids)
    if previous and output.exists():
        sig = previous['signature']
        expected_input = sig.get('inputs_sha256')
        valid_inputs = expected_input == inputs_digest if expected_input is not None else sig.get('inputs') == signature_inputs
        if not valid_inputs or sig.get('rows') != n or sig.get('format') != 'primary_secondary_float32_v1':
            raise ValueError(f'Stale output signature: {output}')
        if primary.exists() and sig['primary'] != input_signature([primary])[0]:
            raise ValueError(f'Primary changed: {primary}')
        if previous.get('bytes') != output.stat().st_size or previous.get('sha256') != file_digest(output):
            raise ValueError(f'Output checksum mismatch: {output}')
        if previous.get('metadata_sha256') is not None and previous['metadata_sha256'] != metadata_digests:
            raise ValueError(f'Metadata checksum differs from conversion record: {output}')
        return primary, True, n, time.monotonic()-started
    if output.exists():
        raise ValueError(f'Untracked output: {output}')
    if not primary.is_file() or primary.is_symlink():
        raise ValueError(f'Missing or symlink Primary: {primary}')
    state = getattr(_worker_state, 'store', None)
    if state is None or state.root != secondary_root:
        state = SecondaryBERTStore(secondary_root, cache_size=1024)
        if cache_paths:
            state.x_files = np.array([cache_paths[str(Path(f) if Path(f).is_absolute() else state.root / f)] for f in state.x_files])
        original_open = state._open_embedding_chunk
        def open_random(row):
            arr = original_open(row)
            mapping = getattr(arr, '_mmap', None)
            if mapping is not None and hasattr(mapping, 'madvise'):
                mapping.madvise(mmap.MADV_RANDOM)
            return arr
        state._open_embedding_chunk = open_random
        _worker_state.store = state
    primary_signature = input_signature([primary])[0]
    sig = {'format': 'primary_secondary_float32_v1', 'rows': n,
           'inputs_sha256': inputs_digest, 'primary': primary_signature}
    def record(temporary):
        if input_signature(dependencies) != signature_inputs or input_signature([primary])[0] != primary_signature:
            raise ValueError('Inputs changed during conversion')
        write_marker(marker, {'signature': sig, 'bytes': temporary.stat().st_size,
                              'sha256': file_digest(temporary),
                              'metadata_sha256': metadata_digests,
                              'output_mtime_ns': temporary.stat().st_mtime_ns})
    concatenate_chunk_fast(primary, gids, state, output, block_rows, record)
    return primary, False, n, time.monotonic()-started


def source_metadata_rows(master, split_master, read_rows):
    """Align physical chunks with an independent split CSV when available."""
    source = iter_physical_chunks(master, read_rows)
    if split_master is None:
        pairs = zip(source, repeat(None))
    else:
        pairs = zip_longest(source, iter_physical_chunks(split_master, read_rows))
    columns = ["row_idx_in_chunk", "group_id", "y"]
    for original, assigned in pairs:
        if original is None or (split_master is not None and assigned is None):
            raise ValueError("Source index and split index differ in chunk count")
        cid, frame = original
        if not np.array_equal(frame["row_idx_in_chunk"], np.arange(len(frame))):
            raise ValueError(f"{master}, chunk {cid}: invalid row order")
        if assigned is not None:
            split_cid, split_frame = assigned
            if cid != split_cid or not np.array_equal(frame[columns], split_frame[columns]):
                raise ValueError(f"{master}, chunk {cid}: source index and split index disagree")
            frame = split_frame
        yield cid, frame


def run_fast(args):
    """Bounded CPU/I/O concurrency and verified archival overlapped with conversion."""
    import time
    import threading
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor
    global _worker_state
    _worker_state = threading.local()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'data_archiving'))
    from archive_inputs import archive_file, archive_tree
    root, output_root = args.root.resolve(), args.output.resolve()
    if root == output_root or root in output_root.parents or output_root in root.parents:
        raise ValueError('Input/output must be separate non-nested directories')
    if (root / 'INCOMPLETE').exists():
        raise ValueError('Shuffle is incomplete')
    if args.secondary_cache_dir:
        cache_root = args.secondary_cache_dir.resolve()
        for data_root in (root, output_root, args.archive_originals.resolve() if args.archive_originals else root):
            if cache_root == data_root or cache_root in data_root.parents or data_root in cache_root.parents:
                raise ValueError('Secondary cache must be separate from all dataset trees')
    if args.archive_originals:
        original = args.archive_originals.resolve()
        if (original == output_root or original in output_root.parents or output_root in original.parents
                or original == root or original in root.parents or root in original.parents):
            raise ValueError('Original, shuffled and output roots must be separate non-nested trees')
    if args.archive_sources:
        reject_active_readers(root)
    output_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with (root / '.concatenate.lock').open('a') as lock, (output_root / '.writer.lock').open('a') as writer:
        fcntl.flock(lock, (fcntl.LOCK_EX if args.archive_sources else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        layout_path = output_root / 'feature_layout.json'
        layout = json.loads(layout_path.read_text()) if layout_path.exists() else {}
        if layout.get('complete') and not (output_root / 'INCOMPLETE').exists():
            if args.archive_sources and layout.get('source_root') != str(root):
                raise ValueError('Completed output belongs to another source root')
            verify_completed_output(output_root, full=args.archive_sources)
            if not args.archive_sources:
                print('Output already complete; quick checks passed (metadata hashes, feature size/shape and changed-file hashes). Use --verify-only for full feature hashing.', flush=True)
                return
            finalize_archives(args, root, archive_tree)
            return
        (output_root / 'INCOMPLETE').write_text('Concatenation and metadata verification in progress.\n')
        masters = sorted(root.rglob('master_index.csv'))
        if not masters:
            raise FileNotFoundError('No uncompressed source master_index.csv found')
        total = converted = skipped = total_rows = scheduled = 0
        pending, archives = deque(), deque()
        def archive_primary(primary):
            rec = archive_file(primary, args.zstd, args.archive_threads)
            print(f'ARCHIVE {primary.name} ratio={rec["compressed_bytes"]/rec["original_bytes"]:.3f}', flush=True)
        def finish_job(future, archive_pool):
            nonlocal total, converted, skipped, total_rows
            primary, was_skipped, n, seconds = future.result()
            total += 1
            total_rows += n
            skipped += int(was_skipped)
            converted += int(not was_skipped)
            print(f'{"SKIP verified" if was_skipped else "WRITE + VERIFY"} {primary.name} rows={n:,} seconds={seconds:.2f}', flush=True)
            if args.archive_sources:
                archives.append(archive_pool.submit(archive_primary, primary))
                # Bound the archive backlog: at most two verified source chunks
                # wait for compression, regardless of conversion parallelism.
                if len(archives) >= 2:
                    archives.popleft().result()
            if total % 10 == 0:
                elapsed = time.monotonic()-started
                print(f'PROGRESS chunks={total} converted={converted} skipped={skipped} elapsed={elapsed:.1f}s chunks_per_hour={total/elapsed*3600:.1f}', flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool, ThreadPoolExecutor(max_workers=1) as archive_pool:
            for master in masters:
                secondary_root = _find_secondary_dir(master.parent.parent)
                if secondary_root is None:
                    raise FileNotFoundError(f'Missing Secondary store: {master}')
                store = SecondaryBERTStore(secondary_root, cache_size=1)
                print(f'AUDIT Secondary mapping: {secondary_root}', flush=True)
                dependencies = [master] + validate_secondary(store, root, max(args.block_rows, 65536))
                signature_inputs = input_signature(dependencies)
                inputs_digest = hashlib.sha256(json.dumps(signature_inputs).encode()).hexdigest()
                cache_paths = cache_secondary_files(store, args.secondary_cache_dir, args.workers) if args.secondary_cache_dir else {}
                del store
                target = output_root / master.parent.relative_to(root)
                metadata_target = target / 'chunk_metadata'
                metadata_target.mkdir(parents=True, exist_ok=True)
                source_meta = master.parent / 'chunk_metadata'
                prepared = set(source_meta.glob('chunk_*_group_id.npy'))
                if not prepared:
                    raise FileNotFoundError(f'No prepared metadata: {source_meta}')
                split_master = master.with_name('master_split.csv')
                if not split_master.is_file():
                    split_master = None
                split_signature = input_signature([split_master]) if split_master else None
                for cid, source_rows in source_metadata_rows(master, split_master, args.block_rows):
                    if cid < args.start_chunk:
                        continue
                    if args.max_chunks is not None and scheduled >= args.max_chunks:
                        break
                    gid_path = source_meta / f'chunk_{cid:06d}_group_id.npy'
                    if gid_path not in prepared:
                        raise ValueError(f'Missing prepared metadata for source index chunk {cid}')
                    prepared.remove(gid_path)
                    gids = np.load(gid_path)
                    if gids.ndim != 1 or gids.dtype.kind not in 'iu' or np.any(gids < 0):
                        raise ValueError(f'Invalid group IDs: {gid_path}')
                    metadata_digests = {}
                    for suffix in ('y', 'group_id', 'split_id'):
                        name = f'chunk_{cid:06d}_{suffix}.npy'
                        a = gids if suffix == 'group_id' else np.load(source_meta / name, mmap_mode='r')
                        if a.shape != (len(gids),):
                            raise ValueError(f'Inconsistent metadata: {name}')
                        if suffix == 'y' and not np.isin(a, [0, 1]).all():
                            raise ValueError('Invalid labels')
                        if suffix == 'split_id' and not np.isin(a, [0, 1, 2]).all():
                            raise ValueError('Invalid split IDs')
                        if suffix != 'split_id' or split_master is not None:
                            if not np.array_equal(a, source_rows[suffix].to_numpy()):
                                raise ValueError(f'{name} differs from source index')
                        metadata_digests[suffix] = copy_verified(source_meta / name, metadata_target / name)
                    primary = master.parent / f'chunk_{cid:06d}_X.npy'
                    output = target / primary.name
                    job = (primary, output, gids, signature_inputs, inputs_digest, dependencies, secondary_root, args.block_rows, cache_paths, metadata_digests)
                    pending.append(pool.submit(process_fast_job, job))
                    scheduled += 1
                    if len(pending) >= args.workers:
                        finish_job(pending.popleft(), archive_pool)
                if prepared and args.max_chunks is None and args.start_chunk == 0:
                    raise ValueError(f"Unexpected prepared metadata outside the source index: {source_meta}")
                while pending:
                    finish_job(pending.popleft(), archive_pool)
                if (input_signature(dependencies) != signature_inputs
                        or (split_master is not None and input_signature([split_master]) != split_signature)):
                    raise ValueError('Inputs changed during conversion')
            while archives:
                archives.popleft().result()
        if args.max_chunks is not None or args.start_chunk:
            print(f'PARTIAL TRIAL ONLY chunks={total}; output remains INCOMPLETE', flush=True)
            return
        provenance = root / 'reorder_manifest.json'
        if provenance.exists():
            expected = json.loads(provenance.read_text())
            if expected.get('chunks') != total or expected.get('rows') != total_rows:
                raise ValueError('Output totals differ from original shuffle manifest')
            copy_verified(provenance, output_root / provenance.name)
        write_marker(layout_path, {'format': 'primary_secondary_float32_v1', 'primary_dim': PRIMARY_DIM,
                                 'secondary_dim': SECONDARY_DIM, 'source_root': str(root), 'normalized': False,
                                 'complete': True, 'chunks': total, 'rows': total_rows,
                                 'metadata': 'independent y/group_id/split_id arrays; source CSVs retained in verified archives'})
        (output_root / 'INCOMPLETE').unlink()
        sync_directory(output_root)
        print(f'COMPLETE chunks={total:,} rows={total_rows:,} seconds={time.monotonic()-started:.1f}; TRAINING READY', flush=True)
        if args.archive_sources:
            finalize_archives(args, root, archive_tree)


def verify_completed_output(root, full=True):
    """Verify metadata hashes; optionally hash every feature file (read-only).

    Quick mode checks feature size/shape and rehashes files whose recorded mtime
    changed. It cannot detect same-size corruption with a preserved timestamp.
    """
    root = Path(root)
    layout = json.loads((root / 'feature_layout.json').read_text())
    if not layout.get('complete') or (root / 'INCOMPLETE').exists():
        raise ValueError('Output dataset is incomplete')
    if (layout.get('format') != 'primary_secondary_float32_v1'
            or layout.get('primary_dim') != PRIMARY_DIM
            or layout.get('secondary_dim') != SECONDARY_DIM
            or layout.get('normalized') is not False):
        raise ValueError('Unsupported completed feature layout')
    markers = sorted(root.rglob('chunk_*_X.json'))
    if len(markers) != layout.get('chunks'):
        raise ValueError('Completed output chunk count mismatch')
    rows = 0
    for marker in markers:
        rec = json.loads(marker.read_text())
        output = marker.with_suffix('.npy')
        stat = output.stat()
        if not isinstance(rec.get('sha256'), str) or len(rec['sha256']) != 64:
            raise ValueError(f'Missing recorded feature checksum: {output}')
        if stat.st_size != rec['bytes']:
            raise ValueError(f'Corrupt completed output: {output}')
        timestamp_changed = (rec.get('output_mtime_ns') is not None
                             and stat.st_mtime_ns != rec['output_mtime_ns'])
        if (full or timestamp_changed) and file_digest(output) != rec['sha256']:
            raise ValueError(f'Corrupt completed output: {output}')
        n = rec['signature']['rows']
        a = np.load(output, mmap_mode='r')
        if a.shape != (n, PRIMARY_DIM + SECONDARY_DIM) or a.dtype != np.dtype("float32"):
            raise ValueError(f'Invalid completed shape: {output}')
        for suffix in ('y', 'group_id', 'split_id'):
            metadata = marker.parent / 'chunk_metadata' / marker.name.replace('_X.json', f'_{suffix}.npy')
            if np.load(metadata, mmap_mode='r').shape != (n,):
                raise ValueError(f'Missing completed metadata: {metadata}')
            if 'metadata_sha256' in rec:
                hashes = rec['metadata_sha256']
                expected = hashes.get(suffix) if isinstance(hashes, dict) else None
            else:
                # Older conversion records did not store metadata hashes. Use
                # independent source/archive evidence without changing records.
                source_root = layout.get('source_root')
                source = Path(source_root) / metadata.relative_to(root) if source_root else None
                if source is not None and source.resolve() == metadata.resolve():
                    source = None
                archived = source.with_name(source.name + '.archive.json') if source else None
                if archived is not None and archived.is_file():
                    expected = json.loads(archived.read_text()).get('original_sha256')
                elif source is not None and source.is_file():
                    expected = file_digest(source)
                else:
                    expected = None
            if not isinstance(expected, str) or len(expected) != 64:
                raise ValueError(f'Missing recorded metadata checksum: {metadata}')
            if file_digest(metadata) != expected:
                raise ValueError(f'Metadata checksum mismatch: {metadata}')
        rows += n
    if rows != layout.get('rows'):
        raise ValueError('Completed row count mismatch')


def finalize_archives(args, root, archive_tree):
    # These are consumed shuffle/recovery scratch files, not source datasets.
    # All final outputs are already verified and independently trainable here.
    for name in ('_shuffle_work', '_recovery'):
        scratch = root / name
        if scratch.exists():
            if scratch.is_symlink():
                raise ValueError(f'Refusing scratch symlink: {scratch}')
            shutil.rmtree(scratch)
            print(f'REMOVED CONSUMED SHUFFLE SCRATCH {scratch}', flush=True)
    if args.archive_originals:
        original = args.archive_originals.resolve()
        print(f'ARCHIVING ORIGINAL DATA {original}; concatenated data already ready for training', flush=True)
        archive_tree(original, args.zstd, args.archive_threads)
    print(f'ARCHIVING REMAINING SHUFFLE DATA {root}', flush=True)
    archive_tree(root, args.zstd, args.archive_threads)
    if args.secondary_cache_dir and args.secondary_cache_dir.exists():
        cache_root = args.secondary_cache_dir.resolve()
        owner = json.loads((cache_root / '.cache_owner.json').read_text())
        if root not in Path(owner['secondary_root']).parents:
            raise ValueError('Cache ownership mismatch; refusing cleanup')
        shutil.rmtree(cache_root)
        print(f'REMOVED TEMPORARY SSD CACHE {cache_root}', flush=True)
    print('ALL SOURCE DATA ARCHIVED AND VERIFIED', flush=True)


if __name__ == '__main__':
    main()
