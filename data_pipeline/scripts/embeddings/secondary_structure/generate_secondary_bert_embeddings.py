#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fast multi-GPU SecondaryBERT embedding generation.

Key properties
--------------
- Uses the corrected SecondaryBERT model.
- Direct C/H/E -> token IDs: no tokenizer in the hot loop.
- Mean-pools the 25 biological token embeddings immediately:
      (B, 25, 768) -> (B, 768)
- Saves float32 pooled embeddings directly.
- Two or more GPUs via torchrun: files are deterministically distributed by rank.
- fp16 autocast on CUDA for fast inference.
- Writes chunks incrementally with numpy.open_memmap: bounded RAM.
- Preserves protein_group_id / group_id mapping and manifests.
- Safe resume: validates output configuration and every existing chunk.
- Atomic chunk publication through temporary files.
- Sanity checks tokenizer, finite values, embedding variability and coverage.
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.distributed as dist

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pynvml
except ImportError:
    pynvml = None
from numpy.lib.format import open_memmap
from transformers import BertForMaskedLM, BertTokenizer


DATA_INTERMEDIATE = Path("/home/nap/lperez_nn/data/data_intermediate")
DATA_INPUT_NN = Path("/data/nap/lperez_nn/data/data_input_nn")
MODEL_DIR = Path("/home/nap/lperez_nn/model/secondary_bert")

PROTEIN_GROUP_COL = "protein_group_id"
GROUP_COL = "group_id"
SEQ_COL = "25aa_seq"
SS_COL = "secondary_structure"
LABEL_COL = "contains_epitope"
POS_COL = "epitope_pos_score"
PROTEIN_COL = "protein_url"
WINDOW_COL = "window_start"
STATUS_COL = "ss_status"

WINDOW_SIZE = 25
HIDDEN_SIZE = 768
SEQUENCE_LENGTH = WINDOW_SIZE + 2
SAVE_DTYPE = np.float32

PAD_ID = 0
UNK_ID = 1
CLS_ID = 2
SEP_ID = 3
MASK_ID = 4
STATE_TO_ID = {"C": 5, "H": 6, "E": 7}
VALID_SS = set(STATE_TO_ID)

DEFAULT_BATCH_SIZE = 1024
DEFAULT_CHUNK_SIZE = 102_400
CONFIG_VERSION = 2


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int):
        super().__init__()
        self.max_level = max_level

    def filter(self, record):
        return record.levelno <= self.max_level


def setup_logging(rank: int) -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.addFilter(MaxLevelFilter(logging.INFO))
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)


def dist_info():
    return (
        int(os.environ.get("RANK", "0")),
        int(os.environ.get("LOCAL_RANK", "0")),
        int(os.environ.get("WORLD_SIZE", "1")),
    )


def init_distributed():
    rank, local_rank, world_size = dist_info()

    if torch.cuda.is_available():
        torch.cuda.set_device(local_rank)
        device = torch.device("cuda", local_rank)
    else:
        device = torch.device("cpu")

    if world_size > 1 and not dist.is_initialized():
        backend = "nccl" if device.type == "cuda" else "gloo"
        dist.init_process_group(
            backend=backend,
            device_id=device if backend == "nccl" else None,
        )
    return rank, local_rank, world_size, device


def barrier():
    if dist.is_initialized():
        dist.barrier()


def cleanup_distributed():
    if dist.is_initialized():
        dist.destroy_process_group()


def clean_secondary_structure(ss) -> str:
    if pd.isna(ss):
        return ""

    ss = str(ss).replace(" ", "").strip().upper()
    if not ss:
        return ""

    # Preserve the semantics of the previous embedding script:
    # invalid labels become coil.
    ss = "".join(ch if ch in VALID_SS else "C" for ch in ss)

    if len(ss) > WINDOW_SIZE:
        ss = ss[:WINDOW_SIZE]
    elif len(ss) < WINDOW_SIZE:
        ss += "C" * (WINDOW_SIZE - len(ss))

    return ss


def encode_batch_direct(batch: List[str], device: torch.device):
    """Build fixed (B,27) input tensors directly, bypassing tokenizer overhead."""
    n = len(batch)
    ids = torch.empty((n, SEQUENCE_LENGTH), dtype=torch.long)
    ids[:, 0] = CLS_ID
    ids[:, -1] = SEP_ID

    # 25 is tiny; constructing a flat NumPy buffer is faster and predictable.
    arr = np.empty((n, WINDOW_SIZE), dtype=np.int64)
    for i, ss in enumerate(batch):
        arr[i] = [STATE_TO_ID[ch] for ch in ss]

    ids[:, 1:-1] = torch.from_numpy(arr)

    attention_mask = torch.ones_like(ids)
    token_type_ids = torch.zeros_like(ids)

    return (
        ids.to(device, non_blocking=True),
        attention_mask.to(device, non_blocking=True),
        token_type_ids.to(device, non_blocking=True),
    )


def validate_tokenizer(model_dir: Path) -> None:
    tokenizer = BertTokenizer.from_pretrained(str(model_dir))
    expected = [2, 5, 6, 7, 5, 3]
    observed = tokenizer("C H E C", add_special_tokens=True)["input_ids"]

    if observed != expected:
        raise RuntimeError(
            f"Tokenizer mismatch: expected {expected}, got {observed}"
        )

    expected_vocab = {
        "[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3,
        "[MASK]": 4, "C": 5, "H": 6, "E": 7,
    }
    for token, expected_id in expected_vocab.items():
        actual = tokenizer.convert_tokens_to_ids(token)
        if actual != expected_id:
            raise RuntimeError(
                f"Tokenizer mapping mismatch for {token}: "
                f"{actual} != {expected_id}"
            )


def load_model(model_dir: Path, device: torch.device):
    model = BertForMaskedLM.from_pretrained(str(model_dir))
    model = model.to(device)
    model.eval()

    if model.config.hidden_size != HIDDEN_SIZE:
        raise RuntimeError(
            f"Unexpected hidden size {model.config.hidden_size}; "
            f"expected {HIDDEN_SIZE}"
        )
    return model


@torch.inference_mode()
def embed_batch(
    batch: List[str],
    model: BertForMaskedLM,
    device: torch.device,
) -> np.ndarray:
    input_ids, attention_mask, token_type_ids = encode_batch_direct(batch, device)

    with torch.autocast(
        device_type=device.type,
        dtype=torch.float16,
        enabled=(device.type == "cuda"),
    ):
        outputs = model.bert(
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            return_dict=True,
        )
        # Exclude [CLS]/[SEP], pool only the 25 secondary-structure positions.
        pooled = outputs.last_hidden_state[:, 1:-1, :].mean(dim=1)

    out = pooled.float().cpu().numpy().astype(SAVE_DTYPE, copy=False)

    if out.shape != (len(batch), HIDDEN_SIZE):
        raise RuntimeError(f"Bad embedding batch shape: {out.shape}")
    if not np.isfinite(out).all():
        raise RuntimeError("NaN/Inf detected in SecondaryBERT embeddings")

    return out


@torch.inference_mode()
def model_sanity_check(model, device):
    sequences = [
        "C" * 25,
        "H" * 25,
        "E" * 25,
        "CHE" * 8 + "C",
    ]
    emb = embed_batch(sequences, model, device)

    if np.allclose(emb, emb[0], rtol=1e-6, atol=1e-7):
        raise RuntimeError(
            "Embedding sanity FAILED: distinct SS sequences produced "
            "effectively identical embeddings."
        )

    std_across_sequences = float(np.mean(np.std(emb, axis=0)))
    max_diff = float(
        max(
            np.max(np.abs(emb[i] - emb[j]))
            for i in range(len(emb))
            for j in range(i + 1, len(emb))
        )
    )
    return std_across_sequences, max_diff


def build_output_dir(ss_csv_path: Path) -> Path:
    # Resolve both paths so --csv accepts either relative or absolute paths.
    ss_csv_path = ss_csv_path.expanduser().resolve()
    data_intermediate = DATA_INTERMEDIATE.expanduser().resolve()
    try:
        relative_parent = ss_csv_path.parent.relative_to(data_intermediate)
    except ValueError as exc:
        raise ValueError(
            f"Input CSV must be inside DATA_INTERMEDIATE. "
            f"CSV={ss_csv_path} | DATA_INTERMEDIATE={data_intermediate}"
        ) from exc
    dataset_name = ss_csv_path.stem.replace("_ss", "")
    out_dir = (
        DATA_INPUT_NN
        / relative_parent
        / f"{dataset_name}_SecondaryBERT_by_group"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def model_fingerprint(model_dir: Path) -> str:
    """Stable lightweight fingerprint of model config + weight-file metadata."""
    h = hashlib.sha256()
    for name in ("config.json", "model.safetensors", "pytorch_model.bin", "vocab.txt"):
        p = model_dir / name
        if p.exists():
            st = p.stat()
            h.update(name.encode())
            h.update(str(st.st_size).encode())
            h.update(str(st.st_mtime_ns).encode())
            if name in ("config.json", "vocab.txt"):
                h.update(p.read_bytes())
    return h.hexdigest()


def desired_config(
    ss_csv_path: Path,
    total: int,
    batch_size: int,
    chunk_size: int,
    model_dir: Path,
    fingerprint: str,
) -> Dict:
    return {
        "config_version": CONFIG_VERSION,
        "source_csv": str(ss_csv_path.resolve()),
        "total_rows": int(total),
        "batch_size": int(batch_size),
        "chunk_size": int(chunk_size),
        "window_size": WINDOW_SIZE,
        "hidden_size": HIDDEN_SIZE,
        "dtype": "float32",
        "pooling": "mean_25_biological_tokens",
        "output_shape_per_row": [HIDDEN_SIZE],
        "model_dir": str(model_dir.resolve()),
        "model_fingerprint": fingerprint,
        "id_columns": [PROTEIN_GROUP_COL, GROUP_COL],
        "token_mapping": STATE_TO_ID,
    }


def config_compatible(config_path: Path, wanted: Dict) -> bool:
    if not config_path.is_file():
        return False
    try:
        current = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    keys = (
        "config_version", "source_csv", "total_rows", "chunk_size",
        "window_size", "hidden_size", "dtype", "pooling",
        "output_shape_per_row", "model_dir", "model_fingerprint",
    )
    return all(current.get(k) == wanted.get(k) for k in keys)


def save_metadata_and_index(df, protein_group_ids, group_ids, out_dir):
    metadata_path = out_dir / "metadata.csv"
    index_path = out_dir / "index.csv"

    metadata_cols = [
        PROTEIN_GROUP_COL, GROUP_COL, SEQ_COL, SS_COL, "clean_ss",
        LABEL_COL, POS_COL, PROTEIN_COL, WINDOW_COL,
    ]
    optional_cols = [
        "selected_epitope", "protein_found", "sequence_match", STATUS_COL,
    ]
    metadata_cols += [c for c in optional_cols if c in df.columns]

    df[metadata_cols].to_csv(metadata_path, index=False)
    pd.DataFrame({
        PROTEIN_GROUP_COL: protein_group_ids,
        GROUP_COL: group_ids,
        "row_idx_in_X_ss": np.arange(len(group_ids), dtype=np.int64),
    }).to_csv(index_path, index=False)

    np.save(out_dir / "protein_group_id.npy", protein_group_ids)
    np.save(out_dir / "group_id.npy", group_ids)


def chunk_is_valid(x_path, protein_path, gid_path, expected_rows):
    if not all(p.is_file() for p in (x_path, protein_path, gid_path)):
        return False
    try:
        x = np.load(x_path, mmap_mode="r")
        p = np.load(protein_path, mmap_mode="r")
        g = np.load(gid_path, mmap_mode="r")
        return (
            x.shape == (expected_rows, HIDDEN_SIZE)
            and x.dtype == SAVE_DTYPE
            and p.shape == (expected_rows,)
            and g.shape == (expected_rows,)
        )
    except Exception:
        return False


def remove_previous_outputs(out_dir: Path):
    for name in (
        "protein_group_id.npy", "group_id.npy", "group_ids.npy",
        "metadata.csv", "index.csv", "group_index.csv",
        "chunks_manifest.csv", "embedding_config.json", "done.flag",
    ):
        p = out_dir / name
        if p.exists():
            p.unlink()
    chunks = out_dir / "chunks"
    if chunks.exists():
        shutil.rmtree(chunks)



class ResourceMonitor:
    """Low-overhead periodic RAM/process/GPU monitor."""

    def __init__(self, rank: int, local_rank: int, interval: float = 60.0):
        self.rank = rank
        self.local_rank = local_rank
        self.interval = max(float(interval), 1.0)
        self.stop_event = threading.Event()
        self.thread = None
        self.nvml_ok = False
        self.nvml_handle = None

        if pynvml is not None and torch.cuda.is_available():
            try:
                pynvml.nvmlInit()
                # CUDA_VISIBLE_DEVICES remaps local CUDA device indices, but NVML
                # sees physical devices. Use CUDA UUID to get the exact handle.
                props = torch.cuda.get_device_properties(local_rank)
                uuid = getattr(props, "uuid", None)
                if uuid is not None:
                    uuid_str = str(uuid)
                    if uuid_str.startswith("GPU-"):
                        self.nvml_handle = pynvml.nvmlDeviceGetHandleByUUID(
                            uuid_str.encode()
                        )
                if self.nvml_handle is None:
                    # Safe fallback for the common non-remapped/single-GPU case.
                    self.nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(local_rank)
                self.nvml_ok = True
            except Exception:
                self.nvml_ok = False
                self.nvml_handle = None

    @staticmethod
    def _gib(n):
        return float(n) / (1024.0 ** 3)

    def log_once(self):
        parts = [f"RESOURCE rank={self.rank}"]

        if psutil is not None:
            try:
                vm = psutil.virtual_memory()
                proc = psutil.Process(os.getpid())
                rss = proc.memory_info().rss
                parts.append(
                    "RAM "
                    f"used={self._gib(vm.used):.1f}GiB "
                    f"avail={self._gib(vm.available):.1f}GiB "
                    f"total={self._gib(vm.total):.1f}GiB "
                    f"({vm.percent:.1f}%)"
                )
                parts.append(f"RSS={self._gib(rss):.2f}GiB")
            except Exception as exc:
                parts.append(f"RAM=unavailable({exc})")

        if torch.cuda.is_available():
            try:
                allocated = torch.cuda.memory_allocated(self.local_rank)
                reserved = torch.cuda.memory_reserved(self.local_rank)
                parts.append(
                    f"torchVRAM alloc={self._gib(allocated):.2f}GiB "
                    f"reserved={self._gib(reserved):.2f}GiB"
                )
            except Exception:
                pass

        if self.nvml_ok:
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(self.nvml_handle)
                util = pynvml.nvmlDeviceGetUtilizationRates(self.nvml_handle)
                temp = pynvml.nvmlDeviceGetTemperature(
                    self.nvml_handle, pynvml.NVML_TEMPERATURE_GPU
                )
                power = pynvml.nvmlDeviceGetPowerUsage(self.nvml_handle) / 1000.0
                parts.append(
                    "GPU "
                    f"util={util.gpu}% "
                    f"VRAM={self._gib(mem.used):.2f}/{self._gib(mem.total):.2f}GiB "
                    f"temp={temp}C power={power:.0f}W"
                )
            except Exception as exc:
                parts.append(f"NVML=unavailable({exc})")

        logging.info(" | ".join(parts))

    def _loop(self):
        self.log_once()
        while not self.stop_event.wait(self.interval):
            self.log_once()

    def start(self):
        self.thread = threading.Thread(
            target=self._loop, name="resource-monitor", daemon=True
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        self.log_once()
        if self.nvml_ok and pynvml is not None:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass


def validate_required_columns(df, csv_path):
    required = {
        PROTEIN_GROUP_COL, GROUP_COL, SEQ_COL, SS_COL,
        LABEL_COL, POS_COL, PROTEIN_COL, WINDOW_COL,
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {csv_path}: {missing}")


def csv_usecols(csv_path: Path) -> List[str]:
    """Read only the header and return columns needed by this pipeline."""
    header = pd.read_csv(csv_path, nrows=0).columns.tolist()
    required = {
        PROTEIN_GROUP_COL, GROUP_COL, SEQ_COL, SS_COL,
        LABEL_COL, POS_COL, PROTEIN_COL, WINDOW_COL,
    }
    missing = required - set(header)
    if missing:
        raise ValueError(f"Missing columns in {csv_path}: {missing}")

    optional = ["selected_epitope", "protein_found", "sequence_match", STATUS_COL]
    return [
        c for c in [
            PROTEIN_GROUP_COL, GROUP_COL, SEQ_COL, SS_COL,
            LABEL_COL, POS_COL, PROTEIN_COL, WINDOW_COL, *optional
        ]
        if c in header
    ]


def iter_unique_group_rows(
    csv_path: Path,
    csv_chunk_rows: int,
    usecols: List[str],
):
    """
    Stream the CSV and yield one row per group_id.

    The classification files are expected to contain repeated BLOSUM rows for a
    group. We do NOT retain the whole dataframe. A set of seen group IDs is kept
    so correctness does not depend on adjacent/sorted duplicates.

    Memory cost is therefore O(number_of_unique_groups) for the integer set,
    rather than O(all CSV rows + strings + dataframe copies).
    """
    seen = set()

    for chunk in pd.read_csv(
        csv_path,
        usecols=usecols,
        chunksize=csv_chunk_rows,
    ):
        if STATUS_COL in chunk.columns:
            chunk = chunk[chunk[STATUS_COL] == "ok"]

        if chunk.empty:
            continue

        # Remove duplicate group IDs inside this source chunk first.
        chunk = chunk.drop_duplicates(GROUP_COL, keep="first")

        for row in chunk.itertuples(index=False, name=None):
            record = dict(zip(chunk.columns, row))
            gid = int(record[GROUP_COL])
            if gid in seen:
                continue

            ss = clean_secondary_structure(record[SS_COL])
            if not ss:
                continue

            seen.add(gid)
            record["clean_ss"] = ss
            yield record

    del seen


def count_unique_groups_streaming(
    csv_path: Path,
    csv_chunk_rows: int,
    usecols: List[str],
) -> int:
    """First streaming pass: count output rows without retaining the dataframe."""
    n = 0
    for _ in iter_unique_group_rows(csv_path, csv_chunk_rows, usecols):
        n += 1
    return n


def stream_records_in_output_chunks(
    csv_path: Path,
    csv_chunk_rows: int,
    output_chunk_rows: int,
    usecols: List[str],
):
    """Second streaming pass: yield lists of unique records of bounded size."""
    buf = []
    for record in iter_unique_group_rows(csv_path, csv_chunk_rows, usecols):
        buf.append(record)
        if len(buf) >= output_chunk_rows:
            yield buf
            buf = []
    if buf:
        yield buf


def write_global_ids_from_chunks(
    out_dir: Path,
    manifest_rows: List[Dict],
    total: int,
):
    """
    Build global protein_group_id.npy and group_id.npy using memmaps.
    This avoids ever holding all IDs in RAM.
    """
    protein_tmp = out_dir / ".protein_group_id.tmp.npy"
    group_tmp = out_dir / ".group_id.tmp.npy"

    for p in (protein_tmp, group_tmp):
        if p.exists():
            p.unlink()

    protein_mm = open_memmap(
        protein_tmp, mode="w+", dtype=np.int64, shape=(total,)
    )
    group_mm = open_memmap(
        group_tmp, mode="w+", dtype=np.int64, shape=(total,)
    )

    for row in manifest_rows:
        start = int(row["start"])
        end = int(row["end"])
        protein_mm[start:end] = np.load(
            row["protein_group_id_file"], mmap_mode="r"
        )
        group_mm[start:end] = np.load(
            row["group_id_file"], mmap_mode="r"
        )

    protein_mm.flush()
    group_mm.flush()
    del protein_mm, group_mm

    os.replace(protein_tmp, out_dir / "protein_group_id.npy")
    os.replace(group_tmp, out_dir / "group_id.npy")


def write_index_streaming(out_dir: Path, manifest_rows: List[Dict]) -> None:
    """Write index.csv incrementally from chunk ID arrays."""
    index_path = out_dir / "index.csv"
    tmp = out_dir / ".index.tmp.csv"

    if tmp.exists():
        tmp.unlink()

    first = True
    for row in manifest_rows:
        start = int(row["start"])
        end = int(row["end"])
        pids = np.load(row["protein_group_id_file"], mmap_mode="r")
        gids = np.load(row["group_id_file"], mmap_mode="r")

        frame = pd.DataFrame({
            PROTEIN_GROUP_COL: np.asarray(pids),
            GROUP_COL: np.asarray(gids),
            "row_idx_in_X_ss": np.arange(start, end, dtype=np.int64),
        })
        frame.to_csv(tmp, mode="w" if first else "a", header=first, index=False)
        first = False

    os.replace(tmp, index_path)


def write_metadata_streaming(
    csv_path: Path,
    out_dir: Path,
    csv_chunk_rows: int,
    usecols: List[str],
):
    """
    Re-create metadata.csv without materializing the complete metadata dataframe.
    This is a third streaming pass, but keeps RAM bounded and preserves the
    previous output contract.
    """
    metadata_path = out_dir / "metadata.csv"
    tmp = out_dir / ".metadata.tmp.csv"
    if tmp.exists():
        tmp.unlink()

    columns = [
        PROTEIN_GROUP_COL, GROUP_COL, SEQ_COL, SS_COL, "clean_ss",
        LABEL_COL, POS_COL, PROTEIN_COL, WINDOW_COL,
    ]
    optional = ["selected_epitope", "protein_found", "sequence_match", STATUS_COL]
    columns += [c for c in optional if c in usecols]

    buffer = []
    first = True
    flush_rows = 50_000

    for record in iter_unique_group_rows(csv_path, csv_chunk_rows, usecols):
        buffer.append({c: record.get(c) for c in columns})
        if len(buffer) >= flush_rows:
            pd.DataFrame.from_records(buffer, columns=columns).to_csv(
                tmp, mode="w" if first else "a", header=first, index=False
            )
            first = False
            buffer.clear()

    if buffer:
        pd.DataFrame.from_records(buffer, columns=columns).to_csv(
            tmp, mode="w" if first else "a", header=first, index=False
        )

    os.replace(tmp, metadata_path)

def write_manifest_atomic(manifest_rows, manifest_path):
    tmp = manifest_path.with_suffix(".tmp.csv")
    pd.DataFrame(manifest_rows).to_csv(tmp, index=False)
    os.replace(tmp, manifest_path)


def process_ss_csv_cooperative(
    ss_csv_path: Path,
    model,
    device,
    rank: int,
    world_size: int,
    batch_size: int,
    chunk_size: int,
    csv_chunk_rows: int,
    model_dir: Path,
    fingerprint: str,
    force: bool,
    sanity_sample: int,
    write_metadata: bool,
):
    """
    Cooperative multi-GPU inference for ONE dataset.

    All ranks stream the same CSV deterministically and identify the same
    unique group_id rows. Output chunk k is owned exclusively by:

        owner_rank = chunk_id % world_size

    Therefore GPUs cooperate on the same dataset without gradient/DDP
    synchronization and without concurrent writes to the same files.

    Rank 0 alone:
      * removes old output when --force is used
      * writes the embedding configuration
      * after a barrier, validates every chunk
      * writes chunks_manifest.csv, global ID arrays, index.csv, metadata.csv,
        and done.flag

    RAM remains bounded: the full CSV/dataframe/SS list is never loaded.
    """
    t0 = time.time()
    ss_csv_path = ss_csv_path.expanduser().resolve()
    usecols = csv_usecols(ss_csv_path)
    out_dir = build_output_dir(ss_csv_path)
    chunks_dir = out_dir / "chunks"
    config_path = out_dir / "embedding_config.json"
    manifest_path = out_dir / "chunks_manifest.csv"
    done_flag = out_dir / "done.flag"

    if rank == 0:
        logging.info("=" * 80)
        logging.info(
            "COOPERATIVE processing %s with %d rank(s)",
            ss_csv_path, world_size,
        )
        if force and out_dir.exists():
            logging.info("--force: deleting previous SecondaryBERT outputs")
            remove_previous_outputs(out_dir)
        chunks_dir.mkdir(parents=True, exist_ok=True)

    # No rank may inspect/write the output until rank 0 has finished cleanup.
    barrier()

    if rank != 0:
        chunks_dir.mkdir(parents=True, exist_ok=True)

    # PASS 1 remains streaming and gives an exact shared N/config.
    # It costs little RAM; each rank performs it independently so there is no
    # need to broadcast Python objects or create a large temporary index.
    count_t0 = time.time()
    total = count_unique_groups_streaming(
        ss_csv_path, csv_chunk_rows, usecols
    )
    expected_chunks = (total + chunk_size - 1) // chunk_size

    logging.info(
        "rank=%d | PASS 1 complete | unique rows=%d | chunks=%d | %.1fs",
        rank, total, expected_chunks, time.time() - count_t0,
    )

    wanted = desired_config(
        ss_csv_path, total, batch_size, chunk_size, model_dir, fingerprint
    )
    wanted["csv_chunk_rows"] = int(csv_chunk_rows)
    wanted["memory_mode"] = "streaming_csv_cooperative_multigpu"
    wanted["world_size"] = int(world_size)
    wanted["distribution"] = "chunk_id_mod_world_size"
    wanted["output_shape"] = [int(total), HIDDEN_SIZE]

    if rank == 0:
        if chunks_dir.exists() and any(chunks_dir.iterdir()):
            if not force and not config_compatible(config_path, wanted):
                raise RuntimeError(
                    f"Existing output in {out_dir} is NOT compatible with the "
                    "cooperative pooled SecondaryBERT configuration/model. "
                    "Re-run this dataset with --force."
                )

        config_path.write_text(
            json.dumps(wanted, indent=2), encoding="utf-8"
        )
        logging.info(
            "Rows=%d | batch/GPU=%d | output chunk=%d | CSV chunk=%d | "
            "output=(N,%d) | GPUs=%d",
            total, batch_size, chunk_size, csv_chunk_rows,
            HIDDEN_SIZE, world_size,
        )

    barrier()

    local_chunks = 0
    local_rows = 0
    local_embed_seconds = 0.0
    sanity_embeddings = []

    # PASS 2: every rank streams deterministically, but only embeds/writes its
    # assigned chunks. This duplicates cheap CSV parsing, not GPU inference.
    for chunk_id, records in enumerate(
        stream_records_in_output_chunks(
            ss_csv_path, csv_chunk_rows, chunk_size, usecols
        )
    ):
        owner = chunk_id % world_size
        if owner != rank:
            # Critical for bounded RAM: immediately release chunks owned by
            # another GPU.
            del records
            continue

        nrows = len(records)
        start_idx = chunk_id * chunk_size
        end_idx = start_idx + nrows

        x_path = chunks_dir / f"chunk_{chunk_id:06d}_X_ss.npy"
        p_path = chunks_dir / f"chunk_{chunk_id:06d}_protein_group_id.npy"
        g_path = chunks_dir / f"chunk_{chunk_id:06d}_group_id.npy"

        if chunk_is_valid(x_path, p_path, g_path, nrows) and not force:
            logging.info(
                "rank=%d GPU=%s | skipping valid chunk %06d | %d rows",
                rank, device, chunk_id, nrows,
            )
            local_chunks += 1
            local_rows += nrows
            del records
            continue

        tmp_x = chunks_dir / f".rank{rank}_chunk_{chunk_id:06d}_X_ss.tmp.npy"
        tmp_p = chunks_dir / f".rank{rank}_chunk_{chunk_id:06d}_protein_group_id.tmp.npy"
        tmp_g = chunks_dir / f".rank{rank}_chunk_{chunk_id:06d}_group_id.tmp.npy"

        for p in (tmp_x, tmp_p, tmp_g):
            if p.exists():
                p.unlink()

        mmap = open_memmap(
            tmp_x,
            mode="w+",
            dtype=SAVE_DTYPE,
            shape=(nrows, HIDDEN_SIZE),
        )

        protein_ids = np.fromiter(
            (int(r[PROTEIN_GROUP_COL]) for r in records),
            dtype=np.int64,
            count=nrows,
        )
        group_ids = np.fromiter(
            (int(r[GROUP_COL]) for r in records),
            dtype=np.int64,
            count=nrows,
        )

        chunk_t0 = time.time()

        for local_start in range(0, nrows, batch_size):
            local_end = min(local_start + batch_size, nrows)
            ss_batch = [
                r["clean_ss"] for r in records[local_start:local_end]
            ]

            x_batch = embed_batch(ss_batch, model, device)
            mmap[local_start:local_end] = x_batch

            if len(sanity_embeddings) < sanity_sample:
                take = min(
                    sanity_sample - len(sanity_embeddings),
                    len(x_batch),
                )
                sanity_embeddings.extend(x_batch[:take].copy())

        mmap.flush()
        del mmap

        np.save(tmp_p, protein_ids)
        np.save(tmp_g, group_ids)
        del protein_ids, group_ids

        if not chunk_is_valid(tmp_x, tmp_p, tmp_g, nrows):
            raise RuntimeError(
                f"Rank {rank}: temporary chunk {chunk_id} failed validation"
            )

        # Atomic publication. No other rank owns these paths.
        os.replace(tmp_x, x_path)
        os.replace(tmp_p, p_path)
        os.replace(tmp_g, g_path)

        elapsed = time.time() - chunk_t0
        local_embed_seconds += elapsed
        local_chunks += 1
        local_rows += nrows

        logging.info(
            "rank=%d GPU=%s | Saved chunk %06d | global rows %d:%d/%d | "
            "%.1f rows/s | %.1fs",
            rank, device, chunk_id, start_idx, end_idx, total,
            nrows / max(elapsed, 1e-9), elapsed,
        )

        del records

    if sanity_embeddings:
        sample = np.asarray(sanity_embeddings, dtype=np.float32)
        if not np.isfinite(sample).all():
            raise RuntimeError(
                f"Rank {rank}: NaN/Inf in embedding sanity sample"
            )
        mean_dim_std = float(np.mean(np.std(sample, axis=0)))
        if mean_dim_std < 1e-7:
            raise RuntimeError(
                f"Rank {rank}: embeddings are effectively constant"
            )
        logging.info(
            "rank=%d | Real-data embedding sanity PASSED | n=%d | "
            "mean per-dimension std=%.6g",
            rank, len(sample), mean_dim_std,
        )
        del sample, sanity_embeddings

    logging.info(
        "rank=%d GPU=%s | local work complete | chunks=%d | rows=%d | "
        "GPU-embedding time=%.1fs | mean=%.1f rows/s",
        rank, device, local_chunks, local_rows, local_embed_seconds,
        local_rows / max(local_embed_seconds, 1e-9),
    )

    # Wait until every GPU has atomically published all its chunks.
    barrier()

    if rank == 0:
        finalize_t0 = time.time()
        manifest_rows = []

        # Validate ALL chunks in global order and reconstruct exact ranges.
        global_start = 0
        for chunk_id in range(expected_chunks):
            nrows = min(chunk_size, total - global_start)
            start_idx = global_start
            end_idx = start_idx + nrows

            x_path = chunks_dir / f"chunk_{chunk_id:06d}_X_ss.npy"
            p_path = chunks_dir / f"chunk_{chunk_id:06d}_protein_group_id.npy"
            g_path = chunks_dir / f"chunk_{chunk_id:06d}_group_id.npy"

            if not chunk_is_valid(x_path, p_path, g_path, nrows):
                raise RuntimeError(
                    f"Final validation FAILED for chunk {chunk_id:06d}: "
                    f"expected {nrows} rows"
                )

            manifest_rows.append({
                "chunk_id": chunk_id,
                "start": start_idx,
                "end": end_idx,
                "n_rows": nrows,
                "x_file": str(x_path),
                "protein_group_id_file": str(p_path),
                "group_id_file": str(g_path),
            })
            global_start = end_idx

        if global_start != total:
            raise RuntimeError(
                f"Final coverage mismatch: {global_start} != {total}"
            )

        write_manifest_atomic(manifest_rows, manifest_path)

        # Global arrays/index are built from mmap-backed chunk arrays, so no
        # full-ID vector is retained in memory.
        write_global_ids_from_chunks(out_dir, manifest_rows, total)
        write_index_streaming(out_dir, manifest_rows)

        if write_metadata:
            metadata_t0 = time.time()
            write_metadata_streaming(
                ss_csv_path, out_dir, csv_chunk_rows, usecols
            )
            logging.info(
                "metadata.csv streamed in %.1fs",
                time.time() - metadata_t0,
            )

        done_flag.write_text(
            json.dumps({
                "status": "done",
                "rows": total,
                "chunks": expected_chunks,
                "model_fingerprint": fingerprint,
                "shape": [total, HIDDEN_SIZE],
                "elapsed_seconds": time.time() - t0,
                "finalize_seconds": time.time() - finalize_t0,
                "memory_mode": "streaming_csv_cooperative_multigpu",
                "world_size": world_size,
                "distribution": "chunk_id_mod_world_size",
            }, indent=2) + "\n",
            encoding="utf-8",
        )

        logging.info(
            "FINALIZED %s | rows=%d | chunks=%d | GPUs=%d | elapsed=%.1f min",
            ss_csv_path.name, total, expected_chunks,
            world_size, (time.time() - t0) / 60.0,
        )

    # Do not allow a rank to move to the next dataset while rank 0 is still
    # generating global files/metadata for this one.
    barrier()

def find_ss_files(species: Optional[str] = None):
    files = sorted(DATA_INTERMEDIATE.glob("**/classification_*_ss.csv"))
    if species is not None:
        files = [p for p in files if f"/{species}/" in str(p)]
    return files


def parse_args():
    p = argparse.ArgumentParser(
        description="Fast pooled SecondaryBERT embeddings with multi-GPU file sharding."
    )
    p.add_argument("--csv", default=None)
    p.add_argument("--species", choices=["human", "mouse"], default=None)
    p.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    p.add_argument(
        "--csv-chunk-rows",
        type=int,
        default=100_000,
        help="Source CSV rows read at once. Lower values reduce RAM further.",
    )
    p.add_argument(
        "--no-metadata",
        action="store_true",
        help="Skip metadata.csv creation if it is not needed downstream.",
    )
    p.add_argument("--force", action="store_true")
    p.add_argument(
        "--sanity-sample",
        type=int,
        default=4096,
        help="Real embeddings retained only for a final variability sanity check.",
    )
    p.add_argument(
        "--allow-cpu",
        action="store_true",
        help="Allow CPU execution. By default this script requires CUDA.",
    )
    p.add_argument(
        "--monitor-interval",
        type=float,
        default=60.0,
        help="Seconds between RAM/GPU resource log lines (default: 60).",
    )
    return p.parse_args()


def main():
    args = parse_args()
    rank, local_rank, world_size, device = init_distributed()
    setup_logging(rank)

    if device.type != "cuda" and not args.allow_cpu:
        raise RuntimeError("CUDA not available. Use --allow-cpu only intentionally.")

    if not args.model_dir.is_dir():
        raise FileNotFoundError(args.model_dir)

    validate_tokenizer(args.model_dir)
    fingerprint = model_fingerprint(args.model_dir)
    model = load_model(args.model_dir, device)

    sanity_std, sanity_diff = model_sanity_check(model, device)

    # INFO logging is enabled for every rank in cooperative mode so throughput
    # and resources from both GPUs are visible.
    logging.info(
        "rank=%d | Corrected SecondaryBERT: %s",
        rank, args.model_dir,
    )
    logging.info(
        "rank=%d | Tokenizer sanity PASSED: C/H/E = 5/6/7",
        rank,
    )
    logging.info(
        "rank=%d | Model embedding sanity PASSED | std=%.6g | max_diff=%.6g",
        rank, sanity_std, sanity_diff,
    )

    if rank == 0:
        logging.info(
            "COOPERATIVE MODE | world_size=%d | visible GPUs=%s | batch/GPU=%d",
            world_size,
            os.environ.get("CUDA_VISIBLE_DEVICES", "default"),
            args.batch_size,
        )

    if args.csv is not None:
        all_files = [Path(args.csv).expanduser().resolve()]
    else:
        all_files = find_ss_files(args.species)

    if rank == 0:
        logging.info(
            "Total datasets discovered: %d | every dataset will use all %d GPU(s)",
            len(all_files), world_size,
        )

    monitor = ResourceMonitor(
        rank=rank,
        local_rank=local_rank,
        interval=args.monitor_interval,
    )
    monitor.start()

    try:
        # IMPORTANT: every rank iterates over exactly the same file list/order.
        for dataset_i, csv_path in enumerate(all_files, start=1):
            if rank == 0:
                logging.info(
                    "DATASET %d/%d | %s",
                    dataset_i, len(all_files), csv_path,
                )

            process_ss_csv_cooperative(
                ss_csv_path=csv_path,
                model=model,
                device=device,
                rank=rank,
                world_size=world_size,
                batch_size=args.batch_size,
                chunk_size=args.chunk_size,
                csv_chunk_rows=args.csv_chunk_rows,
                model_dir=args.model_dir,
                fingerprint=fingerprint,
                force=args.force,
                sanity_sample=args.sanity_sample,
                write_metadata=not args.no_metadata,
            )

        barrier()

        if rank == 0:
            logging.info(
                "All SecondaryBERT datasets finished successfully "
                "with cooperative multi-GPU inference."
            )
    finally:
        monitor.stop()
        cleanup_distributed()


if __name__ == "__main__":
    main()