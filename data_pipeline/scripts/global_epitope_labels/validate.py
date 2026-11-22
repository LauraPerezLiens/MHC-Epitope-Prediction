#!/usr/bin/env python3
"""Audit a global-label export and regenerate its statistical reports."""

import argparse
from contextlib import ExitStack, closing
import csv
from itertools import zip_longest
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time

import pyarrow.parquet as pq

if not __package__:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from data_pipeline.scripts.global_epitope_labels.build import (
    FAMILY_NAMES, ROOT, SOURCES, add_counts, annotation, check_inputs, count_batches,
    frames, open_index, output_lock, row_path, row_schema, row_table, unique_table,
    UNIQUE_SCHEMA, write_json,
)


def audit_rows(output, config, index, audit):
    expected_files = {row_path(output, source) for source in config["sources"]}
    if set((output / "rows").glob("*.parquet")) != expected_files:
        raise ValueError("The family Parquet files do not match the source manifest.")
    families = []
    for i, source in enumerate(config["sources"]):
        started = time.monotonic()
        path = row_path(output, source)
        parquet = pq.ParquetFile(path)
        if parquet.schema_arrow != row_schema(config):
            raise ValueError(f"Wrong row-level schema: {path}")
        rows = original_positive = global_positive = 0
        for group, frame in enumerate(frames(config, source)):
            expected = row_table(frame, source, rows, config, index)
            if group >= parquet.num_row_groups:
                raise ValueError(f"Missing row group {group} in {path}")
            actual = parquet.read_row_group(group)
            if not actual.equals(expected):
                raise ValueError(f"Source values, provenance or global evidence differ in {path}, group {group}.")
            labels = frame["contains_epitope"]
            with audit:
                add_counts(audit, frame[config["sequence_column"]], labels, i)
            positives = int(labels.eq("1").sum())
            if any(label == "1" and value != 1
                   for label, value in zip(labels, actual["global_contains_epitope"].to_pylist())):
                raise ValueError(f"An original positive annotation was lost in {path}, group {group}.")
            original_positive += positives
            global_positive += sum(actual["global_contains_epitope"].to_pylist())
            rows += len(frame)
            print(f"VALIDATE {source['mhc_family']} {rows:,} rows ({time.monotonic()-started:.1f}s)", flush=True)
        if not rows or group + 1 != parquet.num_row_groups or rows != parquet.metadata.num_rows:
            raise ValueError(f"Row totals or row groups differ from the source for {path}.")
        converted = global_positive - original_positive
        negative = rows - original_positive
        families.append({
            "organism": source["organism"], "mhc_class": source["mhc_class"],
            "mhc_family": source["mhc_family"], "total_rows": rows,
            "original_positive": original_positive, "original_negative": negative,
            "global_positive": global_positive, "global_unlabeled": rows - global_positive,
            "converted_rows": converted, "percent_original_negatives_converted": percent(converted, negative),
        })
    return families


def audit_unique(output, config, index, audit):
    parquet = pq.ParquetFile(output / "sequences.parquet")
    if parquet.schema_arrow != UNIQUE_SCHEMA:
        raise ValueError("Wrong unique-sequence schema.")
    distribution = [0] * (len(FAMILY_NAMES) + 1)
    entries = mixed = mixed_rows = original_positive = original_negative = global_positive_rows = 0
    for group, (indexed, recomputed) in enumerate(zip_longest(
        count_batches(index, config["batch_rows"]), count_batches(audit, config["batch_rows"]),
    )):
        if indexed != recomputed:
            raise ValueError(f"Sequence counts or positive family evidence differ in unique group {group}.")
        if group >= parquet.num_row_groups or not parquet.read_row_group(group).equals(unique_table(recomputed)):
            raise ValueError(f"Unique-sequence Parquet differs from source evidence in group {group}.")
        for _, negative, positive, mask in recomputed:
            label, _, family_count, _, _ = annotation(positive, mask)
            distribution[family_count] += 1
            original_positive += positive
            original_negative += negative
            global_positive_rows += (negative + positive) * label
            if negative and positive:
                mixed += 1
                mixed_rows += negative + positive
        entries += len(recomputed)
        if group == 0 or (group + 1) % 10 == 0:
            print(f"VALIDATE unique {entries:,} sequences", flush=True)
    if not entries or group + 1 != parquet.num_row_groups or entries != parquet.metadata.num_rows:
        raise ValueError("Unique-sequence output row count differs from the source.")
    return {
        "original_rows": original_positive + original_negative,
        "original_positive_rows": original_positive, "original_negative_rows": original_negative,
        "unique_sequences": entries, "global_positive_sequences": entries - distribution[0],
        "global_unlabeled_sequences": distribution[0], "global_positive_rows": global_positive_rows,
        "global_unlabeled_rows": original_positive + original_negative - global_positive_rows,
        "rows_changed": global_positive_rows - original_positive,
        "percent_rows_changed": percent(global_positive_rows - original_positive, original_positive + original_negative),
        "mixed_label_sequences": mixed, "mixed_label_rows": mixed_rows,
        "positive_family_count_distribution": dict(enumerate(distribution)),
        "cross_family_evidence": {
            "exactly_1": distribution[1], "exactly_2": distribution[2],
            "exactly_3": distribution[3], "more_than_3": sum(distribution[4:]),
        },
    }


def percent(numerator, denominator):
    return 100 * numerator / denominator if denominator else None


def historical_comparison(config, totals):
    baseline = ROOT / "results/data_contradictions/summary.json"
    if (config["rows_per_family"] is not None or Path(config["sources_root"]) != SOURCES.resolve()
            or not baseline.is_file()):
        return None
    previous = json.loads(baseline.read_text(encoding="utf-8"))
    keys = {"original_rows": "original_rows", "unique_sequences": "unique_sequences",
            "mixed_label_sequences": "contradictory_sequences", "mixed_label_rows": "contradictory_rows"}
    return {key: {"previous": previous[old], "current": totals[key],
                  "matches": previous[old] == totals[key]} for key, old in keys.items()}


def write_csv(path, rows):
    partial = path.with_suffix(".partial")
    with partial.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    partial.replace(path)


def write_reports(output, summary):
    write_csv(output / "families.csv", summary["families"])
    write_csv(output / "family_count_distribution.csv", [
        {"positive_family_count": count, "unique_sequences": rows}
        for count, rows in summary["positive_family_count_distribution"].items()
    ])
    scope = ("Complete input" if summary["rows_per_family"] is None else
             f"First {summary['rows_per_family']:,} rows per family; counts describe only the sample.")
    markdown = [
        "# Global epitope labels", "", scope, "",
        "A positive label requires at least one positive source annotation for the exact original sequence.",
        "Label zero means unlabeled in the input scope. A positive annotation does not establish binding "
        "across families, immunogenicity across organisms, or equivalent biological context.",
        "Evidence counts are source rows and may include repeated observations.", "",
        "## Original data", "",
        f"- Rows: {summary['original_rows']:,}",
        f"- Distinct original sequences: {summary['unique_sequences']:,}",
        f"- Rows labeled positive in their source family: {summary['original_positive_rows']:,}",
        f"- Rows labeled negative in their source family: {summary['original_negative_rows']:,}",
        f"- Exact sequences with both original labels: {summary['mixed_label_sequences']:,} "
        f"({summary['mixed_label_rows']:,} source rows)", "",
        "## Global labels", "",
        f"- Positive distinct sequences: {summary['global_positive_sequences']:,}",
        f"- Unlabeled distinct sequences: {summary['global_unlabeled_sequences']:,}",
        f"- Globally positive rows: {summary['global_positive_rows']:,}",
        f"- Globally unlabeled rows: {summary['global_unlabeled_rows']:,}",
        f"- Rows with a changed label: {summary['rows_changed']:,} ({summary['percent_rows_changed']:.2f}%)",
        "", "## By family", "",
        "| Family | Rows | Original + | Original − | Global + | Unlabeled | Converted | % of original − |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for family in summary["families"]:
        rate = family["percent_original_negatives_converted"]
        formatted_rate = "—" if rate is None else f"{rate:.2f}%"
        fields = ("total_rows", "original_positive", "original_negative", "global_positive",
                  "global_unlabeled", "converted_rows")
        numeric = " | ".join(f"{family[key]:,}" for key in fields)
        markdown.append(f"| {family['organism']}/{family['mhc_class']}/{family['mhc_family']} | "
                        f"{numeric} | {formatted_rate} |")
    evidence = summary["cross_family_evidence"]
    markdown.extend([
        "", "## Cross-family positive evidence", "",
        f"- Exactly 1 family: {evidence['exactly_1']:,}",
        f"- Exactly 2 families: {evidence['exactly_2']:,}",
        f"- Exactly 3 families: {evidence['exactly_3']:,}",
        f"- More than 3 families: {evidence['more_than_3']:,}", "",
        "| Positive families | Distinct sequences |", "|---:|---:|",
    ])
    markdown.extend(f"| {families} | {count:,} |"
                    for families, count in summary["positive_family_count_distribution"].items())
    if summary["historical_comparison"]:
        markdown.extend(["", "## Comparison with the previous full analysis", ""])
        for name, values in summary["historical_comparison"].items():
            markdown.append(f"- `{name}`: {values['current']:,} now, {values['previous']:,} previously.")
    markdown.extend(["", "## Validation", "",
                     "The audit checked family labels, original values, source and row identifiers, "
                     "global evidence, and sequence totals against the original input scope. "
                     "No embeddings, variants, scalers, or splits were generated or changed.", ""])
    partial = output / "report.md.partial"
    partial.write_text("\n".join(markdown), encoding="utf-8")
    partial.replace(output / "report.md")
    write_json(output / "summary.json", summary)


def validate_locked(output, config, *, ram_index=False):
    started = time.monotonic()
    check_inputs(config)
    with ExitStack() as cleanup:
        uri = (output / "index.sqlite").as_uri() + "?mode=ro"
        persisted = cleanup.enter_context(closing(sqlite3.connect(uri, uri=True)))
        if ram_index:
            index = cleanup.enter_context(closing(open_index(":memory:")))
            persisted.backup(index)
            audit_path = ":memory:"
        else:
            index = persisted
            scratch = cleanup.enter_context(TemporaryDirectory(prefix="global-label-audit-", dir=output))
            audit_path = Path(scratch) / "audit.sqlite"
        index.execute("PRAGMA temp_store=MEMORY")
        audit = cleanup.enter_context(closing(open_index(audit_path)))
        families = audit_rows(output, config, index, audit)
        totals = audit_unique(output, config, index, audit)
    for family_key, total_key in (
        ("total_rows", "original_rows"), ("original_positive", "original_positive_rows"),
        ("original_negative", "original_negative_rows"), ("global_positive", "global_positive_rows"),
        ("global_unlabeled", "global_unlabeled_rows"), ("converted_rows", "rows_changed"),
    ):
        if sum(row[family_key] for row in families) != totals[total_key]:
            raise ValueError(f"Family and unique-sequence totals disagree: {total_key}")
    check_inputs(config)
    totals.update({
        "status": "validated", "rows_per_family": config["rows_per_family"],
        "families": families, "historical_comparison": historical_comparison(config, totals),
        "validation_seconds": round(time.monotonic() - started, 2),
    })
    write_reports(output, totals)
    print(f"VALIDATED {totals['original_rows']:,} rows, {totals['unique_sequences']:,} sequences "
          f"({totals['validation_seconds']:.1f}s)", flush=True)
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ram-index", action="store_true", help="Use RAM for the audit indexes.")
    args = parser.parse_args()
    output = args.output.resolve(strict=True)
    config_file = output / "config.json"
    if not config_file.is_file():
        raise ValueError(f"Global-label config not found: {config_file}")
    with output_lock(output):
        validate_locked(output, json.loads(config_file.read_text(encoding="utf-8")), ram_index=args.ram_index)


if __name__ == "__main__":
    main()
