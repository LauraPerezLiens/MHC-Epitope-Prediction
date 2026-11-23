#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Memory-optimized SecondaryBERT MLM training.

Key properties
--------------
- Reads Parquet incrementally with PyArrow; no HuggingFace Dataset.map().
- Never materializes the ~50M training windows.
- Generates up to 3 deterministic, non-overlapping 25-state windows/protein.
- Converts C/H/E directly to token IDs (C=5, H=6, E=7).
- Dynamic MLM masking is performed batch-by-batch.
- DDP: each rank gets disjoint bounded Parquet work units.
- Work units are greedily balanced across ranks using cached window counts.
- DataLoader workers split the rank's row groups again, without duplication.
- Fixed-size sequences (27 tokens) are stacked directly; no padding.
- fp16 on CUDA.
- Resource monitor reports system RAM, process-tree RSS, VRAM, GPU utilization,
  and temperature from global rank 0.
- Scientific model configuration is unchanged from the previous script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import random
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Sequence, Tuple

import psutil
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.optim import AdamW
from torch.utils.data import DataLoader, IterableDataset, get_worker_info
if TYPE_CHECKING:
    from transformers import BertForMaskedLM, BertTokenizer


try:
    import pynvml
except ImportError:
    pynvml = None


# =====================================================================
# Configuration
# =====================================================================

WINDOW_SIZE = 25
MAX_WINDOWS_PER_PROTEIN = 3
SEQUENCE_LENGTH = WINDOW_SIZE + 2  # [CLS] + 25 C/H/E + [SEP]
MAX_LEN = 30

MLM_PROBABILITY = 0.15
HIDDEN_SIZE = 768
NUM_LAYERS = 12
NUM_HEADS = 12
INTERMEDIATE_SIZE = 3072

BATCH_SIZE = 256
NUM_EPOCHS = 1
LEARNING_RATE = 1e-4
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.05
RANDOM_SEED = 42

# Direct token mapping: identical to vocab.txt.
PAD_ID = 0
UNK_ID = 1
CLS_ID = 2
SEP_ID = 3
MASK_ID = 4
STATE_TO_ID = {"C": 5, "H": 6, "E": 7}
VOCAB_SIZE = 8

REQUIRED_COLUMN = "secondary_structure_spaced"


# =====================================================================
# Logging / distributed helpers
# =====================================================================

def setup_logging(rank: int) -> None:
    level = logging.INFO if rank == 0 else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def get_dist_info() -> Tuple[int, int, int]:
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    return rank, local_rank, world_size


def init_distributed() -> Tuple[int, int, int, torch.device]:
    rank, local_rank, world_size = get_dist_info()

    if torch.cuda.is_available():
        torch.cuda.set_device(local_rank)
        device = torch.device("cuda", local_rank)
    else:
        device = torch.device("cpu")

    if world_size > 1 and not dist.is_initialized():
        backend = "nccl" if torch.cuda.is_available() else "gloo"
        dist.init_process_group(
            backend=backend,
            device_id=device if backend == "nccl" else None,
        )

    return rank, local_rank, world_size, device


def barrier() -> None:
    if dist.is_initialized():
        dist.barrier()


def cleanup_distributed() -> None:
    if dist.is_initialized():
        dist.destroy_process_group()


# =====================================================================
# Arguments
# =====================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Memory-optimized SecondaryBERT MLM training."
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[3] / 'data' / 'data_uniref50',
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[3] / 'model' / 'secondary_bert',
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--num-epochs", type=int, default=NUM_EPOCHS)
    parser.add_argument("--learning-rate", type=float, default=LEARNING_RATE)
    parser.add_argument("--warmup-ratio", type=float, default=WARMUP_RATIO)
    parser.add_argument("--mlm-probability", type=float, default=MLM_PROBABILITY)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)

    parser.add_argument(
        "--parquet-batch-rows",
        type=int,
        default=8192,
        help="Rows read from Parquet at a time. Memory stays bounded.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help=(
            "DataLoader workers per rank. Start with 0: PyArrow already performs "
            "efficient batched I/O and extra workers increase RAM."
        ),
    )
    parser.add_argument(
        "--prefetch-factor",
        type=int,
        default=2,
        help="DataLoader prefetch factor when --num-workers > 0.",
    )
    parser.add_argument(
        "--monitor-interval",
        type=float,
        default=30.0,
    )
    parser.add_argument(
        "--logging-steps",
        type=int,
        default=100,
    )

    # Test/debug limits. Limits refer to source proteins, before windowing.
    parser.add_argument("--max-train-proteins", type=int, default=None)
    parser.add_argument("--max-val-proteins", type=int, default=None)

    parser.add_argument(
        "--stats-cache",
        type=Path,
        default=None,
        help=(
            "Optional row-group statistics JSON. Default: "
            "<dataset-dir>/secondary_mlm_rowgroup_stats.json"
        ),
    )
    parser.add_argument(
        "--rebuild-stats",
        action="store_true",
        help="Force rebuilding cached row-group window counts.",
    )
    parser.add_argument(
        "--skip-validation-sanity",
        action="store_true",
        help="Do not stream validation examples for the startup sanity check.",
    )
    parser.add_argument(
        "--sanity-examples",
        type=int,
        default=1000,
        help="Number of generated train examples checked before training.",
    )

    return parser.parse_args()


# =====================================================================
# Tokenizer validation
# =====================================================================

def build_tokenizer(vocab_file: Path) -> BertTokenizer:
    from transformers import BertTokenizer

    tokenizer = BertTokenizer(
        vocab=str(vocab_file),
        do_lower_case=False,
        unk_token="[UNK]",
        sep_token="[SEP]",
        pad_token="[PAD]",
        cls_token="[CLS]",
        mask_token="[MASK]",
    )

    expected_vocab = {
        "[PAD]": 0,
        "[UNK]": 1,
        "[CLS]": 2,
        "[SEP]": 3,
        "[MASK]": 4,
        "C": 5,
        "H": 6,
        "E": 7,
    }

    if tokenizer.vocab_size != len(expected_vocab):
        raise RuntimeError(
            f"Invalid tokenizer vocabulary size: {tokenizer.vocab_size}"
        )

    for token, expected_id in expected_vocab.items():
        actual = tokenizer.convert_tokens_to_ids(token)
        if actual != expected_id:
            raise RuntimeError(
                f"Invalid tokenizer mapping for {token!r}: "
                f"expected {expected_id}, got {actual}"
            )

    expected_ids = [2, 5, 6, 7, 5, 3]
    observed = tokenizer(
        "C H E C",
        add_special_tokens=True,
    )["input_ids"]

    if observed != expected_ids:
        raise RuntimeError(
            f"Tokenizer sanity check failed: expected {expected_ids}, "
            f"got {observed}"
        )

    logging.info(
        "Tokenizer sanity check PASSED: 'C H E C' -> %s",
        observed,
    )
    return tokenizer


# =====================================================================
# Deterministic windows
# =====================================================================

def deterministic_seed(
    global_seed: int,
    split_name: str,
    example_index: int,
) -> int:
    key = f"{global_seed}:{split_name}:{example_index}"
    digest = hashlib.blake2b(
        key.encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, byteorder="little", signed=False)


def clean_secondary_structure(ss_spaced: Optional[str]) -> str:
    if ss_spaced is None:
        return ""

    # Faster than split/join and preserves the previous semantics.
    ss = ss_spaced.replace(" ", "").strip()
    if not ss:
        return ""

    invalid = set(ss) - STATE_TO_ID.keys()
    if invalid:
        raise ValueError(
            f"Invalid secondary-structure states: {sorted(invalid)}"
        )
    return ss


def number_of_windows_from_clean_length(length: int) -> int:
    if length < WINDOW_SIZE:
        return 0
    return min(MAX_WINDOWS_PER_PROTEIN, length // WINDOW_SIZE)


def select_window_starts(
    length: int,
    example_index: int,
    split_name: str,
    global_seed: int,
) -> List[int]:
    n_windows = number_of_windows_from_clean_length(length)
    if n_windows == 0:
        return []

    rng = random.Random(
        deterministic_seed(
            global_seed=global_seed,
            split_name=split_name,
            example_index=example_index,
        )
    )

    occupied = n_windows * WINDOW_SIZE
    slack = length - occupied

    if n_windows == 1:
        return [rng.randint(0, slack)]

    cuts = sorted(
        rng.randint(0, slack)
        for _ in range(n_windows)
    )
    points = [0] + cuts + [slack]
    gaps = [
        points[i + 1] - points[i]
        for i in range(len(points) - 1)
    ]

    starts = []
    current = gaps[0]

    for i in range(n_windows):
        starts.append(current)
        current += WINDOW_SIZE
        if i + 1 < len(gaps):
            current += gaps[i + 1]

    return starts


def encode_window_direct(window: str) -> torch.Tensor:
    if len(window) != WINDOW_SIZE:
        raise RuntimeError(
            f"Window length must be {WINDOW_SIZE}, got {len(window)}"
        )

    ids = [CLS_ID]
    try:
        ids.extend(STATE_TO_ID[state] for state in window)
    except KeyError as exc:
        raise ValueError(f"Invalid secondary state: {exc.args[0]!r}") from exc
    ids.append(SEP_ID)

    return torch.tensor(ids, dtype=torch.long)


# =====================================================================
# Parquet row-group statistics
# =====================================================================

def file_signature(path: Path) -> Dict[str, int]:
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def count_row_group_windows(
    parquet_file: Path,
    batch_rows: int,
    max_proteins: Optional[int] = None,
) -> Dict:
    """
    Stream one column and build small work units inside Parquet row groups.

    A work unit contains at most ``batch_rows`` source proteins. This is
    important for DDP: even when a test limit (e.g. 100k proteins) falls
    entirely inside one Parquet row group, the work can still be balanced
    across all ranks.

    Memory is O(batch_rows), never O(dataset size).
    """
    pf = pq.ParquetFile(parquet_file)

    if REQUIRED_COLUMN not in pf.schema_arrow.names:
        raise ValueError(
            f"Column {REQUIRED_COLUMN!r} not found in {parquet_file}"
        )

    work_units = []
    global_row = 0
    remaining = max_proteins

    for rg_idx in range(pf.num_row_groups):
        rg_meta = pf.metadata.row_group(rg_idx)
        rg_rows_total = int(rg_meta.num_rows)

        if remaining is not None and remaining <= 0:
            break

        rows_to_use = (
            rg_rows_total
            if remaining is None
            else min(rg_rows_total, remaining)
        )

        rows_seen = 0

        for batch in pf.iter_batches(
            batch_size=batch_rows,
            row_groups=[rg_idx],
            columns=[REQUIRED_COLUMN],
            use_threads=True,
        ):
            if rows_seen >= rows_to_use:
                break

            values = batch.column(0).to_pylist()
            take = min(len(values), rows_to_use - rows_seen)
            values = values[:take]

            windows = 0
            for value in values:
                ss = clean_secondary_structure(value)
                windows += number_of_windows_from_clean_length(len(ss))

            work_units.append(
                {
                    "row_group": rg_idx,
                    "row_start": rows_seen,
                    "global_start": global_row + rows_seen,
                    "rows": take,
                    "windows": windows,
                }
            )

            rows_seen += take

        global_row += rg_rows_total

        if remaining is not None:
            remaining -= rows_to_use

    return {
        "file": str(parquet_file.resolve()),
        "signature": file_signature(parquet_file),
        "max_proteins": max_proteins,
        "proteins": sum(x["rows"] for x in work_units),
        "windows": sum(x["windows"] for x in work_units),
        # Keep this key for the rest of the script. Entries are now bounded
        # row-group segments rather than whole row groups.
        "row_groups": work_units,
        "work_unit_rows": batch_rows,
    }

def load_or_build_stats(
    train_file: Path,
    val_file: Path,
    cache_file: Path,
    batch_rows: int,
    max_train_proteins: Optional[int],
    max_val_proteins: Optional[int],
    rebuild: bool,
    rank: int,
) -> Dict:
    desired = {
        "stats_version": 2,
        "train_signature": file_signature(train_file),
        "val_signature": file_signature(val_file),
        "max_train_proteins": max_train_proteins,
        "max_val_proteins": max_val_proteins,
    }

    if rank == 0:
        stats = None

        if cache_file.is_file() and not rebuild:
            try:
                candidate = json.loads(cache_file.read_text())
                cache_key = candidate.get("cache_key", {})
                if cache_key == desired:
                    stats = candidate
                    logging.info("Using cached row-group statistics: %s", cache_file)
            except Exception as exc:
                logging.warning("Ignoring invalid stats cache: %s", exc)

        if stats is None:
            logging.info(
                "Building row-group statistics with bounded memory. "
                "This is a streaming scan and is cached for future runs."
            )
            train_stats = count_row_group_windows(
                train_file,
                batch_rows=batch_rows,
                max_proteins=max_train_proteins,
            )
            val_stats = count_row_group_windows(
                val_file,
                batch_rows=batch_rows,
                max_proteins=max_val_proteins,
            )
            stats = {
                "cache_key": desired,
                "train": train_stats,
                "validation": val_stats,
            }
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(stats, indent=2),
                encoding="utf-8",
            )
            logging.info("Saved row-group statistics: %s", cache_file)

    barrier()

    # Every rank reads the tiny JSON after rank 0 has created it.
    stats = json.loads(cache_file.read_text(encoding="utf-8"))
    return stats


def assign_row_groups_balanced(
    row_groups: Sequence[Dict],
    world_size: int,
) -> Tuple[List[List[Dict]], List[int]]:
    """
    Greedy LPT assignment by window count.

    This avoids every DDP rank reading the full Parquet file.
    """
    assignments: List[List[Dict]] = [[] for _ in range(world_size)]
    loads = [0 for _ in range(world_size)]

    for item in sorted(
        row_groups,
        key=lambda x: x["windows"],
        reverse=True,
    ):
        target = min(range(world_size), key=lambda r: loads[r])
        assignments[target].append(item)
        loads[target] += item["windows"]

    for rank_items in assignments:
        rank_items.sort(key=lambda x: x["row_group"])

    return assignments, loads



def rank_full_batch_capacity(
    rank_items: Sequence[Dict],
    batch_size: int,
    num_workers: int,
) -> int:
    """
    Number of full DataLoader batches available on one rank.

    With IterableDataset + multiple workers, drop_last applies to each worker
    replica independently, so account for each worker tail explicitly.
    """
    if num_workers <= 0:
        total = sum(int(item["windows"]) for item in rank_items)
        return total // batch_size

    capacity = 0
    for worker_id in range(num_workers):
        worker_items = rank_items[worker_id::num_workers]
        worker_windows = sum(int(item["windows"]) for item in worker_items)
        capacity += worker_windows // batch_size
    return capacity

# =====================================================================
# Streaming dataset
# =====================================================================

class SecondaryStructureIterableDataset(IterableDataset):
    def __init__(
        self,
        parquet_file: Path,
        row_groups: Sequence[Dict],
        split_name: str,
        global_seed: int,
        parquet_batch_rows: int,
        epoch: int = 0,
    ):
        super().__init__()
        self.parquet_file = Path(parquet_file)
        self.row_groups = list(row_groups)
        self.split_name = split_name
        self.global_seed = global_seed
        self.parquet_batch_rows = parquet_batch_rows
        self.epoch = epoch

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def _worker_row_groups(self) -> List[Dict]:
        info = get_worker_info()
        if info is None:
            return self.row_groups

        # Default/recommended configuration is num_workers=0. If workers are
        # enabled, split work units deterministically between them.
        return self.row_groups[info.id :: info.num_workers]

    def __iter__(self) -> Iterable[torch.Tensor]:
        pf = pq.ParquetFile(self.parquet_file)
        items = self._worker_row_groups()

        # Deterministic work-unit shuffle between epochs.
        rng = random.Random(
            deterministic_seed(
                self.global_seed + self.epoch,
                self.split_name,
                0,
            )
        )
        items = list(items)
        rng.shuffle(items)

        # Group assigned work units by physical Parquet row group. Each rank
        # scans a physical row group at most once, even if it owns several
        # small segments from that row group.
        by_rg: Dict[int, List[Dict]] = {}
        for item in items:
            by_rg.setdefault(int(item["row_group"]), []).append(item)

        rg_order = list(by_rg)
        rng.shuffle(rg_order)

        for rg_idx in rg_order:
            segments = sorted(
                by_rg[rg_idx],
                key=lambda x: int(x.get("row_start", 0)),
            )

            segment_idx = 0
            row_in_rg = 0

            for batch in pf.iter_batches(
                batch_size=self.parquet_batch_rows,
                row_groups=[rg_idx],
                columns=[REQUIRED_COLUMN],
                use_threads=True,
            ):
                values = batch.column(0).to_pylist()
                batch_start = row_in_rg
                batch_end = row_in_rg + len(values)

                while segment_idx < len(segments):
                    seg = segments[segment_idx]
                    seg_start = int(seg.get("row_start", 0))
                    seg_end = seg_start + int(seg["rows"])

                    if seg_end <= batch_start:
                        segment_idx += 1
                        continue

                    if seg_start >= batch_end:
                        break

                    overlap_start = max(seg_start, batch_start)
                    overlap_end = min(seg_end, batch_end)

                    for absolute_row_in_rg in range(
                        overlap_start,
                        overlap_end,
                    ):
                        value = values[
                            absolute_row_in_rg - batch_start
                        ]
                        example_index = (
                            int(seg["global_start"])
                            + (absolute_row_in_rg - seg_start)
                        )
                        ss = clean_secondary_structure(value)

                        starts = select_window_starts(
                            length=len(ss),
                            example_index=example_index,
                            split_name=self.split_name,
                            global_seed=self.global_seed,
                        )

                        for start in starts:
                            window = ss[start : start + WINDOW_SIZE]
                            yield encode_window_direct(window)

                    if seg_end <= batch_end:
                        segment_idx += 1
                    else:
                        break

                row_in_rg = batch_end

                if segment_idx >= len(segments):
                    break


# =====================================================================
# Dynamic MLM collator
# =====================================================================

class FixedLengthMLMCollator:
    """
    Stack fixed 27-token examples and apply standard BERT-style MLM masking.

    Special tokens are never masked.
    """
    def __init__(self, mlm_probability: float):
        if not (0.0 < mlm_probability < 1.0):
            raise ValueError("--mlm-probability must be between 0 and 1")
        self.mlm_probability = mlm_probability

    def __call__(self, examples: List[torch.Tensor]) -> Dict[str, torch.Tensor]:
        input_ids = torch.stack(examples, dim=0)
        labels = input_ids.clone()

        probability_matrix = torch.full(
            labels.shape,
            self.mlm_probability,
            dtype=torch.float32,
        )

        # Never mask [CLS] or [SEP]. There is no padding in fixed-length inputs.
        probability_matrix[:, 0] = 0.0
        probability_matrix[:, -1] = 0.0

        masked = torch.bernoulli(probability_matrix).bool()
        labels[~masked] = -100

        # 80% of selected tokens -> [MASK]
        replace_prob = torch.full(labels.shape, 0.8, dtype=torch.float32)
        indices_replaced = torch.bernoulli(replace_prob).bool() & masked
        input_ids[indices_replaced] = MASK_ID

        # Of the remaining selected positions, 50% -> random token.
        # This corresponds to 10% of all originally selected positions.
        random_prob = torch.full(labels.shape, 0.5, dtype=torch.float32)
        indices_random = (
            torch.bernoulli(random_prob).bool()
            & masked
            & ~indices_replaced
        )

        # Match BERT MLM semantics: random IDs can be any vocabulary ID.
        random_words = torch.randint(
            low=0,
            high=VOCAB_SIZE,
            size=labels.shape,
            dtype=torch.long,
        )
        input_ids[indices_random] = random_words[indices_random]

        attention_mask = torch.ones_like(input_ids)
        token_type_ids = torch.zeros_like(input_ids)

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
            "labels": labels,
        }


# =====================================================================
# Resource monitor
# =====================================================================

def _visible_physical_gpu_indices() -> List[int]:
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if not visible:
        return list(range(torch.cuda.device_count()))

    indices = []
    for item in visible.split(","):
        item = item.strip()
        if item.isdigit():
            indices.append(int(item))

    if len(indices) == torch.cuda.device_count():
        return indices

    return list(range(torch.cuda.device_count()))


def process_tree_rss_bytes() -> int:
    proc = psutil.Process(os.getpid())
    total = proc.memory_info().rss
    for child in proc.children(recursive=True):
        try:
            total += child.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return total


def start_resource_monitor(interval: float, rank: int):
    if rank != 0 or interval <= 0:
        return None, None

    stop_event = threading.Event()
    physical_gpu_indices = _visible_physical_gpu_indices()
    nvml_available = False

    if pynvml is not None and torch.cuda.is_available():
        try:
            pynvml.nvmlInit()
            nvml_available = True
        except Exception as exc:
            logging.warning("NVML unavailable: %s", exc)

    def monitor():
        while not stop_event.is_set():
            try:
                vm = psutil.virtual_memory()
                rss = process_tree_rss_bytes()

                parts = [
                    (
                        f"SYSTEM RAM {vm.used / 2**30:.1f}/"
                        f"{vm.total / 2**30:.1f} GB ({vm.percent:.1f}%)"
                    ),
                    f"RANK0 PROCESS TREE RSS {rss / 2**30:.2f} GB",
                ]

                if torch.cuda.is_available():
                    for logical_id in range(torch.cuda.device_count()):
                        if nvml_available:
                            physical_id = physical_gpu_indices[logical_id]
                            handle = pynvml.nvmlDeviceGetHandleByIndex(physical_id)
                            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                            temp = pynvml.nvmlDeviceGetTemperature(
                                handle,
                                pynvml.NVML_TEMPERATURE_GPU,
                            )
                            parts.append(
                                f"GPU {physical_id} "
                                f"VRAM {mem.used / 2**30:.1f}/"
                                f"{mem.total / 2**30:.1f} GB "
                                f"({100 * mem.used / mem.total:.1f}%) "
                                f"| util {util.gpu}% | temp {temp}C"
                            )
                        else:
                            free_b, total_b = torch.cuda.mem_get_info(logical_id)
                            used_b = total_b - free_b
                            parts.append(
                                f"GPU {logical_id} "
                                f"VRAM {used_b / 2**30:.1f}/"
                                f"{total_b / 2**30:.1f} GB"
                            )

                logging.info("[RESOURCE MONITOR] %s", " | ".join(parts))

            except Exception:
                logging.exception("Resource monitor error")

            stop_event.wait(interval)

        if nvml_available:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass

    thread = threading.Thread(
        target=monitor,
        name="resource-monitor",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def stop_resource_monitor(stop_event, thread) -> None:
    if stop_event is None:
        return
    stop_event.set()
    if thread is not None:
        thread.join(timeout=5.0)


# =====================================================================
# DataLoader / sanity
# =====================================================================

def build_loader(
    dataset: IterableDataset,
    batch_size: int,
    num_workers: int,
    prefetch_factor: int,
    mlm_probability: float,
    pin_memory: bool,
) -> DataLoader:
    kwargs = dict(
        dataset=dataset,
        batch_size=batch_size,
        collate_fn=FixedLengthMLMCollator(mlm_probability),
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=True,
    )

    if num_workers > 0:
        kwargs["prefetch_factor"] = prefetch_factor
        kwargs["persistent_workers"] = False

    return DataLoader(**kwargs)


def sanity_check_stream(
    dataset: SecondaryStructureIterableDataset,
    tokenizer: BertTokenizer,
    n_examples: int,
) -> None:
    if n_examples <= 0:
        return

    checked = 0
    first_examples = []

    for ids_tensor in dataset:
        ids = ids_tensor.tolist()

        if len(ids) != SEQUENCE_LENGTH:
            raise RuntimeError(f"Invalid streamed sequence length: {len(ids)}")
        if ids[0] != CLS_ID or ids[-1] != SEP_ID:
            raise RuntimeError("Invalid streamed special tokens")
        if any(token not in (5, 6, 7) for token in ids[1:-1]):
            raise RuntimeError("Invalid streamed biological token")

        if len(first_examples) < 5:
            first_examples.append(ids)

        checked += 1
        if checked >= n_examples:
            break

    if checked == 0:
        raise RuntimeError("Streaming dataset produced no examples")

    logging.info("Streaming sanity check PASSED for %d examples", checked)

    for i, ids in enumerate(first_examples):
        logging.info("Example %d IDs: %s", i, ids)
        logging.info(
            "Example %d tokens: %s",
            i,
            tokenizer.convert_ids_to_tokens(ids),
        )


# =====================================================================
# Model
# =====================================================================

def build_model() -> BertForMaskedLM:
    from transformers import BertConfig, BertForMaskedLM

    config = BertConfig(
        vocab_size=VOCAB_SIZE,
        hidden_size=HIDDEN_SIZE,
        num_hidden_layers=NUM_LAYERS,
        num_attention_heads=NUM_HEADS,
        intermediate_size=INTERMEDIATE_SIZE,
        hidden_act="gelu",
        max_position_embeddings=MAX_LEN,
        type_vocab_size=1,
        pad_token_id=PAD_ID,
    )
    return BertForMaskedLM(config)


# =====================================================================
# Training
# =====================================================================

def move_batch(
    batch: Dict[str, torch.Tensor],
    device: torch.device,
) -> Dict[str, torch.Tensor]:
    return {
        key: value.to(device, non_blocking=True)
        for key, value in batch.items()
    }


def require_masked_training_tokens(labels: torch.Tensor) -> None:
    """Fail every rank before forward if any rank would have undefined mean loss."""
    has_tokens = labels.ne(-100).any().to(dtype=torch.int32)
    if dist.is_initialized():
        dist.all_reduce(has_tokens, op=dist.ReduceOp.MIN)
    if not has_tokens.item():
        raise RuntimeError("Training batch has no masked tokens on at least one rank")


def main() -> None:
    from transformers import BertTokenizer, get_linear_schedule_with_warmup

    args = parse_args()
    rank, local_rank, world_size, device = init_distributed()
    setup_logging(rank)

    dataset_dir = (
        args.dataset_dir
        if args.dataset_dir is not None
        else args.data_dir / "bert_mlm_dataset"
    )

    train_file = dataset_dir / "train.parquet"
    val_file = dataset_dir / "val.parquet"
    vocab_file = dataset_dir / "vocab.txt"

    for path in (train_file, val_file, vocab_file):
        if not path.is_file():
            raise FileNotFoundError(path)

    if args.stats_cache is None:
        args.stats_cache = dataset_dir / "secondary_mlm_rowgroup_stats.json"

    if rank == 0:
        logging.info("Starting memory-optimized SecondaryBERT MLM training")
        logging.info("Dataset directory: %s", dataset_dir)
        logging.info("Output directory: %s", args.output_dir)
        logging.info("World size: %d", world_size)
        logging.info("Per-device batch size: %d", args.batch_size)
        logging.info("Parquet batch rows: %d", args.parquet_batch_rows)
        logging.info("DataLoader workers/rank: %d", args.num_workers)

    # Identical model initialization on every DDP rank.
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    tokenizer = build_tokenizer(vocab_file)

    stats = load_or_build_stats(
        train_file=train_file,
        val_file=val_file,
        cache_file=args.stats_cache,
        batch_rows=args.parquet_batch_rows,
        max_train_proteins=args.max_train_proteins,
        max_val_proteins=args.max_val_proteins,
        rebuild=args.rebuild_stats,
        rank=rank,
    )

    train_assignments, train_rank_windows = assign_row_groups_balanced(
        stats["train"]["row_groups"],
        world_size,
    )
    val_assignments, val_rank_windows = assign_row_groups_balanced(
        stats["validation"]["row_groups"],
        world_size,
    )

    # All DDP ranks must execute exactly the same number of optimizer steps.
    # Use enough full batches to cover the longest rank. Shorter ranks restart
    # their streaming iterator only after all of their original windows have
    # been consumed. This guarantees 100% coverage of original windows while
    # repeating only the minimum number needed for DDP synchronization.
    rank_windows = [int(x) for x in train_rank_windows]
    if any(x <= 0 for x in rank_windows):
        raise RuntimeError(
            "At least one DDP rank received zero training windows. "
            "Reduce world size or use more data."
        )

    batches_needed_per_rank = [
        math.ceil(x / args.batch_size) for x in rank_windows
    ]
    steps_per_epoch = max(batches_needed_per_rank)

    if steps_per_epoch <= 0:
        raise RuntimeError("No training batches were generated.")

    processed_windows_per_epoch = (
        steps_per_epoch * args.batch_size * world_size
    )
    total_windows = int(stats["train"]["windows"])
    repeated_windows = max(0, processed_windows_per_epoch - total_windows)

    total_steps = steps_per_epoch * args.num_epochs
    warmup_steps = int(total_steps * args.warmup_ratio)

    if rank == 0:
        logging.info("=" * 72)
        logging.info("STREAMING DATASET")
        logging.info("Train proteins: %d", stats["train"]["proteins"])
        logging.info("Train windows: %d", total_windows)
        logging.info(
            "Validation proteins: %d",
            stats["validation"]["proteins"],
        )
        logging.info(
            "Validation windows: %d",
            stats["validation"]["windows"],
        )
        logging.info("Windows assigned/rank: %s", train_rank_windows)
        logging.info(
            "Effective global batch: %d",
            args.batch_size * world_size,
        )
        logging.info("Steps/epoch: %d", steps_per_epoch)
        logging.info("Total optimizer steps: %d", total_steps)
        logging.info("Warmup steps: %d", warmup_steps)
        logging.info("Batches needed/rank: %s", batches_needed_per_rank)
        logging.info(
            "Original-window coverage/epoch: 100%% (%d/%d)",
            total_windows,
            total_windows,
        )
        logging.info(
            "DDP synchronization repeats/epoch: %d windows (%.4f%% overhead)",
            repeated_windows,
            100.0 * repeated_windows / max(total_windows, 1),
        )
        logging.info("=" * 72)

    train_dataset = SecondaryStructureIterableDataset(
        parquet_file=train_file,
        row_groups=train_assignments[rank],
        split_name="train",
        global_seed=args.seed,
        parquet_batch_rows=args.parquet_batch_rows,
    )

    val_dataset = SecondaryStructureIterableDataset(
        parquet_file=val_file,
        row_groups=val_assignments[rank],
        split_name="validation",
        global_seed=args.seed,
        parquet_batch_rows=args.parquet_batch_rows,
    )

    # Sanity check only on rank 0 to avoid redundant work.
    if rank == 0:
        sanity_check_stream(
            train_dataset,
            tokenizer,
            n_examples=args.sanity_examples,
        )
        if not args.skip_validation_sanity:
            sanity_check_stream(
                val_dataset,
                tokenizer,
                n_examples=min(100, args.sanity_examples),
            )

    barrier()

    model = build_model().to(device)

    total_params = sum(p.numel() for p in model.parameters())
    if rank == 0:
        logging.info("Model parameters: %d", total_params)

    if world_size > 1:
        model = DDP(
            model,
            device_ids=[local_rank] if device.type == "cuda" else None,
            output_device=local_rank if device.type == "cuda" else None,
            find_unused_parameters=False,
        )

    # Match the Trainer/Transformers AdamW convention: do not apply
    # weight decay to biases or LayerNorm parameters.
    decay_parameters = []
    no_decay_parameters = []

    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        if (
            name.endswith(".bias")
            or "LayerNorm.weight" in name
            or "layer_norm.weight" in name
        ):
            no_decay_parameters.append(parameter)
        else:
            decay_parameters.append(parameter)

    optimizer = AdamW(
        [
            {
                "params": decay_parameters,
                "weight_decay": WEIGHT_DECAY,
            },
            {
                "params": no_decay_parameters,
                "weight_decay": 0.0,
            },
        ],
        lr=args.learning_rate,
        betas=(0.9, 0.999),
        eps=1e-8,
    )
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    scaler = torch.amp.GradScaler(
        "cuda",
        enabled=(device.type == "cuda"),
    )

    monitor_stop, monitor_thread = start_resource_monitor(
        args.monitor_interval,
        rank,
    )

    global_step = 0
    loss_accumulator = 0.0
    loss_count = 0

    try:
        for epoch in range(args.num_epochs):
            train_dataset.set_epoch(epoch)

            loader = build_loader(
                dataset=train_dataset,
                batch_size=args.batch_size,
                num_workers=args.num_workers,
                prefetch_factor=args.prefetch_factor,
                mlm_probability=args.mlm_probability,
                pin_memory=(device.type == "cuda"),
            )

            model.train()
            iterator = iter(loader)

            if rank == 0:
                logging.info(
                    "Epoch %d/%d started",
                    epoch + 1,
                    args.num_epochs,
                )

            for epoch_step in range(steps_per_epoch):
                try:
                    batch = next(iterator)
                except StopIteration:
                    # This rank has consumed all of its original windows.
                    # Restart only to provide the minimal DDP synchronization
                    # padding required to match the longest rank.
                    iterator = iter(loader)
                    try:
                        batch = next(iterator)
                    except StopIteration as exc:
                        raise RuntimeError(
                            f"Rank {rank} streaming dataset produced no full "
                            "batch after restart."
                        ) from exc

                batch = move_batch(batch, device)
                require_masked_training_tokens(batch["labels"])

                optimizer.zero_grad(set_to_none=True)

                with torch.autocast(
                    device_type=device.type,
                    dtype=torch.float16,
                    enabled=(device.type == "cuda"),
                ):
                    outputs = model(**batch)
                    loss = outputs.loss

                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                grad_norm = torch.nn.utils.clip_grad_norm_(
                    model.parameters(),
                    max_norm=1.0,
                )
                # GradScaler can skip optimizer.step() when it detects an
                # overflow. Advance the LR scheduler only when an optimizer
                # update actually happened; otherwise PyTorch warns that the
                # scheduler stepped before the optimizer and the LR schedule
                # becomes off by one.
                scale_before = scaler.get_scale()
                scaler.step(optimizer)
                scaler.update()
                scale_after = scaler.get_scale()
                optimizer_step_was_skipped = scale_after < scale_before
                if not optimizer_step_was_skipped:
                    scheduler.step()

                global_step += 1
                loss_accumulator += float(loss.detach().item())
                loss_count += 1

                if (
                    rank == 0
                    and (
                        global_step % args.logging_steps == 0
                        or epoch_step + 1 == steps_per_epoch
                    )
                ):
                    avg_loss = loss_accumulator / max(loss_count, 1)
                    lr = scheduler.get_last_lr()[0]
                    logging.info(
                        "step %d/%d | epoch %d | epoch_step %d/%d | "
                        "loss %.6f | grad_norm %.4f | lr %.6g",
                        global_step,
                        total_steps,
                        epoch + 1,
                        epoch_step + 1,
                        steps_per_epoch,
                        avg_loss,
                        float(grad_norm),
                        lr,
                    )
                    loss_accumulator = 0.0
                    loss_count = 0

            del iterator
            del loader

    finally:
        stop_resource_monitor(monitor_stop, monitor_thread)

    barrier()

    if rank == 0:
        args.output_dir.mkdir(parents=True, exist_ok=True)

        model_to_save = model.module if isinstance(model, DDP) else model
        logging.info("Saving model to %s", args.output_dir)
        model_to_save.save_pretrained(str(args.output_dir))
        tokenizer.save_pretrained(str(args.output_dir))

        reloaded = BertTokenizer.from_pretrained(str(args.output_dir))
        observed = reloaded(
            "C H E C",
            add_special_tokens=True,
        )["input_ids"]
        expected = [2, 5, 6, 7, 5, 3]

        if observed != expected:
            raise RuntimeError(
                f"Saved tokenizer verification failed: {observed}"
            )

        logging.info(
            "Saved tokenizer verification PASSED: 'C H E C' -> %s",
            observed,
        )
        logging.info(
            "SecondaryBERT MLM training completed successfully"
        )

    barrier()
    cleanup_distributed()


if __name__ == "__main__":
    main()