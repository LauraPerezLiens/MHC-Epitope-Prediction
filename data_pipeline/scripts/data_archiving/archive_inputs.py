#!/usr/bin/env python3
"""Compress source files with zstd, verify decompressed SHA-256, then remove originals."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def signature(path):
    st = path.stat()
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns]


def atomic_json(path, record):
    tmp = path.with_name(path.name + '.partial')
    with tmp.open('w') as f:
        json.dump(record, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    sync_dir(path.parent)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def decompressed_digest(path, zstd):
    h = hashlib.sha256()
    with subprocess.Popen([zstd, '-q', '-d', '-c', str(path)], stdout=subprocess.PIPE) as proc:
        for block in iter(lambda: proc.stdout.read(8 * 1024 * 1024), b''):
            h.update(block)
        if proc.wait() != 0:
            raise RuntimeError(f'Archive decompression failed: {path}')
    return h.hexdigest()


def archive_file(path, zstd='zstd', threads=1):
    """Idempotent across crashes; never unlink until verified and durably recorded."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f'Refusing to archive symlink: {path}')
    target = path.with_name(path.name + '.zst')
    record_path = path.with_name(path.name + '.archive.json')
    if not path.exists():
        if not target.is_file() or not record_path.is_file():
            raise FileNotFoundError(f'Missing original and verified archive: {path}')
        record = json.loads(record_path.read_text())
        if target.stat().st_size != record['compressed_bytes'] or digest(target) != record['archive_sha256']:
            raise ValueError(f'Archive checksum mismatch: {target}')
        return record
    before = signature(path)
    original_hash = digest(path)
    if target.exists():
        if decompressed_digest(target, zstd) != original_hash:
            raise ValueError(f'Existing archive differs from original: {target}')
    else:
        if shutil.disk_usage(path.parent).free < before[2] + 1024 * 1024:
            raise OSError(f'Insufficient space to archive {path}')
        fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.zst.partial', dir=path.parent)
        os.close(fd)
        temporary = Path(name)
        try:
            subprocess.run([zstd, '-q', '-f', '-1', f'-T{threads}', str(path), '-o', str(temporary)], check=True)
            if decompressed_digest(temporary, zstd) != original_hash:
                raise ValueError(f'Archive verification failed: {path}')
            with temporary.open('rb') as f:
                os.fsync(f.fileno())
            if signature(path) != before:
                raise ValueError(f'Original changed during archiving: {path}')
            os.replace(temporary, target)
            sync_dir(path.parent)
        finally:
            temporary.unlink(missing_ok=True)
    if signature(path) != before:
        raise ValueError(f'Original changed during archiving: {path}')
    record = {'original_bytes': before[2], 'original_sha256': original_hash,
              'compressed_bytes': target.stat().st_size, 'archive_sha256': digest(target),
              'source_signature': before, 'format': 'verified_zstd_v1'}
    atomic_json(record_path, record)
    if signature(path) != before:
        raise ValueError(f'Original changed before removal: {path}')
    path.unlink()
    sync_dir(path.parent)
    return record


def archive_tree(root, zstd='zstd', threads=1):
    root = Path(root)
    # A tree-level completion marker is only published after every retained file
    # has a verified compressed counterpart. Existing archives are revalidated.
    files = sorted(p for p in root.rglob('*') if p.is_file() or p.is_symlink())
    count = original_bytes = compressed_bytes = 0
    for p in files:
        if p.name.endswith(('.zst', '.archive.json', '.lock')) or p.name in ('lock', 'ARCHIVED.json'):
            continue
        if '.partial' in p.name:
            raise ValueError(f'Unfinished source file requires inspection: {p}')
        rec = archive_file(p, zstd, threads)
        count += 1
        original_bytes += rec['original_bytes']
        compressed_bytes += rec['compressed_bytes']
        print(f'ARCHIVE {p} original={rec["original_bytes"]:,} compressed={rec["compressed_bytes"]:,}', flush=True)
    for p in root.rglob('*.archive.json'):
        original = p.with_name(p.name[:-len('.archive.json')])
        if not original.exists():
            archive_file(original, zstd, threads)
    atomic_json(root / 'ARCHIVED.json', {'format': 'verified_zstd_tree_v1', 'complete': True,
                                         'files_compressed_this_run': count,
                                         'original_bytes_this_run': original_bytes,
                                         'compressed_bytes_this_run': compressed_bytes})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--zstd', default=shutil.which('zstd') or 'zstd')
    parser.add_argument('--threads', type=int, default=1)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error('threads must be positive')
    archive_tree(args.root, args.zstd, args.threads)


if __name__ == '__main__':
    main()
