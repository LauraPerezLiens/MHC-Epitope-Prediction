#!/usr/bin/env python3

from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd


# =============================================================================
# CONFIGURATION
# =============================================================================

ROOT = Path("/data/nap/lperez_nn/data/data_input_nn")

EXPECTED_DATASETS = [
    ("human", "mhc-I",  "HLA-A"),
    ("human", "mhc-I",  "HLA-B"),
    ("human", "mhc-I",  "HLA-C"),
    ("human", "mhc-II", "HLA-DP"),
    ("human", "mhc-II", "HLA-DQ"),
    ("human", "mhc-II", "HLA-DR"),
    ("mouse", "mhc-I",  "H2-D"),
    ("mouse", "mhc-I",  "H2-K"),
    ("mouse", "mhc-I",  "H2-L"),
    ("mouse", "mhc-II", "H2-IA"),
    ("mouse", "mhc-II", "H2-IE"),
]

EXPECTED_DIM = 768
EXPECTED_DTYPE = np.dtype("float32")

# Numerical checks are sampled to avoid reading every embedding value.
SAMPLE_PER_CHUNK = 512

# group_id ordering/uniqueness is checked block-wise.
ID_BLOCK_SIZE = 1_000_000


# =============================================================================
# PRINT HELPERS
# =============================================================================

def ok(msg):
    print(f"    [OK]   {msg}")


def warn(msg):
    print(f"    [WARN] {msg}")


def fail(msg):
    print(f"    [FAIL] {msg}")


# =============================================================================
# FILE HELPERS
# =============================================================================

def find_output_dir(species, mhc, allele):
    """
    Find the SecondaryBERT output directory for one dataset.
    """

    parent = ROOT / species / mhc / allele

    if not parent.exists():
        return None

    matches = sorted(parent.glob("*_SecondaryBERT_by_group"))

    if len(matches) == 1:
        return matches[0]

    if len(matches) == 0:
        return None

    raise RuntimeError(
        f"Multiple SecondaryBERT directories found under {parent}: "
        + ", ".join(str(x) for x in matches)
    )


def load_manifest(path):
    """
    Read and validate the basic manifest columns.
    """

    df = pd.read_csv(path)

    required = {
        "chunk_id",
        "start",
        "end",
        "n_rows",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Manifest missing columns: {sorted(missing)}"
        )

    return (
        df
        .sort_values("chunk_id")
        .reset_index(drop=True)
    )


def sample_indices(n, max_samples=SAMPLE_PER_CHUNK):
    """
    Return evenly distributed row indices across a chunk.
    """

    if n <= 0:
        return np.array([], dtype=np.int64)

    if n <= max_samples:
        return np.arange(n, dtype=np.int64)

    return np.linspace(
        0,
        n - 1,
        max_samples,
        dtype=np.int64,
    )


def classify_chunk_files(chunks_dir):
    """
    Classify chunk files into mutually exclusive categories.

    IMPORTANT:
    A naive glob such as:

        chunk_*_group_id.npy

    also matches:

        chunk_*_protein_group_id.npy

    Therefore files are classified explicitly and in the correct order.
    """

    x_files = []
    gid_files = []
    pgid_files = []

    if not chunks_dir.exists():
        return x_files, gid_files, pgid_files

    for path in chunks_dir.iterdir():

        if not path.is_file():
            continue

        name = path.name

        if name.endswith("_X_ss.npy"):
            x_files.append(path)

        elif name.endswith("_protein_group_id.npy"):
            pgid_files.append(path)

        elif name.endswith("_group_id.npy"):
            gid_files.append(path)

    x_files.sort()
    gid_files.sort()
    pgid_files.sort()

    return x_files, gid_files, pgid_files


# =============================================================================
# DATASET CHECK
# =============================================================================

def check_dataset(species, mhc, allele):

    dataset_name = f"{species}/{mhc}/{allele}"

    print()
    print("=" * 100)
    print(f"DATASET: {dataset_name}")
    print("=" * 100)

    errors = []
    warnings = []

    # -------------------------------------------------------------------------
    # Find output directory
    # -------------------------------------------------------------------------

    try:
        out_dir = find_output_dir(
            species,
            mhc,
            allele,
        )

    except Exception as exc:

        msg = str(exc)
        fail(msg)

        return {
            "dataset": dataset_name,
            "status": "FAIL",
            "rows": 0,
            "chunks": 0,
            "errors": [msg],
            "warnings": [],
        }

    if out_dir is None:

        msg = "SecondaryBERT output directory not found"
        fail(msg)

        return {
            "dataset": dataset_name,
            "status": "FAIL",
            "rows": 0,
            "chunks": 0,
            "errors": [msg],
            "warnings": [],
        }

    print(f"    Directory: {out_dir}")

    chunks_dir = out_dir / "chunks"

    manifest_path = out_dir / "chunks_manifest.csv"
    global_gid_path = out_dir / "group_id.npy"
    global_pgid_path = out_dir / "protein_group_id.npy"

    config_path = out_dir / "embedding_config.json"
    done_path = out_dir / "done.flag"

    index_path = out_dir / "index.csv"
    metadata_path = out_dir / "metadata.csv"

    # =========================================================================
    # 1. REQUIRED FILES
    # =========================================================================

    required_paths = {
        "chunks/": chunks_dir,
        "chunks_manifest.csv": manifest_path,
        "group_id.npy": global_gid_path,
        "protein_group_id.npy": global_pgid_path,
        "embedding_config.json": config_path,
        "done.flag": done_path,
    }

    for label, path in required_paths.items():

        if path.exists():
            ok(f"{label} exists")

        else:
            msg = f"{label} missing"
            fail(msg)
            errors.append(msg)

    optional_paths = {
        "index.csv": index_path,
        "metadata.csv": metadata_path,
    }

    for label, path in optional_paths.items():

        if path.exists():
            ok(f"{label} exists")

        else:
            msg = f"{label} missing"
            warn(msg)
            warnings.append(msg)

    if errors:

        return {
            "dataset": dataset_name,
            "status": "FAIL",
            "rows": 0,
            "chunks": 0,
            "errors": errors,
            "warnings": warnings,
        }

    # =========================================================================
    # 2. CONFIGURATION
    # =========================================================================

    try:

        with open(config_path) as f:
            config = json.load(f)

        print("    Config:")

        for key in [
            "model_dir",
            "hidden_size",
            "window_size",
            "output_shape",
            "dtype",
        ]:
            if key in config:
                print(
                    f"        {key}: "
                    f"{config[key]}"
                )

        config_text = json.dumps(config)

        # Detect accidental reference to the OLD model.
        if "secondary_bert_mlm" in config_text:

            msg = (
                "Configuration appears to reference old "
                "'secondary_bert_mlm' model"
            )

            fail(msg)
            errors.append(msg)

        else:

            ok(
                "config does not reference old "
                "secondary_bert_mlm"
            )

        # Hidden size
        if "hidden_size" in config:

            if int(config["hidden_size"]) == EXPECTED_DIM:

                ok(
                    f"config hidden_size = "
                    f"{EXPECTED_DIM}"
                )

            else:

                msg = (
                    f"config hidden_size="
                    f"{config['hidden_size']}, "
                    f"expected={EXPECTED_DIM}"
                )

                fail(msg)
                errors.append(msg)

        # dtype
        if "dtype" in config:

            if str(config["dtype"]) == "float32":

                ok("config dtype = float32")

            else:

                msg = (
                    f"config dtype="
                    f"{config['dtype']}, "
                    f"expected=float32"
                )

                fail(msg)
                errors.append(msg)

    except Exception as exc:

        msg = (
            "Could not read "
            f"embedding_config.json: {exc}"
        )

        fail(msg)
        errors.append(msg)

    # =========================================================================
    # 3. MANIFEST
    # =========================================================================

    try:

        manifest = load_manifest(
            manifest_path
        )

    except Exception as exc:

        msg = (
            f"Could not read manifest: {exc}"
        )

        fail(msg)
        errors.append(msg)

        return {
            "dataset": dataset_name,
            "status": "FAIL",
            "rows": 0,
            "chunks": 0,
            "errors": errors,
            "warnings": warnings,
        }

    n_chunks = len(manifest)

    print(
        f"    Manifest chunks: "
        f"{n_chunks:,}"
    )

    # -------------------------------------------------------------------------
    # chunk_id continuity
    # -------------------------------------------------------------------------

    expected_chunk_ids = np.arange(
        n_chunks,
        dtype=np.int64,
    )

    actual_chunk_ids = (
        manifest["chunk_id"]
        .to_numpy(dtype=np.int64)
    )

    if np.array_equal(
        expected_chunk_ids,
        actual_chunk_ids,
    ):

        ok(
            "chunk_id sequence is contiguous"
        )

    else:

        msg = (
            "chunk_id sequence is not "
            "contiguous from 0"
        )

        fail(msg)
        errors.append(msg)

    # -------------------------------------------------------------------------
    # Manifest ranges
    # -------------------------------------------------------------------------

    starts = (
        manifest["start"]
        .to_numpy(dtype=np.int64)
    )

    ends = (
        manifest["end"]
        .to_numpy(dtype=np.int64)
    )

    n_rows = (
        manifest["n_rows"]
        .to_numpy(dtype=np.int64)
    )

    if np.all(
        ends - starts == n_rows
    ):

        ok(
            "manifest end - start == n_rows"
        )

    else:

        msg = (
            "manifest contains inconsistent "
            "start/end/n_rows"
        )

        fail(msg)
        errors.append(msg)

    if len(manifest) > 1:

        if np.array_equal(
            starts[1:],
            ends[:-1],
        ):

            ok(
                "manifest ranges are contiguous"
            )

        else:

            msg = (
                "manifest ranges contain "
                "gaps or overlaps"
            )

            fail(msg)
            errors.append(msg)

    if len(manifest) > 0:

        if starts[0] == 0:

            ok(
                "first manifest start = 0"
            )

        else:

            msg = (
                f"first manifest start is "
                f"{starts[0]}, expected 0"
            )

            fail(msg)
            errors.append(msg)

    total_rows = int(
        n_rows.sum()
    )

    if (
        len(manifest) > 0
        and int(ends[-1]) == total_rows
    ):

        ok(
            f"manifest total rows = "
            f"{total_rows:,}"
        )

    else:

        msg = (
            "last manifest end does not "
            f"equal total rows ({total_rows:,})"
        )

        fail(msg)
        errors.append(msg)

    # =========================================================================
    # 4. PHYSICAL CHUNK FILES
    # =========================================================================

    (
        x_files,
        gid_files,
        pgid_files,
    ) = classify_chunk_files(
        chunks_dir
    )

    print(
        f"    Physical files: "
        f"X={len(x_files)}, "
        f"group_id={len(gid_files)}, "
        f"protein_group_id={len(pgid_files)}"
    )

    if len(x_files) == n_chunks:

        ok(
            "number of X chunks "
            "matches manifest"
        )

    else:

        msg = (
            f"X chunk count "
            f"{len(x_files)} "
            f"!= manifest {n_chunks}"
        )

        fail(msg)
        errors.append(msg)

    if len(gid_files) == n_chunks:

        ok(
            "number of group_id chunks "
            "matches manifest"
        )

    else:

        msg = (
            f"group_id chunk count "
            f"{len(gid_files)} "
            f"!= manifest {n_chunks}"
        )

        fail(msg)
        errors.append(msg)

    if len(pgid_files) == n_chunks:

        ok(
            "number of protein_group_id "
            "chunks matches manifest"
        )

    else:

        msg = (
            f"protein_group_id chunk count "
            f"{len(pgid_files)} "
            f"!= manifest {n_chunks}"
        )

        fail(msg)
        errors.append(msg)

    # =========================================================================
    # 5. GLOBAL ID ARRAYS
    # =========================================================================

    global_gid = None
    global_pgid = None

    try:

        global_gid = np.load(
            global_gid_path,
            mmap_mode="r",
        )

        global_pgid = np.load(
            global_pgid_path,
            mmap_mode="r",
        )

        print(
            f"    Global group_id: "
            f"shape={global_gid.shape}, "
            f"dtype={global_gid.dtype}"
        )

        print(
            f"    Global protein_group_id: "
            f"shape={global_pgid.shape}, "
            f"dtype={global_pgid.dtype}"
        )

        if global_gid.ndim != 1:

            msg = (
                "global group_id is not "
                "1-dimensional"
            )

            fail(msg)
            errors.append(msg)

        if global_pgid.ndim != 1:

            msg = (
                "global protein_group_id "
                "is not 1-dimensional"
            )

            fail(msg)
            errors.append(msg)

        if len(global_gid) == total_rows:

            ok(
                "global group_id length "
                "matches manifest"
            )

        else:

            msg = (
                f"global group_id length="
                f"{len(global_gid):,}, "
                f"expected={total_rows:,}"
            )

            fail(msg)
            errors.append(msg)

        if len(global_pgid) == total_rows:

            ok(
                "global protein_group_id "
                "length matches manifest"
            )

        else:

            msg = (
                "global protein_group_id "
                f"length={len(global_pgid):,}, "
                f"expected={total_rows:,}"
            )

            fail(msg)
            errors.append(msg)

    except Exception as exc:

        msg = (
            "Could not mmap global ID "
            f"arrays: {exc}"
        )

        fail(msg)
        errors.append(msg)

        global_gid = None
        global_pgid = None

    # =========================================================================
    # 6. CHECK EVERY CHUNK
    # =========================================================================

    numerical_stds = []
    numerical_dim_stds = []
    numerical_max_diffs = []

    sample_global_min = float("inf")
    sample_global_max = float("-inf")

    chunk_rows_total = 0

    print()
    print("    Checking every chunk...")

    for row in manifest.itertuples(
        index=False
    ):

        cid = int(row.chunk_id)
        expected_n = int(row.n_rows)

        start = int(row.start)
        end = int(row.end)

        prefix = (
            f"chunk_{cid:06d}"
        )

        x_path = (
            chunks_dir
            / f"{prefix}_X_ss.npy"
        )

        gid_path = (
            chunks_dir
            / f"{prefix}_group_id.npy"
        )

        pgid_path = (
            chunks_dir
            / f"{prefix}_protein_group_id.npy"
        )

        chunk_errors = []

        # ---------------------------------------------------------------------
        # Required physical files
        # ---------------------------------------------------------------------

        for path in [
            x_path,
            gid_path,
            pgid_path,
        ]:

            if not path.exists():

                chunk_errors.append(
                    f"missing {path.name}"
                )

        if chunk_errors:

            msg = (
                f"{prefix}: "
                + "; ".join(chunk_errors)
            )

            fail(msg)
            errors.append(msg)

            continue

        # ---------------------------------------------------------------------
        # Load mmap
        # ---------------------------------------------------------------------

        try:

            x = np.load(
                x_path,
                mmap_mode="r",
            )

            gid = np.load(
                gid_path,
                mmap_mode="r",
            )

            pgid = np.load(
                pgid_path,
                mmap_mode="r",
            )

            # -----------------------------------------------------------------
            # X shape
            # -----------------------------------------------------------------

            expected_shape = (
                expected_n,
                EXPECTED_DIM,
            )

            if x.shape != expected_shape:

                chunk_errors.append(
                    f"X shape={x.shape}, "
                    f"expected={expected_shape}"
                )

            # -----------------------------------------------------------------
            # ID lengths
            # -----------------------------------------------------------------

            if len(gid) != expected_n:

                chunk_errors.append(
                    f"group_id rows="
                    f"{len(gid)}, "
                    f"expected={expected_n}"
                )

            if len(pgid) != expected_n:

                chunk_errors.append(
                    "protein_group_id rows="
                    f"{len(pgid)}, "
                    f"expected={expected_n}"
                )

            # -----------------------------------------------------------------
            # dtype
            # -----------------------------------------------------------------

            if x.dtype != EXPECTED_DTYPE:

                chunk_errors.append(
                    f"X dtype={x.dtype}, "
                    "expected=float32"
                )

            # -----------------------------------------------------------------
            # Numerical sample
            # -----------------------------------------------------------------

            if expected_n > 0:

                idx = sample_indices(
                    expected_n
                )

                sample = np.asarray(
                    x[idx]
                )

                if not np.isfinite(
                    sample
                ).all():

                    chunk_errors.append(
                        "NaN/Inf detected "
                        "in embedding sample"
                    )

                std = float(
                    sample.std()
                )

                dim_std = float(
                    np.mean(
                        np.std(
                            sample,
                            axis=0,
                        )
                    )
                )

                max_diff = float(
                    np.max(
                        np.abs(
                            sample
                            - sample[0]
                        )
                    )
                )

                sample_min = float(
                    sample.min()
                )

                sample_max = float(
                    sample.max()
                )

                numerical_stds.append(
                    std
                )

                numerical_dim_stds.append(
                    dim_std
                )

                numerical_max_diffs.append(
                    max_diff
                )

                sample_global_min = min(
                    sample_global_min,
                    sample_min,
                )

                sample_global_max = max(
                    sample_global_max,
                    sample_max,
                )

                if max_diff <= 1e-7:

                    chunk_errors.append(
                        "sample embeddings "
                        "appear constant"
                    )

                if std <= 1e-7:

                    chunk_errors.append(
                        "sample embedding std "
                        "approximately zero"
                    )

                if dim_std <= 1e-7:

                    chunk_errors.append(
                        "mean per-dimension std "
                        "approximately zero"
                    )

            # -----------------------------------------------------------------
            # Chunk group_id vs global group_id
            # -----------------------------------------------------------------

            if (
                global_gid is not None
                and len(global_gid) >= end
            ):

                if not np.array_equal(
                    gid,
                    global_gid[start:end],
                ):

                    chunk_errors.append(
                        "chunk group_id != "
                        "global group_id slice"
                    )

            # -----------------------------------------------------------------
            # Chunk protein_group_id vs global protein_group_id
            # -----------------------------------------------------------------

            if (
                global_pgid is not None
                and len(global_pgid) >= end
            ):

                if not np.array_equal(
                    pgid,
                    global_pgid[start:end],
                ):

                    chunk_errors.append(
                        "chunk protein_group_id "
                        "!= global "
                        "protein_group_id slice"
                    )

            # -----------------------------------------------------------------
            # Result
            # -----------------------------------------------------------------

            if chunk_errors:

                msg = (
                    f"{prefix}: "
                    + "; ".join(
                        chunk_errors
                    )
                )

                fail(msg)
                errors.append(msg)

            else:

                print(
                    f"        OK {prefix} | "
                    f"rows={expected_n:,} | "
                    f"shape={x.shape}"
                )

            chunk_rows_total += (
                expected_n
            )

        except Exception as exc:

            msg = (
                f"{prefix}: "
                f"exception: {exc}"
            )

            fail(msg)
            errors.append(msg)

    # =========================================================================
    # 7. CROSS-CHUNK TOTALS
    # =========================================================================

    if chunk_rows_total == total_rows:

        ok(
            "sum of checked chunk rows = "
            f"{chunk_rows_total:,}"
        )

    else:

        msg = (
            f"checked chunk rows="
            f"{chunk_rows_total:,}, "
            f"manifest={total_rows:,}"
        )

        fail(msg)
        errors.append(msg)

    # =========================================================================
    # 8. GLOBAL GROUP_ID ORDER + DUPLICATES
    # =========================================================================

    if (
        global_gid is not None
        and len(global_gid) > 0
    ):

        duplicate_or_unsorted = False

        previous_last = None

        for block_start in range(
            0,
            len(global_gid),
            ID_BLOCK_SIZE,
        ):

            block_end = min(
                block_start
                + ID_BLOCK_SIZE,
                len(global_gid),
            )

            block = np.asarray(
                global_gid[
                    block_start:
                    block_end
                ]
            )

            if len(block) == 0:
                continue

            # Cross-block boundary
            if previous_last is not None:

                if block[0] <= previous_last:

                    duplicate_or_unsorted = True
                    break

            # Within block
            if (
                len(block) > 1
                and np.any(
                    block[1:]
                    <= block[:-1]
                )
            ):

                duplicate_or_unsorted = True
                break

            previous_last = block[-1]

        if duplicate_or_unsorted:

            msg = (
                "global group_id is not "
                "strictly increasing "
                "(duplicate or ordering problem)"
            )

            fail(msg)
            errors.append(msg)

        else:

            ok(
                "global group_id is strictly "
                "increasing (no duplicates)"
            )

    # =========================================================================
    # 9. CONFIG OUTPUT SHAPE VS REAL OUTPUT
    # =========================================================================

    try:

        output_shape = config.get(
            "output_shape"
        )

        if output_shape is not None:

            expected_config_shape = [
                total_rows,
                EXPECTED_DIM,
            ]

            if (
                list(output_shape)
                == expected_config_shape
            ):

                ok(
                    "config output_shape "
                    "matches real dataset"
                )

            else:

                msg = (
                    "config output_shape="
                    f"{output_shape}, "
                    "expected="
                    f"{expected_config_shape}"
                )

                fail(msg)
                errors.append(msg)

    except Exception as exc:

        msg = (
            "Could not validate config "
            f"output_shape: {exc}"
        )

        warn(msg)
        warnings.append(msg)

    # =========================================================================
    # 10. NUMERICAL SUMMARY
    # =========================================================================

    if numerical_stds:

        print()
        print(
            "    Numerical embedding summary:"
        )

        print(
            "        chunk sample std: "
            f"min={min(numerical_stds):.6f} "
            f"mean={np.mean(numerical_stds):.6f} "
            f"max={max(numerical_stds):.6f}"
        )

        print(
            "        mean per-dimension std: "
            f"min={min(numerical_dim_stds):.6f} "
            f"mean={np.mean(numerical_dim_stds):.6f} "
            f"max={max(numerical_dim_stds):.6f}"
        )

        print(
            "        max row difference: "
            f"min={min(numerical_max_diffs):.6f} "
            f"mean={np.mean(numerical_max_diffs):.6f} "
            f"max={max(numerical_max_diffs):.6f}"
        )

        print(
            "        sampled value range: "
            f"[{sample_global_min:.6f}, "
            f"{sample_global_max:.6f}]"
        )

    # =========================================================================
    # FINAL DATASET STATUS
    # =========================================================================

    status = (
        "PASS"
        if not errors
        else "FAIL"
    )

    print()

    if status == "PASS":

        print(
            f"    >>> PASS {dataset_name} | "
            f"{total_rows:,} rows | "
            f"{n_chunks:,} chunks"
        )

    else:

        print(
            f"    >>> FAIL {dataset_name} | "
            f"{len(errors)} error(s)"
        )

    return {
        "dataset": dataset_name,
        "status": status,
        "rows": total_rows,
        "chunks": n_chunks,
        "errors": errors,
        "warnings": warnings,
        "mean_sample_std": (
            float(
                np.mean(
                    numerical_stds
                )
            )
            if numerical_stds
            else None
        ),
        "mean_dimension_std": (
            float(
                np.mean(
                    numerical_dim_stds
                )
            )
            if numerical_dim_stds
            else None
        ),
    }


# =============================================================================
# MAIN
# =============================================================================

def main():

    print(
        "=" * 100
    )

    print(
        "SECONDARYBERT EMBEDDING "
        "INTEGRITY CHECK"
    )

    print(
        f"Root: {ROOT}"
    )

    print(
        f"Expected datasets: "
        f"{len(EXPECTED_DATASETS)}"
    )

    print(
        f"Expected embedding dimension: "
        f"{EXPECTED_DIM}"
    )

    print(
        "=" * 100
    )

    results = []

    for (
        species,
        mhc,
        allele,
    ) in EXPECTED_DATASETS:

        result = check_dataset(
            species,
            mhc,
            allele,
        )

        results.append(
            result
        )

    # =========================================================================
    # GLOBAL SUMMARY
    # =========================================================================

    print()
    print()

    print(
        "#" * 100
    )

    print(
        "FINAL SUMMARY"
    )

    print(
        "#" * 100
    )

    total_rows = 0
    total_chunks = 0

    n_pass = 0
    n_fail = 0

    for result in results:

        status = result["status"]

        if status == "PASS":
            n_pass += 1
        else:
            n_fail += 1

        total_rows += (
            result.get(
                "rows",
                0,
            )
        )

        total_chunks += (
            result.get(
                "chunks",
                0,
            )
        )

        print(
            f"{status:4s} | "
            f"{result['dataset']:25s} | "
            f"rows="
            f"{result.get('rows', 0):>12,} | "
            f"chunks="
            f"{result.get('chunks', 0):>5,}"
        )

    print(
        "-" * 100
    )

    print(
        f"Datasets PASS : "
        f"{n_pass}/{len(results)}"
    )

    print(
        f"Datasets FAIL : "
        f"{n_fail}/{len(results)}"
    )

    print(
        f"Total rows    : "
        f"{total_rows:,}"
    )

    print(
        f"Total chunks  : "
        f"{total_chunks:,}"
    )

    print()

    # =========================================================================
    # SUCCESS
    # =========================================================================

    if n_fail == 0:

        print(
            "=" * 100
        )

        print(
            "ALL SECONDARYBERT "
            "DATASETS PASSED"
        )

        print(
            "=" * 100
        )

        print(
            "Validated:"
        )

        print(
            "  ✓ all 11 expected datasets"
        )

        print(
            "  ✓ corrected SecondaryBERT "
            "configuration"
        )

        print(
            "  ✓ completion markers"
        )

        print(
            "  ✓ manifests"
        )

        print(
            "  ✓ contiguous chunk ranges"
        )

        print(
            "  ✓ physical chunk counts"
        )

        print(
            "  ✓ X/group_id/protein_group_id "
            "file separation"
        )

        print(
            "  ✓ (N, 768) embedding shape"
        )

        print(
            "  ✓ float32 embeddings"
        )

        print(
            "  ✓ sampled embeddings finite"
        )

        print(
            "  ✓ sampled embeddings "
            "non-constant"
        )

        print(
            "  ✓ chunk IDs match global "
            "ID arrays"
        )

        print(
            "  ✓ global group_id unique "
            "and ordered"
        )

        print(
            "  ✓ config output_shape "
            "matches real output"
        )

        return 0

    # =========================================================================
    # FAILURE
    # =========================================================================

    print(
        "=" * 100
    )

    print(
        "SECONDARYBERT CHECK FAILED"
    )

    print(
        "=" * 100
    )

    for result in results:

        if result["status"] != "FAIL":
            continue

        print(
            f"\n{result['dataset']}:"
        )

        for error in result["errors"]:

            print(
                f"  - {error}"
            )

    return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )