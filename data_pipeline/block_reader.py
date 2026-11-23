"""Bounded, read-only access to fixed-width rows in C-order NPY blocks."""

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import logging
from math import prod
from numbers import Integral
import os
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator

import numpy as np


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Block:
    block_id: int
    path: Path
    shape: tuple[int, ...]
    dtype: str
    sha256: str | None = None


@dataclass(frozen=True)
class RowRange:
    block_id: int
    offset: int
    count: int


def _row_bytes(shape: tuple[int, ...], dtype: np.dtype) -> int:
    return dtype.itemsize * prod(int(width) for width in shape[1:])


class BlockReader:
    """Use as a context manager. Each batch owns at most max_bytes of payload.

    Callers must release consumed batches to bound total retained payload.
    Files are assumed immutable for the lifetime of a reader.
    """

    def __init__(self, blocks: Iterable[Block], *, max_bytes: int = 1 << 20,
                 max_open: int = 4):
        if (not isinstance(max_bytes, Integral) or not isinstance(max_open, Integral)
                or max_bytes < 1 or max_open < 0):
            raise ValueError("invalid byte or file limit")
        self._blocks = {}
        for block in blocks:
            if block.block_id in self._blocks:
                LOG.error("duplicate block ID %s", block.block_id)
                raise ValueError(f"duplicate block ID {block.block_id}")
            self._blocks[block.block_id] = block
        self.max_bytes = int(max_bytes)
        self.max_open = int(max_open)
        self._files: OrderedDict[int, tuple[BinaryIO, int, int]] = OrderedDict()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        while self._files:
            _, (file, _, _) = self._files.popitem()
            file.close()

    @staticmethod
    def _open(block: Block) -> tuple[BinaryIO, int, int]:
        file = block.path.open("rb", buffering=0)
        try:
            version = np.lib.format.read_magic(file)
            if version == (1, 0):
                length_size = 2
                read_header = np.lib.format.read_array_header_1_0
            elif version == (2, 0):
                length_size = 4
                read_header = np.lib.format.read_array_header_2_0
            else:
                raise ValueError(f"unsupported NPY version {version}")
            length_position = file.tell()
            length = file.read(length_size)
            if len(length) != length_size or int.from_bytes(length, "little") > 10_000:
                raise ValueError("invalid or oversized NPY header")
            file.seek(length_position)
            shape, fortran, dtype = read_header(file)
            if (not shape or any(size < 0 for size in shape)
                    or fortran or dtype.kind not in "biufc" or dtype.itemsize < 1):
                raise ValueError("expected a C-order numeric array with a row axis")
            if shape != block.shape or dtype != np.dtype(block.dtype):
                raise ValueError("shape or dtype differs from manifest")
            row_bytes = _row_bytes(shape, dtype)
            start = file.tell()
            if not row_bytes or os.fstat(file.fileno()).st_size != start + shape[0] * row_bytes:
                raise ValueError("invalid row size or incomplete/inconsistent NPY payload")
            return file, start, row_bytes
        except BaseException:
            file.close()
            raise

    def _resolve(self, span: RowRange) -> Block:
        if not all(isinstance(value, Integral)
                   for value in (span.block_id, span.offset, span.count)):
            raise ValueError("block ID, offset and count must be integers")
        block = self._blocks.get(span.block_id)
        if block is None:
            raise ValueError(f"unknown block ID {span.block_id}")
        if (not block.shape or span.offset < 0 or span.count < 0
                or int(span.offset) + int(span.count) > block.shape[0]):
            raise ValueError(f"range outside block {span.block_id}: {span}")
        return block

    def _read(self, block: Block, offset: int, count: int) -> np.ndarray:
        entry = self._files.get(block.block_id)
        row_bytes = entry[2] if entry is not None else _row_bytes(block.shape, np.dtype(block.dtype))
        size = count * row_bytes
        if size > self.max_bytes:
            raise ValueError("range exceeds max_bytes; use batches")
        if entry is None:
            if self.max_open and len(self._files) == self.max_open:
                _, (old_file, _, _) = self._files.popitem(last=False)
                old_file.close()
            entry = self._open(block)
        file, start, row_bytes = entry
        if self.max_open:
            self._files[block.block_id] = entry
            self._files.move_to_end(block.block_id)
        try:
            file.seek(start + offset * row_bytes)
            payload = file.read(size)
            if len(payload) != size:
                raise OSError("short read")
            return np.frombuffer(payload, dtype=block.dtype).reshape((count, *block.shape[1:]))
        finally:
            if not self.max_open:
                file.close()

    def read(self, span: RowRange) -> np.ndarray:
        try:
            return self._read(self._resolve(span), int(span.offset), int(span.count))
        except (OSError, ValueError, EOFError, TypeError) as exc:
            LOG.error("read failed for %s: %s", span, exc)
            raise

    def batches(self, spans: Iterable[RowRange], batch_rows: int) -> Iterator[np.ndarray]:
        if not isinstance(batch_rows, Integral) or batch_rows < 1:
            raise ValueError("batch_rows must be positive")
        for span in spans:
            try:
                block = self._resolve(span)
                row_bytes = _row_bytes(block.shape, np.dtype(block.dtype))
                step = min(batch_rows, self.max_bytes // row_bytes) if row_bytes else 0
                if step < 1:
                    raise ValueError("invalid row size for max_bytes")
            except (ValueError, TypeError) as exc:
                LOG.error("invalid batch range %s: %s", span, exc)
                raise
            if span.count == 0:
                self.read(span)
            stop = int(span.offset) + int(span.count)
            for offset in range(int(span.offset), stop, step):
                yield self.read(RowRange(span.block_id, offset, min(step, stop - offset)))

    def validate(self, block_id: int, *, verify_checksum: bool = False) -> None:
        """Check header and exact file size, optionally streaming the full SHA-256."""
        try:
            block = self._blocks.get(block_id)
            if block is None:
                raise ValueError(f"unknown block ID {block_id}")
            file, _, _ = self._open(block)
            with file:
                if verify_checksum:
                    if block.sha256 is None:
                        raise ValueError("manifest lacks SHA-256")
                    file.seek(0)
                    digest = hashlib.sha256()
                    for part in iter(lambda: file.read(min(self.max_bytes, 1 << 20)), b""):
                        digest.update(part)
                    if digest.hexdigest() != block.sha256.lower():
                        raise ValueError("SHA-256 mismatch")
        except (OSError, ValueError, EOFError, TypeError) as exc:
            LOG.error("validation failed for block %s: %s", block_id, exc)
            raise
