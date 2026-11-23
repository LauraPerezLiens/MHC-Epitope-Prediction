#!/usr/bin/env python3
"""Find identical 25aa sequences carrying opposite labels; retain every source column.

Run from anywhere with nap_env. Outputs one CSV of all conflicting source rows,
a JSON summary and a resumable SQLite counting index. This does NOT establish
identity of embeddings. Local IDs are scoped to source_file; global_group_id
uses the actual shuffle manifest (never an inferred offset).
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tarfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def extract_sources(archive, target):
    """Extract only classification CSVs, atomically, without extracting embeddings."""
    proc = subprocess.Popen(['zstd', '-qdc', str(archive)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=proc.stdout, mode='r|') as tar:
            for member in tar:
                path = Path(member.name)
                if (not member.isfile() or not path.name.startswith('classification_')
                        or not path.name.endswith('.csv')
                        or path.name.endswith(('_blosum.csv', '_ss.csv'))):
                    continue
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError(f'Unsafe archive path: {path}')
                parts = path.parts
                if parts and parts[0] == 'data_intermediate':
                    path = Path(*parts[1:])
                dest = target / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                partial = dest.with_suffix('.partial')
                with tar.extractfile(member) as src, partial.open('wb') as dst:
                    while block := src.read(4 * 1024 * 1024):
                        dst.write(block)
                os.replace(partial, dest)
        if proc.wait() != 0:
            raise RuntimeError('zstd extraction failed')
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    run_lock = (args.output / '.run.lock').open('a')
    fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not args.sources.exists():
        extract_sources(args.archive, args.sources)
    files = sorted(p for p in args.sources.rglob('classification_*.csv')
                   if not p.name.endswith(('_blosum.csv', '_ss.csv')))
    if not files:
        raise ValueError(f'No classification CSVs in {args.sources}')
    manifest = json.loads(args.manifest.read_text())
    mapping = {}
    for source in manifest['sources']:
        parts = Path(source['master_index']).parts
        # The last four components are species / MHC class / family / store.
        mapping[tuple(parts[-5:-2])] = source
    signatures = [(str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns) for p in files]
    identity = json.dumps({'files': signatures, 'batch_rows': args.batch_rows,
                           'manifest': manifest}, sort_keys=True)
    db = sqlite3.connect(args.output / 'index.sqlite')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA cache_size=-131072')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS config (identity TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS counts (
            sequence TEXT PRIMARY KEY, negative INTEGER NOT NULL,
            positive INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS completed (
            source TEXT, batch INTEGER, rows INTEGER,
            PRIMARY KEY(source,batch)) WITHOUT ROWID;
    ''')
    saved = db.execute('SELECT identity FROM config').fetchone()
    if saved and saved[0] != identity:
        raise ValueError('Inputs or batch size changed; use a new --output directory')
    if not saved:
        with db:
            db.execute('INSERT INTO config VALUES (?)', (identity,))
    original_columns = list(pd.read_csv(files[0], nrows=0).columns)
    required = {'25aa_seq', 'contains_epitope', 'group_id', 'protein_group_id', 'protein_url'}
    if not required.issubset(original_columns):
        raise ValueError(f'Missing columns: {required - set(original_columns)}')
    # Each batch and its counts commit together, allowing restart after interruption.
    for path in files:
        rel = path.relative_to(args.sources).as_posix()
        if tuple(path.relative_to(args.sources).parts[:3]) not in mapping:
            raise ValueError(f'Source not present in shuffle manifest: {rel}')
        if list(pd.read_csv(path, nrows=0).columns) != original_columns:
            raise ValueError(f'Inconsistent columns: {path}')
        done = {r[0] for r in db.execute('SELECT batch FROM completed WHERE source=?', (rel,))}
        for batch, frame in enumerate(pd.read_csv(path, chunksize=args.batch_rows,
                                                  keep_default_na=False)):
            if batch in done:
                continue
            if not frame.contains_epitope.isin([0, 1]).all():
                raise ValueError(f'Nonbinary labels: {rel}, batch {batch}')
            grouped = frame.groupby(['25aa_seq', 'contains_epitope']).size()
            records = [(str(seq), int(n) if label == 0 else 0,
                        int(n) if label == 1 else 0) for (seq, label), n in grouped.items()]
            with db:
                db.executemany('''INSERT INTO counts VALUES (?,?,?)
                    ON CONFLICT(sequence) DO UPDATE SET
                    negative=negative+excluded.negative,
                    positive=positive+excluded.positive''', records)
                db.execute('INSERT INTO completed VALUES (?,?,?)', (rel, batch, len(frame)))
            print(f'COUNT {rel} batch={batch} rows={len(frame):,}', flush=True)
    db.execute('CREATE TEMP TABLE requested (sequence TEXT PRIMARY KEY) WITHOUT ROWID')
    partial = args.output / 'contradictions.csv.partial'
    exported = 0
    per_source = {}
    with partial.open('w') as dst:
        header = True
        for path in files:
            relpath = path.relative_to(args.sources)
            rel = relpath.as_posix()
            species, mhc_class, family = relpath.parts[:3]
            source = mapping[(species, mhc_class, family)]
            source_rows = 0
            per_source[rel] = 0
            for frame in pd.read_csv(path, chunksize=args.batch_rows, keep_default_na=False):
                db.execute('DELETE FROM requested')
                db.executemany('INSERT INTO requested VALUES (?)',
                               ((str(s),) for s in frame['25aa_seq'].unique()))
                hits = pd.read_sql_query('''SELECT c.sequence AS "25aa_seq",
                    c.negative AS sequence_negative_rows, c.positive AS sequence_positive_rows
                    FROM requested r JOIN counts c ON c.sequence=r.sequence
                    WHERE c.negative>0 AND c.positive>0''', db)
                frame['source_row_index'] = range(source_rows, source_rows + len(frame))
                source_rows += len(frame)
                selected = frame.merge(hits, on='25aa_seq', how='inner', validate='many_to_one')
                selected['source_file'] = rel
                selected['species'] = species
                selected['mhc_class'] = mhc_class
                selected['mhc_family'] = family
                selected['source_dataset_id'] = source['id']
                selected['global_group_id'] = selected.group_id + source['group_id_offset']
                selected['protein_accession'] = selected.protein_url.str.rstrip('/').str.rsplit('/', n=1).str[-1]
                selected['protein_key'] = rel + ':protein:' + selected.protein_group_id.astype(str)
                selected['group_key'] = rel + ':group:' + selected.group_id.astype(str)
                selected.to_csv(dst, index=False, header=header)
                header = False
                exported += len(selected)
                per_source[rel] += len(selected)
            print(f'EXPORT {rel} contradictory_rows={per_source[rel]:,}', flush=True)
    unique, conflicts, conflict_rows = db.execute('''SELECT COUNT(*),
        COALESCE(SUM(negative>0 AND positive>0),0),
        COALESCE(SUM(CASE WHEN negative>0 AND positive>0 THEN negative+positive ELSE 0 END),0)
        FROM counts''').fetchone()
    if exported != conflict_rows:
        partial.unlink()
        raise ValueError(f'Export count mismatch: {exported} != {conflict_rows}')
    os.replace(partial, args.output / 'contradictions.csv')
    summary = {'status': 'completed', 'criterion': 'identical_25aa_sequence_opposite_labels',
               'embeddings_compared': False, 'sources': len(files),
               'original_rows': db.execute('SELECT SUM(rows) FROM completed').fetchone()[0],
               'unique_sequences': unique, 'contradictory_sequences': conflicts,
               'contradictory_rows': exported, 'rows_by_source': per_source,
               'id_scope': 'group_id and protein_group_id are local to source_file; global_group_id uses shuffle offsets',
               'row_index_convention': 'source_row_index is zero-based, excluding the CSV header',
               'note': 'Opposite annotations do not by themselves prove mislabelling.'}
    tmp = args.output / 'summary.json.partial'
    tmp.write_text(json.dumps(summary, indent=2) + '\n')
    os.replace(tmp, args.output / 'summary.json')
    db.commit()
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    db.close()
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, default=ROOT / 'data/used_data/contradiction_sources')
    parser.add_argument('--archive', type=Path, default=ROOT / 'data/used_data/data_intermediate.tar.zst')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/data_input_nn_shuffled_concatenate/reorder_manifest.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/data_contradictions')
    parser.add_argument('--batch-rows', type=int, default=200000)
    options = parser.parse_args()
    if options.batch_rows <= 0:
        parser.error('--batch-rows must be positive')
    run(options)
