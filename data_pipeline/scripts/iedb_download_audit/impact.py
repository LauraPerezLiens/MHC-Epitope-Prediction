"""Estimate window sensitivity to the normalization policy, without remapping source loci."""

import argparse
from collections import Counter, defaultdict
import csv
import gzip
from pathlib import Path

from data_pipeline.scripts.global_epitope_labels.build import FAMILIES, write_json
from data_pipeline.scripts.iedb_download_audit.audit import event_id, windows


def run(output, inputs):
    removed = defaultdict(set)
    with gzip.open(output / "removed_events.csv.gz", "rt", newline="") as f:
        for row in csv.DictReader(f):
            removed[row["family"]].add(row["old_event_id"])
    fasta = {}
    for org in ("human", "mouse"):
        with (inputs / "data_intermediate" / f"{org}_parent_protein_fasta.csv").open(newline="") as f:
            for row in csv.DictReader(f):
                if row["id_full"] == row["resolved_id"]:
                    key = org, row["protein_url"].replace("https://", "http://")
                    sequence = "".join(row["fasta"].splitlines()[1:])
                    if key in fasta and fasta[key] != sequence:
                        fasta[key] = ""
                    else:
                        fasta[key] = sequence
    result = {}
    old_parents = defaultdict(set)
    for org, mhc, family in FAMILIES:
        drop, keep = defaultdict(set), defaultdict(set)
        before, after = set(), set()
        counts = Counter()
        path = inputs / "data_raw" / org / mhc / family / "merged_unique_events.csv"
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                url = row["parent_id"]
                if url:
                    old_parents[family].add(url)
                protein = fasta.get((org, url.replace("https://", "http://")))
                if not protein or len(protein) < 25:
                    continue
                pep = row["epitope__name_canonical"]
                try:
                    a, b = (int(row[k]) for k in ("epitope__starting_position", "epitope__ending_position"))
                except ValueError:
                    continue
                if not (1 <= a <= b <= len(protein) and protein[a-1:b] == pep):
                    continue
                eid = event_id((pep, row["epitope__starting_position"], row["epitope__ending_position"],
                                row["source_id"], url))
                before.add(url)
                if eid in removed[family]:
                    counts["removed_groups_accepted_by_legacy_local_fasta_check"] += 1
                    drop[url].update(windows(a, len(pep), len(protein)))
                else:
                    after.add(url)
                    keep[url].update(windows(a, len(pep), len(protein)))
        counts["affected_legacy_positive_positions"] = sum(len(v) for v in drop.values())
        counts["positions_with_other_legacy_event"] = sum(len(v & keep[u]) for u, v in drop.items())
        counts["positions_without_other_legacy_event"] = sum(len(v - keep[u]) for u, v in drop.items())
        counts["parents_losing_last_legacy_event"] = len(before - after)
        result[family] = dict(counts)
    new_refs = defaultdict(set)
    missing_refs = Counter()
    orgs = {family: org for org, _, family in FAMILIES}
    with gzip.open(output / "added_events.csv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f):
            fam, url = r["family"], r["parent_iri"]
            if r["corrected_sequence"] and not r["modification"] and url and r["source_iri"]:
                missing_refs["added_plain_event_with_both_references"] += 1
                if fasta.get((orgs[fam], url.replace("https://", "http://"))):
                    missing_refs["added_plain_event_with_both_references_and_parent_fasta"] += 1
            if url and url not in old_parents[fam]:
                new_refs[fam].add(url)
    missing_refs["new_parent_iris_with_archived_fasta"] = sum(
        bool(fasta.get((orgs[f], u.replace("https://", "http://"))))
        for f, urls in new_refs.items() for u in urls
    )
    write_json(output / "window_sensitivity.json", {
        "families": result, "totals": dict(sum(map(Counter, result.values()), Counter())),
        "missing_coordinate_nominations": dict(missing_refs),
    })


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--inputs", type=Path, default=Path("results/source_audits_inputs_20261118"))
    args = p.parse_args()
    run(args.output, args.inputs)


if __name__ == "__main__":
    main()
