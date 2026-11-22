"""Run with python -m examples.benchmark_block_reader on Linux."""

import json
from pathlib import Path
import random
import statistics
import tempfile
from time import perf_counter

import numpy as np

from data_pipeline.block_reader import Block, BlockReader, RowRange


def main():
    block_count, rows, width, stride = 8, 4096, 32, 64
    with tempfile.TemporaryDirectory() as directory:
        array = np.arange(rows * width, dtype=np.float32).reshape(rows, width)
        blocks = []
        for block_id in range(block_count):
            path = Path(directory) / f"{block_id}.npy"
            np.save(path, array)
            blocks.append(Block(block_id, path, array.shape, array.dtype.str))
        sequential = [RowRange(block.block_id, offset, stride)
                      for block in blocks for offset in range(0, rows, stride)]
        shuffled = sequential.copy()
        random.Random(42).shuffle(shuffled)
        result = {}
        with BlockReader(blocks) as reader:
            started = perf_counter()
            for _ in range(8):
                for block in blocks:
                    reader.validate(block.block_id)
            result["mean_open_validate_us"] = (perf_counter() - started) * 1e6 / (8 * len(blocks))
        catalog = {block.block_id: block for block in blocks}
        started = perf_counter()
        for _ in range(128):
            for span in shuffled:
                catalog[span.block_id]
        result["mean_index_lookup_us"] = (perf_counter() - started) * 1e6 / (128 * len(shuffled))
        for order, spans in (("sequential", sequential), ("random", shuffled)):
            for cache in (0, 4):
                rates, latencies = [], []
                for _ in range(3):
                    with BlockReader(blocks, max_open=cache, max_bytes=stride * width * 4) as reader:
                        started = perf_counter()
                        for span in spans:
                            before = perf_counter()
                            reader.read(span)
                            latencies.append((perf_counter() - before) * 1e6)
                        rates.append(len(spans) * stride / (perf_counter() - started))
                result[f"{order}_cache_{cache}"] = {
                    "rows_per_second": round(statistics.median(rates)),
                    "median_range_us": round(statistics.median(latencies), 2),
                }
        block_latencies = []
        with BlockReader(blocks, max_open=4, max_bytes=array.nbytes) as reader:
            for _ in range(3):
                for block in blocks:
                    started = perf_counter()
                    reader.read(RowRange(block.block_id, 0, rows))
                    block_latencies.append((perf_counter() - started) * 1e6)
        result["median_full_block_us"] = round(statistics.median(block_latencies), 2)
        # VmHWM measures this process image, including the Python and NumPy baseline.
        status = Path("/proc/self/status").read_text()
        peak = next(line for line in status.splitlines() if line.startswith("VmHWM:"))
        result["peak_rss_mib"] = round(int(peak.split()[1]) / 1024, 2)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
