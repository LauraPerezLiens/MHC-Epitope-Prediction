"""Publish a single deterministic split manifest keyed by exact primary sequence."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from zoneinfo import ZoneInfo

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from data_pipeline.scripts.rebuild_iedb.dataset_views import load_manifest, require

ROOT = Path("results/nap_cnb_v2_dataset_views")
SELECTION = Path("results/nap_cnb_v2_final_selection/selection.json")
NAMES = ("train", "validation", "test")
VERSION = "primary-blake2b-mod10-v1"
FILES = ("base_dataset", "global_dataset", "global_labels", "window_provenance", "legacy_group_links")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array(table, name):
    return table[name].combine_chunks()


def indexes(keys, catalog):
    result = pc.index_in(keys, value_set=catalog)
    require(result.null_count == 0, "A key is missing from its catalog")
    return result.to_numpy()


def assign(sequences, seed):
    key = seed.to_bytes(8, "little")
    require(pc.all(pc.equal(pc.binary_length(sequences), 25)).as_py(), "Unexpected primary length")
    data = memoryview(sequences.buffers()[2])
    offset = int(np.frombuffer(sequences.buffers()[1], dtype="<i4")[sequences.offset])
    count = len(sequences)
    buckets = np.fromiter(
        (int.from_bytes(hashlib.blake2b(data[pos:pos + 25], key=key, digest_size=8).digest(), "little") % 10
         for pos in range(offset, offset + 25 * count, 25)), dtype=np.uint8, count=count,
    )
    return np.where(buckets < 8, 0, buckets - 7).astype(np.uint8)


def distribution(splits, labels, weights=None):
    if weights is None:
        weights = np.ones(len(splits), dtype=np.int32)
    result = np.bincount(splits * 2 + labels, weights=weights, minlength=6).astype(np.int64).reshape(3, 2)
    return {name: {"negative": int(n), "positive": int(p), "rows": int(n + p)}
            for name, (n, p) in zip(NAMES, result)}


def add_distributions(groups):
    return {split: {field: sum(g[split][field] for g in groups)
                    for field in ("negative", "positive", "rows")} for split in NAMES}


def historical_and_original(family, source, base, base_splits, proteins):
    bounds = [("window_id", ">=", family + "|"), ("window_id", "<", family + "}")]
    provenance = pq.read_table(ROOT / "window_provenance.parquet", filters=bounds)
    ids = array(provenance, "window_id")
    require(pc.count_distinct(ids).as_py() == len(ids), f"Repeated window: {family}")
    base_rows = indexes(array(provenance, "base_id"), array(base, "base_id"))
    require(np.array_equal(np.bincount(base_rows, minlength=len(base)),
                           array(base, "observation_count").to_numpy()), f"Provenance cardinality: {family}")
    links = pq.read_table(ROOT / "legacy_group_links.parquet", filters=bounds,
                          columns=["window_id", "legacy_source_file", "group_id"])
    (source_file,) = pc.unique(links["legacy_source_file"]).to_pylist()
    require(Path(source_file).name.endswith(f"_{family}.csv"), f"Unexpected group scope: {source_file}")
    link_groups = array(links, "group_id")
    require(pc.count_distinct(link_groups).as_py() == len(links), f"Historical group fans out: {family}")
    link_rows = indexes(array(links, "window_id"), ids)
    candidates = np.bincount(link_rows, minlength=len(ids))
    original = pq.read_table(source, columns=["window_id", "parent_sha256", "window_start", "sequence",
                                             "contains_epitope"])
    original = original.filter(pc.is_in(array(original, "window_id"), value_set=ids))
    require(len(original) == len(ids), f"Selection membership changed: {family}")
    rows = indexes(ids, array(original, "window_id"))
    require(pc.all(pc.equal(pc.take(array(original, "sequence"), rows),
                            pc.take(array(base, "sequence"), base_rows))).as_py(), f"Primary provenance changed: {family}")
    require(np.array_equal(array(original, "contains_epitope").to_numpy()[rows],
                           array(base, "label_original").to_numpy()[base_rows]), f"Label provenance changed: {family}")
    proteins_by_window = indexes(array(original, "parent_sha256"), proteins)[rows]
    require(np.array_equal(proteins_by_window, indexes(array(base, "parent_sha256"), proteins)[base_rows]),
            f"Protein provenance changed: {family}")
    metrics = {
        "source_file": source_file, "scoped_groups": len(links),
        "single_candidate_windows": int(np.count_nonzero(candidates == 1)),
        "multiple_candidate_windows": int(np.count_nonzero(candidates > 1)),
        "unmatched_windows": int(np.count_nonzero(candidates == 0)),
        "candidate_links_to_ambiguous_windows": int(candidates[candidates > 1].sum()),
        "historical_groups_by_split": dict(zip(NAMES, np.bincount(base_splits[base_rows[link_rows]],
                                                                  minlength=3).tolist())),
        "original_rows_by_split": dict(zip(NAMES, np.bincount(base_splits[base_rows], minlength=3).tolist())),
    }
    windows = (proteins_by_window, array(original, "window_start").to_numpy()[rows].astype(np.int32),
               base_splits[base_rows])
    return metrics, windows


def overlaps(windows):
    protein, start, split = (np.concatenate(parts) for parts in zip(*windows))
    order = np.lexsort((start, protein))
    protein, start, split = protein[order], start[order], split[order]
    edges = np.r_[0, np.flatnonzero(protein[1:] != protein[:-1]) + 1, len(protein)]
    shared = 0
    touched = np.zeros(3, dtype=np.int64)
    different_start = np.zeros(3, dtype=np.int64)
    pair_counts = np.zeros((3, 3), dtype=np.int64)
    for left, right in zip(edges[:-1], edges[1:]):
        positions = start[left:right]
        partitions = split[left:right]
        if partitions.min() == partitions.max():
            continue
        shared += 1
        starts = [positions[partitions == i] for i in range(3)]
        for i, selected in enumerate(starts):
            hits = np.zeros(len(selected), dtype=bool)
            nearby = np.zeros(len(selected), dtype=bool)
            for j, reference in enumerate(starts):
                if i == j:
                    continue
                count = np.searchsorted(reference, selected + 24, side="right") - np.searchsorted(reference, selected - 24)
                same = np.searchsorted(reference, selected, side="right") - np.searchsorted(reference, selected)
                hits |= count > 0
                nearby |= count > same
                pair_counts[i, j] += count.sum()
            touched[i] += hits.sum()
            different_start[i] += nearby.sum()
    return {
        "unique_protein_sequence_hashes": len(edges) - 1,
        "protein_hashes_in_multiple_splits": shared,
        "windows_overlapping_another_split": dict(zip(NAMES, touched.tolist())),
        "windows_overlapping_another_split_at_different_start": dict(zip(NAMES, different_start.tolist())),
        "overlapping_window_pairs": {f"{NAMES[i]}–{NAMES[j]}": int(pair_counts[i, j])
                                     for i in range(3) for j in range(i + 1, 3)},
    }


def build(output, seed):
    started = perf_counter()
    signatures = {name: sha(ROOT / f"{name}.parquet") for name in FILES}
    selection = load_manifest(SELECTION)
    labels = pq.read_table(ROOT / "global_labels.parquet")
    sequences = array(labels, "sequence")
    require(len(sequences) == pc.count_distinct(sequences).as_py() == 14_530_324, "Primary inventory changed")
    splits = assign(sequences, seed)
    labels_global = array(labels, "label_global").to_numpy()
    counts_global = array(labels, "representations").to_numpy()
    counts_base = array(labels, "base_observations").to_numpy()
    predictions = distribution(splits, labels_global, counts_global)
    representations = pq.read_table(ROOT / "global_dataset.parquet",
                                    columns=["sequence", "secondary_structure", "label_global"])
    rep_idx = indexes(array(representations, "sequence"), sequences)
    require(np.array_equal(np.bincount(rep_idx, minlength=len(sequences)), counts_global) and
            np.array_equal(array(representations, "label_global").to_numpy(), labels_global[rep_idx]),
            "Global view disagrees with the primary catalog")
    rep_pairs = pc.binary_join_element_wise(array(representations, "sequence"),
                                           array(representations, "secondary_structure"), "")
    require(pc.count_distinct(rep_pairs).as_py() == len(representations), "Repeated global representation")
    del representations, rep_idx, rep_pairs

    protein_tables = [pq.read_table(f, columns=["parent_sha256"]) for f in
                      (SELECTION.parent / "../nap_cnb_v2_phase1/proteins").glob("*.parquet")]
    proteins = pc.unique(pa.concat_tables(protein_tables)["parent_sha256"])
    minimum = np.full(len(sequences), len(proteins), dtype=np.int32)
    maximum = np.full(len(sequences), -1, dtype=np.int32)
    seen_base = np.zeros(len(sequences), dtype=np.int64)
    families, history, windows = {}, {}, []
    dimension = {"species": {}, "mhc_class": {}}
    for family, relative in selection["base_families"].items():
        base = pq.read_table(ROOT / "base_dataset.parquet", filters=[("family", "=", family)],
                             columns=["base_id", "parent_sha256", "sequence", "label_original", "organism",
                                      "mhc_class", "observation_count"])
        indices = indexes(array(base, "sequence"), sequences)
        codes = splits[indices]
        rows = distribution(codes, array(base, "label_original").to_numpy())
        families[family] = rows
        for key, column in (("species", "organism"), ("mhc_class", "mhc_class")):
            (value,) = pc.unique(base[column]).to_pylist()
            dimension[key].setdefault(value, []).append(rows)
        selected_proteins = indexes(array(base, "parent_sha256"), proteins)
        np.minimum.at(minimum, indices, selected_proteins)
        np.maximum.at(maximum, indices, selected_proteins)
        seen_base += np.bincount(indices, minlength=len(sequences))
        report, coordinates = historical_and_original(family, SELECTION.parent / relative, base, codes, proteins)
        history[family] = report
        windows.append(coordinates)
        print(f"{family}: {sum(item['rows'] for item in rows.values()):,} base rows and historical links verified", flush=True)
    require(np.array_equal(seen_base, counts_base), "Missing base observations")
    require(len({item["source_file"] for item in history.values()}) == len(history), "Historical scope spans families")
    require(sum(sum(item["original_rows_by_split"].values()) for item in history.values()) == 49_123_503,
            "Missing original windows")
    original = add_distributions(list(families.values()))
    require(sum(x["rows"] for x in original.values()) == 49_022_360 and
            sum(x["positive"] for x in original.values()) == 5_587_073 and
            sum(x["rows"] for x in predictions.values()) == 15_100_592 and
            sum(x["positive"] for x in predictions.values()) == 3_844_628, "Label totals changed")

    protein_diagnostics = overlaps(windows)
    protein_diagnostics["primaries_shared_between_protein_hashes"] = int(np.count_nonzero(minimum != maximum))
    require(signatures == {name: sha(ROOT / f"{name}.parquet") for name in FILES} and
            load_manifest(SELECTION) == selection, "Inputs changed mid-run")

    with TemporaryDirectory(dir=output.parent, prefix=".splits_") as temporary:
        stage = Path(temporary) / output.name
        stage.mkdir()
        path = stage / "assignments.parquet"
        # Sort by exact primary to make physical output invariant to input row order.
        ordering = pc.sort_indices(sequences)
        sorted_keys = pc.take(sequences, ordering)
        sorted_codes = pc.take(pa.array(splits), ordering)
        pq.write_table(pa.table({"effective_group_id": sorted_keys, "split_id": sorted_codes}), path,
                       compression="zstd", row_group_size=250_000)
        reopened = pq.read_table(path)
        reopened_keys = array(reopened, "effective_group_id")
        reopened_codes = array(reopened, "split_id").to_numpy()
        require(reopened_keys.equals(sorted_keys) and np.array_equal(reopened_codes, sorted_codes.to_numpy()) and
                np.array_equal(assign(reopened_keys, seed), reopened_codes), "Reopened assignment is not reproducible")
        report = {
            "version": VERSION, "seed": seed, "targets": [0.8, 0.1, 0.1], "split_ids": dict(enumerate(NAMES)),
            "generated_at": datetime.now(ZoneInfo("Europe/Madrid")).isoformat(),
            "selection_sha256": sha(SELECTION), "catalog_sha256": signatures,
            "assignment_sha256": sha(path), "assignment_bytes": path.stat().st_size,
            "effective_groups": len(sequences),
            "effective_groups_by_split": dict(zip(NAMES, np.bincount(splits, minlength=3).tolist())),
            "base": original, "global": predictions, "families": families,
            "species": {key: add_distributions(groups) for key, groups in dimension["species"].items()},
            "mhc_class": {key: add_distributions(groups) for key, groups in dimension["mhc_class"].items()},
            "original_windows_by_split": {name: sum(row["original_rows_by_split"][name] for row in history.values())
                                          for name in NAMES},
            "historical": history, "protein_diagnostics": protein_diagnostics,
            "verified_cross_primary_historical_edges": 0,
            "elapsed_seconds": perf_counter() - started,
        }
        report["largest_effective_group"] = {
            column: pc.max(labels[column]).as_py()
            for column in ("base_observations", "representations", "original_observations")
        }
        for dimension in ("base", "global"):
            total = sum(entry["rows"] for entry in report[dimension].values())
            for name, target in zip(NAMES, report["targets"], strict=True):
                entry = report[dimension][name]
                entry["row_share"] = entry["rows"] / total
                entry["target_deviation_percentage_points"] = 100 * (entry["row_share"] - target)
        (stage / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
        stage.rename(output)
    print(f"Published {output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=ROOT / "splits")
    args = parser.parse_args()
    require(0 <= args.seed < 2**64, "Seed must be unsigned 64 bit")
    require(not args.output.exists(), f"Output already exists: {args.output}")
    pa.set_cpu_count(8)
    build(args.output, args.seed)


if __name__ == "__main__":
    main()
