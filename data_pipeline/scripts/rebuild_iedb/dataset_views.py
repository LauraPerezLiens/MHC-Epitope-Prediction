"""Build the reversible NAP-CNB v2 metadata views from the signed final selection."""
import argparse
from contextlib import ExitStack, closing
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

PROTEIN = ["parent_url", "parent_accession", "parent_version", "parent_sha256"]
PAIR = ["sequence", "secondary_structure"]
LABEL = "label_original"
BASE = ["family", *PROTEIN, *PAIR, LABEL]
MATCH = ["parent_url", "window_start", "sequence"]
HISTORICAL = Path("data/global_epitope_labels/rows")
PROTT5 = Path("results/nap_cnb_v2_embedding_audit/missing_prott5_sequences.parquet")
SECONDARY = Path("results/nap_cnb_v2_secondarybert/index.sqlite")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonnull(table, fields):
    return all(table[name].null_count == 0 for name in fields)


def total(values):
    return pc.sum(values).as_py() or 0


def cardinality(values):
    return pc.count_distinct(values).as_py()


def load_manifest(path):
    manifest = json.loads(path.read_text())
    for item in manifest["input_signatures"]:
        stat = (path.parent / item["path"]).stat()
        require((stat.st_size, stat.st_mtime_ns) == (item["bytes"], item["mtime_ns"]), item["path"])
    for name, expected in manifest["supplement_sha256"].items():
        require(digest(path.parent / name) == expected, name)
    return manifest


def write_table(stack, writers, directory, name, table):
    if name not in writers:
        writers[name] = stack.enter_context(pq.ParquetWriter(directory / f"{name}.parquet", table.schema,
                                                           compression="zstd"))
    writers[name].write_table(table, row_group_size=250_000)


def legacy_groups(family):
    (path,) = HISTORICAL.glob(f"*_{family}.parquet")
    old = pq.read_table(path, columns=["protein_url", "window_start", "25aa_seq", "source_file",
                                      "source_row_index", "group_id", "contains_epitope"])
    old = old.rename_columns(["parent_url", "window_start", "sequence", "legacy_source_file",
                              "legacy_row_index", "group_id", "legacy_label"])
    url = pc.utf8_trim_whitespace(old["parent_url"])
    url = pc.replace_substring_regex(url, r"^https?://", "")
    old = old.set_column(0, "parent_url", pc.replace_substring_regex(url, r"/+$", ""))
    valid = pc.match_substring_regex(old["window_start"], r"^[0-9]+$")
    old = old.filter(valid)
    old = old.set_column(1, "window_start", pc.cast(old["window_start"], pa.int64()))
    require(nonnull(old, ["group_id", "legacy_source_file", "legacy_row_index"]), f"Legacy ID incomplete: {family}")
    groups = old.select(["legacy_source_file", "group_id"]).group_by(["legacy_source_file", "group_id"]).aggregate([])
    require(len(groups) == len(old), f"Repeated scoped legacy group: {family}")
    return old


def process_family(path, family, overlay, excluded):
    fields = ["window_id", "family", "organism", "mhc_class", *PROTEIN, "window_start",
              "sequence", "contains_epitope", "secondary_structure"]
    rows = pq.read_table(path, columns=fields)
    rows = rows.filter(pc.invert(pc.is_in(rows["window_id"], value_set=excluded)))
    rows = rows.join(overlay, keys="window_id", join_type="left outer")
    rows = rows.set_column(rows.schema.get_field_index("secondary_structure"), "secondary_structure",
                           pc.coalesce(rows["secondary_structure"], rows["recovered_ss"])).drop(["recovered_ss"])
    rows = rows.rename_columns([LABEL if name == "contains_epitope" else name for name in rows.column_names])
    require(nonnull(rows, BASE + ["window_id", "window_start"]), f"Null canonical key: {family}")
    require(total(pc.not_equal(rows["family"], family)) == 0, f"Mixed family: {family}")
    require(total(pc.invert(pc.is_in(rows[LABEL], value_set=pa.array([0, 1], type=pa.int8())))) == 0,
            f"Nonbinary label: {family}")
    require(cardinality(rows["window_id"]) == len(rows), f"Repeated original window_id: {family}")
    base = rows.group_by(BASE + ["organism", "mhc_class"]).aggregate(
        [("window_id", "min"), ("window_id", "count")])
    base = base.rename_columns([*BASE, "organism", "mhc_class", "base_id", "observation_count"])
    require(total(base["observation_count"]) == len(rows), f"Lost rows: {family}")
    # Species and MHC class are constant in each family. Verify they did not affect deduplication.
    require(all(cardinality(rows[field]) == 1 for field in ("organism", "mhc_class")),
            f"Family metadata varied: {family}")
    mapping = rows.select(["window_id", "window_start", *BASE]).join(
        base.select([*BASE, "base_id"]), keys=BASE, join_type="inner")
    require(len(mapping) == len(rows) and cardinality(mapping["window_id"]) == len(rows),
            f"Invalid base provenance: {family}")
    old = legacy_groups(family)
    legacy_ids = pc.unique(old["group_id"])
    linked = mapping.select(["window_id", LABEL, *MATCH]).join(old, keys=MATCH, join_type="inner")
    links = linked.select(["window_id", "legacy_source_file", "group_id", "legacy_row_index", "legacy_label"])
    link_counts = links.select(["window_id", "group_id"]).group_by("window_id").aggregate([("group_id", "count")])
    scoped_groups = links.select(["legacy_source_file", "group_id"]).group_by(
        ["legacy_source_file", "group_id"]).aggregate([])
    stats = {
        "original": len(rows), "base": len(base), "removed": len(rows) - len(base),
        "original_positive": total(rows[LABEL]), "base_positive": total(base[LABEL]),
        "legacy_groups": len(old), "matched_legacy_groups": len(scoped_groups),
        "windows_with_legacy_candidate": len(link_counts),
        "ambiguous_legacy_windows": total(pc.greater(link_counts["group_id_count"], 1)),
        "legacy_links": len(links),
        "legacy_label_differences": total(pc.not_equal(linked[LABEL], linked["legacy_label"])),
        "windows_related_by_base": total(pc.filter(base["observation_count"], pc.greater(base["observation_count"], 1))),
    }
    return base, mapping.select(["window_id", "base_id"]), links, stats, legacy_ids


def validate_catalogs(labels, representations):
    import sqlite3

    original = pq.read_table(PROTT5, columns=["sequence"])["sequence"].combine_chunks()
    require(len(original) == len(labels) and total(pc.invert(pc.is_in(labels["sequence"], value_set=original))) == 0,
            "ProtT5 inventory and view do not match")
    with closing(sqlite3.connect(f"file:{SECONDARY.resolve()}?mode=ro", uri=True)) as db:
        secondary = pa.array([row[0] for row in db.execute("""
            SELECT structure FROM inventory WHERE shard IS NOT NULL
            UNION ALL
            SELECT structure FROM embedding
        """)])
    actual = pc.unique(representations["secondary_structure"])
    require(len(secondary) == len(actual) and total(pc.invert(pc.is_in(actual, value_set=secondary))) == 0,
            "SecondaryBERT inventory and view do not match")


def global_tables(base, path):
    # The URL is a conservative identity component. Encode all components for equality checks.
    identity = pc.binary_join_element_wise(*(base[k] for k in PROTEIN), "\x1f")
    compact = base.select([*PAIR, LABEL, "family", "observation_count"]).append_column("protein_identity", identity)
    pair = compact.group_by(PAIR).aggregate([
        (LABEL, "min"), (LABEL, "max"), ("observation_count", "sum"), ("family", "count"),
        ("family", "min"), ("family", "max"),
    ])
    families = compact.select(["sequence", "family", LABEL]).group_by(["sequence", "family"]).aggregate([(LABEL, "max")])
    maxima = families.group_by("sequence").aggregate([("label_original_max", "min"), ("label_original_max", "max")])
    labels = pair.group_by("sequence").aggregate([("label_original_max", "max"), ("label_original_min", "min"),
                                                 ("secondary_structure", "count"), ("family_count", "sum"),
                                                 ("observation_count_sum", "sum")])
    labels = labels.rename_columns(["sequence", "label_global", "min_original_label", "representations",
                                    "base_observations", "original_observations"])
    positions = pc.index_in(maxima["sequence"], value_set=labels["sequence"])
    require(len(maxima) == len(labels) and positions.null_count == 0 and
            pc.all(pc.equal(pc.take(labels["label_global"], positions), maxima["label_original_max_max"])).as_py(),
            "Independent family maxima disagree with global labels")
    label_positions = pc.index_in(pair["sequence"], value_set=labels["sequence"])
    require(label_positions.null_count == 0, "Representation without global label")
    representations = pair.select(PAIR + ["family_count", "observation_count_sum"]).rename_columns(
        [*PAIR, "base_observations", "original_observations"])
    representations = representations.append_column("label_global", pc.take(labels["label_global"], label_positions))
    require(total(labels["base_observations"]) == total(representations["base_observations"]) == len(base),
            "Global provenance does not cover base")
    require(total(labels["original_observations"]) == total(representations["original_observations"]) == 49123503,
            "Global provenance does not cover original observations")
    validate_catalogs(labels, representations)
    pq.write_table(labels, path / "global_labels.parquet", compression="zstd", row_group_size=250_000)
    pq.write_table(representations, path / "global_dataset.parquet", compression="zstd", row_group_size=250_000)
    # Same input and label across distinct proteins or families are retained in the base.
    same_label = compact.group_by([*PAIR, LABEL]).aggregate([
        ("family", "min"), ("family", "max"), ("protein_identity", "min"), ("protein_identity", "max"),
        ("observation_count", "sum"),
    ])
    shared_family = pc.not_equal(same_label["family_min"], same_label["family_max"])
    shared_protein = pc.not_equal(same_label["protein_identity_min"], same_label["protein_identity_max"])
    same_pair = pc.greater(pair["observation_count_sum"], 1)
    shared_primary = pc.greater(labels["original_observations"], 1)
    return {
        "global_sequences": len(labels),
        "global_positive": total(labels["label_global"]),
        "mixed_label_sequences": total(pc.not_equal(labels["label_global"], labels["min_original_label"])),
        "different_family_maximum_sequences": total(pc.not_equal(maxima["label_original_max_min"],
                                                                   maxima["label_original_max_max"])),
        "multiple_secondary_sequences": total(pc.greater(labels["representations"], 1)),
        "global_representations": len(representations),
        "global_positive_representations": total(representations["label_global"]),
        "mixed_label_pairs": total(pc.not_equal(pair["label_original_min"], pair["label_original_max"])),
        "same_label_keys_shared_across_families": total(shared_family),
        "same_label_windows_shared_across_families": total(pc.filter(same_label["observation_count_sum"], shared_family)),
        "same_label_keys_shared_across_proteins": total(shared_protein),
        "same_label_windows_shared_across_proteins": total(pc.filter(same_label["observation_count_sum"], shared_protein)),
        "windows_related_by_exact_pair": total(pc.filter(pair["observation_count_sum"], same_pair)),
        "windows_related_by_exact_primary": total(pc.filter(labels["original_observations"], shared_primary)),
        "maximum_component_windows_by_exact_primary": pc.max(labels["original_observations"]).as_py(),
        "windows_related_by_exact_pair_across_families": total(pc.filter(
            pair["observation_count_sum"], pc.not_equal(pair["family_min"], pair["family_max"]))),
        "base_labels_changed_in_global_view": (total(pc.take(labels["label_global"], pc.index_in(compact["sequence"].combine_chunks(), value_set=labels["sequence"])))
                                               - total(compact[LABEL])),
    }


def group_statistics(output, families):
    """Count scoped historical IDs connected by canonical provenance relations."""
    labels = pq.read_table(output / "global_labels.parquet",
                           columns=["sequence", "original_observations"])
    shared_primaries = pc.filter(labels["sequence"], pc.greater(labels["original_observations"], 1))
    global_pairs = pq.read_table(output / "global_dataset.parquet", columns=[*PAIR, "original_observations"])
    global_pairs = global_pairs.filter(pc.greater(global_pairs["original_observations"], 1))
    shared_pairs = pc.binary_join_element_wise(*(global_pairs[name] for name in PAIR), "")
    statistics = {}
    for family in families:
        # Every canonical window ID starts with its family and a vertical bar.
        bounds = [("window_id", ">=", family + "|"), ("window_id", "<", family + "}")]
        base = pq.read_table(output / "base_dataset.parquet",
                             columns=["base_id", *PAIR, "observation_count"], filters=[("family", "=", family)])
        provenance = pq.read_table(output / "window_provenance.parquet", filters=bounds)
        links = pq.read_table(output / "legacy_group_links.parquet",
                              columns=["window_id", "legacy_source_file", "group_id"], filters=bounds)
        reference = pc.index_in(provenance["base_id"].combine_chunks(), value_set=base["base_id"])
        require(reference.null_count == 0, f"Cannot resolve base provenance: {family}")
        ids = pc.index_in(links["window_id"].combine_chunks(), value_set=provenance["window_id"])
        require(ids.null_count == 0, f"Cannot resolve historical group provenance: {family}")
        base_mask = {
            "legacy_groups_related_by_base": pc.greater(base["observation_count"], 1),
            "legacy_groups_related_by_exact_pair": pc.is_in(
                pc.binary_join_element_wise(*(base[name].combine_chunks() for name in PAIR), ""), value_set=shared_pairs),
            "legacy_groups_related_by_exact_primary": pc.is_in(base["sequence"].combine_chunks(), value_set=shared_primaries),
        }
        statistics[family] = {}
        for name, mask in base_mask.items():
            scoped = links.filter(pc.take(pc.take(mask, reference), ids)).select(["legacy_source_file", "group_id"])
            statistics[family][name] = len(scoped.group_by(scoped.column_names).aggregate([]))
    return statistics


def build(selection, output):
    started = perf_counter()
    manifest = load_manifest(selection)
    overlay = pq.read_table(selection.parent / manifest["structure_overlay"],
                            columns=["window_id", "secondary_structure"]).rename_columns(["window_id", "recovered_ss"])
    excluded = pq.read_table(selection.parent / manifest["exclusions"], columns=["window_id"])["window_id"].combine_chunks()
    output.parent.mkdir(parents=True, exist_ok=True)
    require(not output.exists(), f"Output already exists: {output}")
    with TemporaryDirectory(dir=output.parent, prefix=".dataset_views_") as tmp:
        stage = Path(tmp) / output.name
        stage.mkdir()
        metrics = {"selection_sha256": digest(selection), "families": {}}
        historical_ids = []
        with ExitStack() as stack:
            writers = {}
            for family, relative in manifest["base_families"].items():
                base, provenance, links, stats, ids = process_family(selection.parent / relative, family, overlay, excluded)
                expected = manifest["counts_by_family"][family]
                require((stats["original_positive"], stats["original"] - stats["original_positive"]) ==
                        (expected["positive_final"], expected["negative_final"]), f"Manifest counts changed: {family}")
                historical_ids.append(pa.table({"id": ids}))
                metrics["families"][family] = stats
                write_table(stack, writers, stage, "base_dataset", base)
                write_table(stack, writers, stage, "window_provenance", provenance)
                write_table(stack, writers, stage, "legacy_group_links", links)
                print(f"{family}: {stats}", flush=True)
                del base, provenance, links
        require(sum(s["original"] for s in metrics["families"].values()) == 49123503, "Selection row count changed")
        require(sum(s["original_positive"] for s in metrics["families"].values()) == 5587074, "Selection label count changed")
        ids_by_source = pa.concat_tables(historical_ids).group_by("id").aggregate([("id", "count")])
        metrics["numeric_group_ids_reused_between_files"] = total(pc.greater(ids_by_source["id_count"], 1))
        print("Building global metadata and diagnostics", flush=True)
        base = pq.read_table(stage / "base_dataset.parquet")
        metrics.update(global_tables(base, stage))
        del base
        for family, stats in group_statistics(stage, metrics["families"]).items():
            metrics["families"][family].update(stats)
        require(load_manifest(selection) == manifest, "Selection changed during build")
        metrics["elapsed_seconds"] = perf_counter() - started
        metrics["files_bytes"] = {p.name: p.stat().st_size for p in sorted(stage.iterdir())}
        (stage / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        stage.rename(output)
    print(f"Published {output} in {metrics['elapsed_seconds']:.2f} s", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path,
                        default=Path("results/nap_cnb_v2_final_selection/selection.json"))
    parser.add_argument("--output", type=Path, default=Path("results/nap_cnb_v2_dataset_views"))
    args = parser.parse_args()
    pa.set_cpu_count(8)
    build(args.selection, args.output)


if __name__ == "__main__":
    main()
