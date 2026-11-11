"""Audit and recover legacy reorder output; preserve immutable recovery inputs.

All output metadata is checked against original rows and checked for duplicates.
Embedding shape/dtype is checked for every chunk; three full vectors per chunk
are compared to their original rows. Embeddings are sampled, not exhaustively
compared. Each new output chunk has a durable CSV-offset checkpoint.
"""
import argparse
import fcntl
import io
import json
import os
import re
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

ADDRESS = ['source_dataset_id', 'source_chunk_id', 'source_row_idx_in_chunk']
FIELDS = ['y', 'protein_group_id', 'group_id']



def address_tables(lookup):
    shape = (max(k[0] for k in lookup)+1,max(k[1] for k in lookup)+1)
    starts = np.full(shape,-1,dtype=np.int64)
    sizes = np.zeros(shape,dtype=np.int64)
    for (sid,cid),(start,n) in lookup.items():
        starts[sid,cid],sizes[sid,cid] = start,n
    return starts,sizes


def row_indices(frame,starts,sizes):
    values = frame[ADDRESS].to_numpy()
    if not np.issubdtype(values.dtype,np.integer):
        raise ValueError('Row addresses must be integers')
    sid,cid,row = values.T
    if (values<0).any() or (sid>=starts.shape[0]).any() or (cid>=starts.shape[1]).any():
        raise ValueError('Invalid source address')
    start,n = starts[sid,cid],sizes[sid,cid]
    if (start<0).any() or (row>=n).any():
        raise ValueError('Original source row out of range')
    return start+row


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    with temp.open('w') as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def records(log):
    result, total, committed, chunks = [], 0, 0, 0
    for line in log.read_text().splitlines(keepends=True):
        m = re.fullmatch(r'PARTITION source=(\d+) chunk=(\d+) total_rows=([\d,]+)\n?', line)
        if m:
            end = int(m[3].replace(',', ''))
            result.append((int(m[1]), int(m[2]), total, end-total))
            total = end
        m = re.fullmatch(r'WRITE chunk=(\d+) rows=([\d,]+) total=([\d,]+)\n?', line)
        if m:
            chunks, committed = int(m[1])+1, int(m[3].replace(',', ''))
    if not result or not committed:
        raise ValueError('Legacy log must contain complete partition and write records')
    return result, total, committed, chunks


def csv_offset(path, rows):
    """Byte boundary after the header and exactly rows complete CSV records."""
    wanted, position = rows+1, 0
    with path.open('rb') as handle:
        while True:
            block = handle.read(16*1024*1024)
            if not block:
                raise ValueError('CSV shorter than committed rows')
            lines = block.count(b'\n')
            if lines >= wanted:
                end = 0
                for _ in range(wanted):
                    end = block.index(b'\n', end)+1
                return position+end
            wanted -= lines
            position += len(block)


def restore_checkpoint(primary, checkpoint):
    master = primary / 'master_index.csv'
    if master.stat().st_size < checkpoint['csv_bytes']:
        raise ValueError('CSV shorter than durable checkpoint')
    with master.open('r+b') as handle:
        handle.truncate(checkpoint['csv_bytes'])
        handle.flush()
        os.fsync(handle.fileno())
    for path in primary.glob('chunk_*_X.npy'):
        if int(path.stem.split('_')[1]) >= checkpoint['chunks']:
            print(f'REMOVE uncommitted embedding {path.name}', flush=True)
            path.unlink()
    for path in primary.glob('*.partial'):
        path.unlink()


def audit(root, output, recs, total, committed, chunks, chunk_rows, recovery):
    primary = output / 'mixed/classification_mixed_ProtT5_chunks'
    sources = sorted(root.resolve().rglob('master_index.csv'))
    expected = np.memmap(recovery / 'original_rows.bin', mode='w+', dtype=np.int64, shape=(total, 3))
    lookup, offsets, provenance = {}, [], []
    group_offset = 0
    manifests, secondary_offset, manifest_offset = [], 0, 0
    shape = dtype = columns = None
    for sid, source in enumerate(sources):
        sec = _find_secondary_dir(source.parent.parent)
        store = SecondaryBERTStore(sec, cache_size=1)
        manifest = store.manifest[['chunk_id','start','end','x_file']].copy()
        manifest['chunk_id'] = np.arange(manifest_offset,manifest_offset+len(manifest))
        manifest['start'] += secondary_offset
        manifest['end'] += secondary_offset
        manifest['x_file'] = [str((sec/path).resolve()) for path in manifest.x_file]
        if not all(Path(path).is_file() for path in manifest.x_file):
            raise ValueError('Missing original secondary embeddings')
        manifests.append(manifest)
        secondary_offset += len(store.global_group_ids)
        manifest_offset += len(manifest)
        offsets.append(group_offset)
        provenance.append(dict(id=sid, master_index=str(source), secondary=str(sec), group_id_offset=group_offset))
        expected_records = {cid: (start,n) for s,cid,start,n in recs if s == sid}
        seen_chunks = set()
        for cid, frame in iter_physical_chunks(source, 500000):
            start, n = expected_records[cid]
            if len(frame) != n or not np.array_equal(frame.row_idx_in_chunk, np.arange(n)):
                raise ValueError(f'Source changed: {source}, chunk {cid}')
            if columns is None:
                columns = list(frame.columns)
            if list(frame.columns) != columns or set(columns) != {'chunk_id','row_idx_in_chunk',*FIELDS}:
                raise ValueError('Unsupported or changed source columns')
            expected[start:start+n] = frame[FIELDS].to_numpy(dtype=np.int64)
            lookup[sid,cid] = (start,n)
            seen_chunks.add(cid)
            x = np.load(_resolve_primary_embedding_file(source.parent, cid), mmap_mode='r')
            if shape is None:
                shape, dtype = x.shape[1:], x.dtype
            if x.shape != (n,*shape) or x.dtype != dtype:
                raise ValueError('Inconsistent source embedding dimensions')
        if seen_chunks != set(expected_records):
            raise ValueError('Missing source chunks')
        gids = store.global_group_ids
        combined = output / 'mixed/classification_mixed_SecondaryBERT_by_group'
        # Verify every referenced secondary group against the existing combined store.
        combined_gids = np.load(combined / 'group_id.npy', mmap_mode='r')
        secondary_start = sum(len(SecondaryBERTStore(_find_secondary_dir(p.parent.parent), cache_size=1).global_group_ids) for p in sources[:sid])
        if not np.array_equal(combined_gids[secondary_start:secondary_start+len(gids)], gids+group_offset):
            raise ValueError('Combined secondary group mapping mismatch')
        group_offset += int(gids[-1])+1
        print(f'AUDIT source={sid} original metadata indexed; chunks={len(seen_chunks)}', flush=True)
    combined_manifest = pd.read_csv(output/'mixed/classification_mixed_SecondaryBERT_by_group/chunks_manifest.csv')
    pd.testing.assert_frame_equal(combined_manifest, pd.concat(manifests,ignore_index=True))
    if len(combined_gids) != secondary_offset:
        raise ValueError('Combined secondary group count mismatch')
    expected.flush()
    visited = np.memmap(recovery / 'visited.bin', mode='w+', dtype=np.uint8, shape=(total,))
    visited[:] = 0
    starts,sizes = address_tables(lookup)
    master = primary / 'master_index.csv'
    validated, valid_chunks, error = 0, 0, None
    output_columns = columns + ['source_dataset_id','source_chunk_id','source_row_idx_in_chunk','source_group_id']
    reader = pd.read_csv(master, chunksize=chunk_rows)
    try:
        for frame in reader:
            cid = valid_chunks
            if cid >= chunks:
                raise ValueError('Uncommitted CSV tail')
            if len(frame) != chunk_rows or list(frame.columns) != output_columns:
                raise ValueError('Incomplete CSV chunk or incorrect columns')
            if not (frame.chunk_id == cid).all() or not np.array_equal(frame.row_idx_in_chunk, np.arange(len(frame))):
                raise ValueError('Incorrect output chunk/row numbering')
            indices = row_indices(frame,starts,sizes)
            if len(np.unique(indices)) != len(indices) or visited[indices].any():
                raise ValueError('Duplicate original rows')
            original = expected[indices]
            if not np.array_equal(original[:,0], frame.y) or not np.array_equal(original[:,1], frame.protein_group_id):
                raise ValueError('Original label or protein identifier mismatch')
            sid = frame.source_dataset_id.to_numpy()
            if not np.array_equal(original[:,2], frame.source_group_id) or not np.array_equal(original[:,2]+np.asarray(offsets)[sid], frame.group_id):
                raise ValueError('Original/secondary group identifier mismatch')
            path = primary / f'chunk_{cid:06d}_X.npy'
            x = np.load(path, mmap_mode='r')
            if x.shape != (len(frame),*shape) or x.dtype != dtype:
                raise ValueError('Incomplete or incorrect embedding file')
            for i in sorted({0,len(frame)//2,len(frame)-1}):
                row = frame.iloc[i]
                source_x = np.load(_resolve_primary_embedding_file(sources[int(row.source_dataset_id)].parent, int(row.source_chunk_id)), mmap_mode='r')
                if not np.array_equal(x[i], source_x[int(row.source_row_idx_in_chunk)], equal_nan=True):
                    raise ValueError('Sampled embedding does not match its original row')
            visited[indices] = 1
            validated += len(frame)
            valid_chunks += 1
            if valid_chunks % 50 == 0:
                print(f'AUDIT output chunks={valid_chunks}/{chunks}, rows={validated:,}', flush=True)
    except (ValueError, KeyError, OSError, IndexError) as exc:
        error = str(exc)
        print(f'AUDIT invalid suffix starts at chunk={valid_chunks}: {error}', flush=True)
    finally:
        reader.close()
    if valid_chunks != chunks and error is None:
        error = 'CSV shorter than original log'
    checkpoint = dict(chunks=valid_chunks, emitted=validated, csv_bytes=csv_offset(master,validated))
    # The immutable bucket files must suffice to regenerate everything removed.
    first = min(int(p.stem) for p in (output/'_shuffle_work').glob('*.bin'))
    if error and valid_chunks == 0:
        raise ValueError('No valid prefix; refusing large automatic rollback: '+error)
    # Record exact validation scope; do not imply exhaustive embedding comparison.
    report = dict(rows=validated,chunks=valid_chunks,metadata='all rows compared to original; duplicate check',
                  embeddings='all shapes/dtypes; three full original vectors per chunk', invalid_suffix=error)
    atomic_json(recovery/'audit.json', report)
    if error:
        restore_checkpoint(primary,checkpoint)
    return checkpoint, lookup, expected, sources, offsets, provenance, shape, dtype, columns


def _run(root, output, log, chunk_rows=100000, buckets=1024, seed=42):
    output = output.resolve()
    recovery = output/'_recovery'
    recovery.mkdir(exist_ok=True)
    if not (output/'INCOMPLETE').exists():
        raise ValueError('Expected INCOMPLETE marker')
    recs,total,legacy_committed,legacy_chunks = records(log)
    primary = output/'mixed/classification_mixed_ProtT5_chunks'
    stage = output/'_shuffle_work'
    cp_path = recovery/'checkpoint.json'
    config_path = recovery/'config.json'
    rng = np.random.default_rng(seed)
    counts = np.zeros(buckets,dtype=np.int64)
    for sid,cid,start,n in recs:
        counts += np.bincount(rng.integers(buckets,size=n),minlength=buckets)
    partition_state = rng.bit_generator.state
    first = min(int(p.stem) for p in stage.glob('*.bin'))
    before = int(counts[:first].sum())
    if cp_path.exists():
        config = json.loads(config_path.read_text())
        cp = json.loads(cp_path.read_text())
        if config['total'] != total or config['seed'] != seed or config['buckets'] != buckets or config['chunk_rows'] != chunk_rows:
            raise ValueError('Recovery parameters changed')
        restore_checkpoint(primary,cp)
        shape,dtype = tuple(config['shape']),np.dtype(config['dtype'])
        provenance, columns = config['provenance'], config['columns']
    else:
        cp,lookup,expected,sources,offsets,provenance,shape,dtype,columns = audit(root,output,recs,total,legacy_committed,legacy_chunks,chunk_rows,recovery)
        carry_n = max(0,before-cp['emitted'])
        if carry_n:
            print(f'RECOVER lost buffered rows={carry_n:,}',flush=True)
            # Replay deleted bucket permutations to identify missing row addresses.
            wanted_by_bucket = {}
            cumulative = 0
            for b,n in enumerate(counts[:first]):
                order = rng.permutation(n)
                skip = max(0,cp['emitted']-cumulative)
                if skip < n:
                    wanted_by_bucket[b] = (order[skip:], cumulative+skip-cp['emitted'])
                cumulative += int(n)
            # Replay only RNG assignments; read selected embeddings from originals.
            address = np.empty((carry_n,3),dtype=np.int64)
            seen = np.zeros(buckets,dtype=np.int64)
            assign_rng = np.random.default_rng(seed)
            sorted_targets = {b: (np.sort(v[0]), np.argsort(v[0]), v[1]) for b,v in wanted_by_bucket.items()}
            for sid,cid,start,n in recs:
                assignment = assign_rng.integers(buckets,size=n)
                for b,(targets,order,base) in sorted_targets.items():
                    rows = np.flatnonzero(assignment == b)
                    left,right = np.searchsorted(targets,[seen[b],seen[b]+len(rows)])
                    if right > left:
                        selected = rows[targets[left:right]-seen[b]]
                        address[base+order[left:right],0] = sid
                        address[base+order[left:right],1] = cid
                        address[base+order[left:right],2] = selected
                    seen[b] += len(rows)
            carry_x = np.lib.format.open_memmap(recovery/'carry_X.npy',mode='w+',dtype=dtype,shape=(carry_n,*shape))
            carry_frame = pd.DataFrame(address,columns=ADDRESS)
            idx = np.empty(carry_n,dtype=np.int64)
            for (sid,cid),positions in carry_frame.groupby(ADDRESS[:2],sort=False).indices.items():
                start,n = lookup[sid,cid]
                rows = address[positions,2]
                idx[positions] = start+rows
                x = np.load(_resolve_primary_embedding_file(sources[sid].parent,cid),mmap_mode='r')
                carry_x[positions] = x[rows]
            values = expected[idx]
            for i,name in enumerate(FIELDS):
                carry_frame[name] = values[:,i]
            carry_frame['source_group_id'] = carry_frame.group_id
            carry_frame['group_id'] += np.asarray(offsets)[address[:,0]]
            carry_frame['chunk_id'] = 0
            carry_frame['row_idx_in_chunk'] = 0
            carry_frame = carry_frame[columns+ADDRESS+['source_group_id']]
            carry_frame.to_csv(recovery/'carry.csv',index=False)
            carry_x.flush()
            print(f'RECOVER saved buffered rows={carry_n:,}',flush=True)
        config = dict(total=total,seed=seed,buckets=buckets,chunk_rows=chunk_rows,base_emitted=cp['emitted'],
                      shape=list(shape),dtype=str(dtype),provenance=provenance,columns=columns,carry_n=carry_n)
        # Validate the complete remaining stream before writing any new chunk.
        starts,sizes = address_tables(lookup)
        visited = np.memmap(recovery/'visited.bin',mode='r+',dtype=np.uint8,shape=(total,))
        def check_remaining(frame,x,selection):
            frame = frame.iloc[selection]
            indices = row_indices(frame,starts,sizes)
            if len(np.unique(indices)) != len(indices) or visited[indices].any():
                raise ValueError('Duplicate row in pending recovery stream')
            values = expected[indices]
            if not np.array_equal(values[:,0],frame.y) or not np.array_equal(values[:,1],frame.protein_group_id):
                raise ValueError('Pending row label or protein mismatch')
            if not np.array_equal(values[:,2],frame.source_group_id) or not np.array_equal(values[:,2]+np.asarray(offsets)[frame.source_dataset_id.to_numpy()],frame.group_id):
                raise ValueError('Pending group mapping mismatch')
            for i in sorted({0,len(frame)//2,len(frame)-1}) if len(frame) else []:
                row = frame.iloc[i]
                original_x = np.load(_resolve_primary_embedding_file(sources[int(row.source_dataset_id)].parent,int(row.source_chunk_id)),mmap_mode='r')
                if not np.array_equal(x[selection[i]],original_x[int(row.source_row_idx_in_chunk)],equal_nan=True):
                    raise ValueError('Pending sampled embedding mismatch')
            visited[indices] = 1
            return len(frame)
        checked = cp['emitted']
        if carry_n:
            f = pd.read_csv(recovery/'carry.csv')
            checked += check_remaining(f,np.load(recovery/'carry_X.npy',mmap_mode='r'),np.arange(len(f)))
        rng.bit_generator.state = partition_state
        for b,n in enumerate(counts):
            order = rng.permutation(n)
            if b < first:
                continue
            prefix = stage/f'{b:06d}'
            f = pd.read_csv(prefix.with_suffix('.csv'))
            if len(f) != n:
                raise ValueError(f'Incomplete pending CSV bucket {b}')
            x = np.memmap(prefix.with_suffix('.bin'),mode='r',dtype=dtype,shape=(int(n),*shape))
            skip = max(0,cp['emitted']-before) if b == first else 0
            checked += check_remaining(f,x,order[skip:])
            print(f'AUDIT pending bucket={b}, total accounted rows={checked:,}/{total:,}',flush=True)
        if checked != total or not visited.all():
            raise ValueError('Missing original rows in complete recovery stream')
        report = json.loads((recovery/'audit.json').read_text())
        report.update(pending_rows=total-cp['emitted'],total_rows=total,all_original_rows_accounted_once=True,secondary_manifest='verified against originals')
        atomic_json(recovery/'audit.json',report)
        atomic_json(config_path,config)
        atomic_json(cp_path,cp)
        restore_checkpoint(primary,cp)
        del expected
    for b in range(first,buckets):
        prefix = stage/f'{b:06d}'
        if prefix.with_suffix('.bin').stat().st_size != int(counts[b])*int(np.prod(shape))*dtype.itemsize:
            raise ValueError(f'Incomplete bucket {b}')
    # Repeatable immutable stream starts with recovered carry, then surviving buckets.
    def stream():
        if config['carry_n']:
            yield pd.read_csv(recovery/'carry.csv'),np.load(recovery/'carry_X.npy',mmap_mode='r'),np.arange(config['carry_n'])
        rng.bit_generator.state = partition_state
        for b,n in enumerate(counts):
            order = rng.permutation(n)
            if b < first:
                continue
            prefix = stage/f'{b:06d}'
            frame = pd.read_csv(prefix.with_suffix('.csv'))
            if len(frame) != n:
                raise ValueError(f'Bucket {b} metadata count mismatch')
            x = np.memmap(prefix.with_suffix('.bin'),mode='r',dtype=dtype,shape=(int(n),*shape))
            skip = max(0,config['base_emitted']-before) if b == first else 0
            yield frame,x,order[skip:]
    skip = cp['emitted']-config['base_emitted']
    pending_x,pending_f,pending_n = [],[],0
    master = primary/'master_index.csv'
    def emit():
        nonlocal cp,pending_x,pending_f,pending_n
        frame = pd.concat(pending_f,ignore_index=True)
        frame['chunk_id'] = cp['chunks']
        frame['row_idx_in_chunk'] = np.arange(pending_n)
        target = primary/f"chunk_{cp['chunks']:06d}_X.npy"
        temp = target.with_suffix('.partial')
        with temp.open('wb') as handle:
            np.save(handle,np.concatenate(pending_x))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp,target)
        with master.open('a') as handle:
            frame.to_csv(handle,index=False,header=False)
            handle.flush()
            os.fsync(handle.fileno())
        cp = dict(chunks=cp['chunks']+1,emitted=cp['emitted']+pending_n,csv_bytes=master.stat().st_size)
        atomic_json(cp_path,cp)
        print(f"WRITE chunk={cp['chunks']-1} rows={pending_n:,} total={cp['emitted']:,}",flush=True)
        pending_x,pending_f,pending_n = [],[],0
    print(f"RESUME audit passed; next chunk={cp['chunks']}, committed={cp['emitted']:,}",flush=True)
    for frame,x,order in stream():
        if skip >= len(order):
            skip -= len(order)
            continue
        cursor,skip = skip,0
        while cursor < len(order):
            take = min(chunk_rows-pending_n,len(order)-cursor)
            rows = order[cursor:cursor+take]
            pending_x.append(np.array(x[rows]))
            pending_f.append(frame.iloc[rows].copy())
            pending_n += take
            cursor += take
            if pending_n == chunk_rows:
                emit()
    if pending_n:
        emit()
    if cp['emitted'] != total:
        raise ValueError('Final row count mismatch')
    atomic_json(output/'reorder_manifest.json',dict(seed=seed,buckets=buckets,chunk_rows=chunk_rows,rows=total,
        chunks=cp['chunks'],sources=provenance,secondary_storage='absolute references to original embeddings'))
    (output/'INCOMPLETE').unlink()
    print('COMPLETE; immutable recovery buckets retained',flush=True)


def run(root, output, log, chunk_rows=100000, buckets=1024, seed=42):
    recovery = output.resolve()/'_recovery'
    recovery.mkdir(exist_ok=True)
    with (recovery/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _run(root,output,log,chunk_rows,buckets,seed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--log',type=Path,required=True)
    args = parser.parse_args()
    run(args.root,args.output,args.log)
