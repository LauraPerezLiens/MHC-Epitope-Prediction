"""Check event/assay links and resolve which quarantined groups retain a clean record."""

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import json
from pathlib import Path
import re

from data_pipeline.scripts.global_epitope_labels.build import write_json


def run(output, prior):
    # The initial replay nominates groups with at least one doubtful record.
    provisional = output / "quarantined_events.csv.gz"
    original = output / "removed_events.csv.gz"
    if not provisional.exists():
        original.replace(provisional)
    with gzip.open(provisional, "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        quarantine = {(r["family"], r["old_event_id"]): r for r in reader}
    supported = set()
    edges = defaultdict(set)
    first = {}
    multi = defaultdict(set)
    old_refs = defaultdict(set)
    new_refs = defaultdict(set)
    stats = defaultdict(Counter)
    archive_offsets = Counter()
    previous_index = {}
    with gzip.open(output / "event_assay_provenance.csv.gz", "rt", newline="") as handle:
        for r in csv.DictReader(handle):
            family, mode, old_id = r["family"], r["kind"], r["old_event_id"]
            key = family, old_id
            index = int(r["record_index"])
            source_file = r["source_file"]
            if index != previous_index.get(source_file, -1) + 1:
                raise ValueError(f"Missing row in saved archive traversal: {source_file}:{index}")
            previous_index[source_file] = index
            archive_offsets[source_file] += 1
            for col in ("source_iri", "parent_iri"):
                if r[col].strip():
                    new_refs[family, col].add(r[col])
                    if old_id:
                        old_refs[family, col].add(r[col].strip())
            reasons = set(r["reasons"].split("|"))
            if (key in quarantine and r["corrected_sequence"] and not r["modification"]
                    and not {"invalid_coordinates", "coordinate_length_mismatch", "missing_reference"} & reasons):
                supported.add(key)
            assay = r["assay_iri"]
            if assay and not re.search(r"/assay/\d+$", assay):
                stats[family]["non_instance_assay_iri"] += 1
            if old_id and re.search(r"/assay/\d+$", assay):
                link = old_id, assay
                if link in edges[family]:
                    stats[family]["repeated_projected_event_assay_link"] += 1
                edges[family].add(link)
                prev = first.setdefault(key, assay)
                if prev != assay:
                    multi[family].add(old_id)
    with gzip.open(original, "wt", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=header)
        w.writeheader()
        for key, example in quarantine.items():
            if key in supported:
                stats[key[0]]["reviewed_legacy_events_with_another_clean_record"] += 1
            else:
                stats[key[0]]["legacy_events_removed_from_plain_pool"] += 1
                w.writerow(dict(example, classification="pending_no_clean_record"))
    for family in stats.keys() | edges.keys():
        stats[family]["distinct_legacy_event_assay_links_reconstructable"] = len(edges[family])
        stats[family]["legacy_events_with_multiple_assays"] = len(multi[family])
        for col in ("source_iri", "parent_iri"):
            stats[family][f"new_{col}"] = len(new_refs[family, col] - old_refs[family, col])
    # The previous API cache is a convenience sample, not a historical ground truth.
    cache = json.loads(prior.read_text()) if prior.is_file() else {}
    corroboration = Counter()
    examples = []
    with gzip.open(output / "modified_events.csv.gz", "rt", newline="") as handle:
        for r in csv.DictReader(handle):
            m = re.search(r"/epitope/(\d+)$", r["epitope_iri"])
            if not m or m[1] not in cache or r["corrected_sequence"]:
                continue
            canonical = cache[m[1]].get("linear_sequence")
            if not canonical:
                continue
            corroboration["modified_unparsed_pairs_checked_against_cached_iedb"] += 1
            if r["original_sequence"] != canonical:
                corroboration["legacy_different_from_cached_iedb"] += 1
                if len(examples) < 6:
                    examples.append(dict(r, cached_iedb_linear_sequence=canonical))
            else:
                corroboration["legacy_equal_to_cached_iedb"] += 1
    write_json(output / "provenance_checks.json", {
        "families": {family: dict(c) for family, c in sorted(stats.items())},
        "archive_rows": dict(archive_offsets),
        "external_corroboration": dict(corroboration),
        "examples": examples,
    })


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--prior", type=Path, default=Path("results/epitope_counterfactual_20261118/iedb_records.json"))
    args = p.parse_args()
    run(args.output, args.prior)


if __name__ == "__main__":
    main()
