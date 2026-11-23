"""Compare legacy and experimental IEDB processing on the archived download."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from functools import lru_cache
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
from tempfile import TemporaryDirectory

from data_pipeline.scripts.data_download.build_iedb_dataset import canonical_epitope, get_value
from data_pipeline.scripts.global_epitope_labels.build import FAMILIES, ROOT, write_json

ALLOWED = {"positive", "positive-low", "positive-intermediate", "positive-medium", "positive-high"}
AMINO = re.compile(r"[ACDEFGHIKLMNPQRSTVWY]+")
SPECIES = {"human": "homo sapiens", "mouse": "mus musculus"}
TAXON = {"human": "9606", "mouse": "10090"}
BASE = ROOT / "data/used_data/data_raw.tar.zst"
FASTA = ROOT / "results/source_audits_inputs_20261118/data_intermediate"
MEMBERS = {f"data_raw/{org}/{mhc}/{family}/{kind}_export_full.csv": (org, mhc, family, kind)
           for org, mhc, family in FAMILIES for kind in ("mhc", "tcell")}
COLUMNS = ("family", "kind", "source_file", "record_index", "assay_iri", "epitope_iri", "reference_iri",
           "original_name", "original_sequence", "corrected_sequence", "start", "end", "source_iri",
           "parent_iri", "qualitative", "modification", "old_event_id", "new_event_id", "classification",
           "reasons", "host", "organism", "class", "restriction")


def id_str(row, *fields):
    return next((row.get(field, "").strip() for field in fields if row.get(field, "").strip()), "")


@lru_cache(maxsize=8192)
def event_id(key):
    return hashlib.sha256(json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def plain_sequence(name):
    value = name.strip().upper()
    return value if AMINO.fullmatch(value) else ""


def conditions(row, org, mhc, family):
    species = SPECIES[org]
    host, source = (row.get(k, "").casefold() for k in ("host__name", "epitope__source_organism"))
    positive = row.get("assay__qualitative_measurement", "").strip().casefold()
    restriction = row.get("mhc_restriction__name", "")
    klass = row.get("mhc_restriction__class", "")
    legacy = {
        "positive": "positive" in positive,
        "host": species in host,
        "source_organism": species in source,
        "mhc_class": klass == mhc.removeprefix("mhc-"),
        "mhc_family": family.casefold() in restriction.casefold(),
        "object": row.get("epitope__object_type", "") == "Linear peptide",
    }
    species_word = r"(?<![a-z])" + re.escape(species) + r"(?![a-z])"
    allele = restriction.upper().replace("H-2-", "H2-")
    suffix = (r"(?:[A-Z][0-9]*)?" if org == "mouse" else
              r"(?:[AB](?:[0-9]+)?|W?[0-9]+)?" if mhc == "mhc-II" else r"(?:W?[0-9]+)?")
    token = r"(?<![A-Z0-9])" + re.escape(family) + suffix + r"(?![A-Z0-9])"
    alternative = {
        "positive": positive in ALLOWED,
        "host": bool(re.search(species_word, host)),
        "source_organism": bool(re.search(species_word, source)),
        "mhc_class": klass.strip().upper() == mhc.removeprefix("mhc-"),
        "mhc_family": bool(re.search(token, allele)),
        "object": legacy["object"],
    }
    return legacy, alternative


def compare_record(row):
    name = row.get("epitope__name", "")
    legacy = canonical_epitope(name)
    seq = plain_sequence(name)
    start = get_value(row, "epitope__starting_position")
    end = get_value(row, "epitope__ending_position")
    src, parent = (row.get(f, "") for f in ("epitope__source_molecule_iri", "epitope__molecule_parent_iri"))
    epi = id_str(row, "epitope__epitope_iri", "epitope__iri")
    assay = id_str(row, "assay_id__iedb_iri")
    if not assay and re.search(r"/assay/\d+$", row.get("assay__iri", "")):
        assay = id_str(row, "assay__iri")
    old_key = (legacy, start, end, src.strip(), parent.strip()) if legacy and start and end else None
    reasons = []
    if not seq:
        reasons.append("sequence_requires_review")
    modification = row.get("epitope__modifications", "").strip()
    if modification:
        reasons.append("modification_requires_review")
    if not start or not end:
        reasons.append("missing_coordinates")
    elif not start.isdecimal() or not end.isdecimal() or not 1 <= int(start) <= int(end):
        reasons.append("invalid_coordinates")
    elif seq and int(end) - int(start) + 1 != len(seq):
        reasons.append("coordinate_length_mismatch")
    if not src.strip() or not parent.strip():
        reasons.append("missing_reference")
    if not epi:
        reasons.append("missing_epitope_iri")
    if not assay:
        reasons.append("missing_assay_iri")
    corrected = (seq or name, start, end, src, parent, modification)
    if not seq or "missing_coordinates" in reasons or "invalid_coordinates" in reasons:
        corrected += (epi or assay or name,)
    if old_key is None:
        classification = "added"
    elif corrected != (*old_key, ""):
        classification = "modified"
    else:
        classification = "unchanged"
    return old_key, corrected, classification, reasons, seq, legacy, epi, assay


def exact_possible(sequence, peptide):
    offset = sequence.find(peptide)
    while offset >= 0:
        yield offset + 1
        offset = sequence.find(peptide, offset + 1)


def windows(interval_start, length, protein_length):
    return range(max(1, interval_start + length - 25), min(interval_start, protein_length - 24) + 1)


def audit(archive, output, fasta):
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".iedb-audit-", dir=output.parent) as temporary:
        staged = Path(temporary) / "report"
        staged.mkdir()
        _audit(archive, staged, fasta)
        if output.exists() or output.is_symlink():
            raise FileExistsError(output)
        staged.rename(output)


def _audit(archive, output, fasta):
    csv.field_size_limit(16 * 1024 * 1024)
    proteins = {}
    for org in SPECIES:
        path = fasta / f"{org}_parent_protein_fasta.csv"
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                if row["id_full"] != row["resolved_id"]:
                    continue
                key = org, row["protein_url"].replace("https://", "http://")
                seq = "".join(row["fasta"].splitlines()[1:])
                if key in proteins and proteins[key] != seq:
                    proteins[key] = ""
                else:
                    proteins[key] = seq
    counts = defaultdict(Counter)
    types = defaultdict(Counter)
    labels = defaultdict(Counter)
    filter_counts = defaultdict(Counter)
    family = defaultdict(lambda: defaultdict(set))
    old_archive = defaultdict(set)
    seq_error_examples = defaultdict(list)
    potential = defaultdict(Counter)
    missing_windows = defaultdict(set)
    legacy_windows = defaultdict(set)
    mtime = archive.stat().st_mtime_ns
    expected_members = set(MEMBERS) | {
        f"data_raw/{org}/{mhc}/{fam}/merged_unique_events.csv" for org, mhc, fam in FAMILIES
    }
    seen_members = set()
    with ExitStack() as stack:
        writers = {}
        for name in ("added_events", "removed_events", "modified_events", "discarded_records",
                     "filter_differences", "event_assay_provenance"):
            h = stack.enter_context(gzip.open(output / f"{name}.csv.gz", "wt", newline=""))
            writers[name] = csv.DictWriter(h, fieldnames=COLUMNS)
            writers[name].writeheader()
        proc = stack.enter_context(subprocess.Popen(["zstd", "-qdc", str(archive)], stdout=subprocess.PIPE))
        with tarfile.open(fileobj=proc.stdout, mode="r|", bufsize=1024*1024) as tar:
            for member in tar:
                if member.name not in expected_members:
                    continue
                if not member.isfile() or member.name in seen_members:
                    raise ValueError(f"Invalid or duplicate archive member: {member.name}")
                seen_members.add(member.name)
                entry = MEMBERS.get(member.name)
                if not entry:
                    if member.name.endswith("/merged_unique_events.csv"):
                        fam = Path(member.name).parent.name
                        with tar.extractfile(member) as h:
                            for row in csv.DictReader(line.decode() for line in h):
                                old_archive[fam].add((row["epitope__name_canonical"], row["epitope__starting_position"],
                                    row["epitope__ending_position"], row["source_id"], row["parent_id"]))
                    continue
                org, mhc, fam, kind = entry
                s, c = family[fam], counts[fam]
                with tar.extractfile(member) as h:
                    for i, raw in enumerate(csv.DictReader(line.decode("utf-8") for line in h)):
                        old, new, change, reasons, seq, legacy, epi, assay = compare_record(raw)
                        original, alternative = conditions(raw, org, mhc, fam)
                        qualifier = raw.get("assay__qualitative_measurement", "")
                        labels[fam, kind][qualifier] += 1
                        c[f"{kind}_records"] += 1
                        types[fam, kind]["records"] += 1
                        if assay:
                            s[f"{kind}_assays"].add(assay)
                        else:
                            c[f"{kind}_missing_assay_id"] += 1
                        if epi:
                            s["iedb_epitope_ids"].add(epi)
                        modification = new[5]
                        deduplicated = old is not None and old in s["legacy_events"]
                        if old is None:
                            c["legacy_discard_no_peptide" if not legacy else "legacy_discard_missing_coordinates"] += 1
                        elif old in s["legacy_events"]:
                            c["legacy_dedup_rows"] += 1
                        if old:
                            s["legacy_events"].add(old)
                            s["legacy_epitopes"].add(old[0])
                            if old[3]: s["legacy_source"].add(old[3])
                            if old[4]: s["legacy_parent"].add(old[4])
                        s["experimental_events"].add(new)
                        if seq: s["experimental_epitopes"].add(seq)
                        if new[3]: s["experimental_source"].add(new[3])
                        if new[4]: s["experimental_parent"].add(new[4])
                        c[f"{change}_records"] += 1
                        types[fam, kind][f"{change}_records"] += 1
                        for reason in reasons:
                            c[reason] += 1
                            types[fam, kind][reason] += 1
                        if not seq and legacy:
                            c["regex_extracted_unverified_substring"] += 1
                        if seq and legacy != seq:
                            c["regex_different_from_validated_plain_sequence"] += 1
                        if "missing_coordinates" in reasons:
                            s["events_missing_coordinates"].add(new)
                        if change == "added": s["added"].add(new)
                        if change == "modified": s["modified"].add((old, new))
                        if reasons: s["pending"].add(new)
                        if old and (not seq or "modification_requires_review" in reasons):
                            s["legacy_events_quarantined"].add(old)
                        record = dict(family=fam, kind=kind, source_file=member.name, record_index=i,
                                      assay_iri=assay, epitope_iri=epi, reference_iri=raw.get("reference__iedb_iri"),
                                      original_name=raw.get("epitope__name"), original_sequence=legacy,
                                      corrected_sequence=seq, start=new[1], end=new[2], source_iri=new[3],
                                      parent_iri=new[4], qualitative=qualifier, modification=new[5],
                                      old_event_id=event_id(old) if old else "",new_event_id=event_id(new),
                                      classification=change, reasons="|".join(reasons),
                                      host=raw.get("host__name"), organism=raw.get("epitope__source_organism"),
                                      **{"class":raw.get("mhc_restriction__class"),"restriction":raw.get("mhc_restriction__name")})
                        writers["event_assay_provenance"].writerow(record)
                        if change in {"added", "modified"}:
                            # Keep a single event/pair entry; per-assay trace is separate.
                            dedup = new if change == "added" else (old, new)
                            if dedup not in s[f"{change}_emitted"]:
                                writers[f"{change}_events"].writerow(record)
                                s[f"{change}_emitted"].add(dedup)
                        if old is None or reasons or deduplicated:
                            discarded_reasons = [*reasons]
                            if deduplicated:
                                discarded_reasons.append("legacy_deduplicated_assay_link")
                            if old is None:
                                discarded_reasons.append("legacy_no_peptide" if not legacy else "legacy_missing_coordinates")
                            writers["discarded_records"].writerow(dict(record, reasons="|".join(discarded_reasons)))
                        if old and (not seq or "modification_requires_review" in reasons):
                            if old not in s["quarantine_emitted"]:
                                writers["removed_events"].writerow(dict(record, classification="quarantined_from_plain_positive"))
                                s["quarantine_emitted"].add(old)
                        variants = []
                        for criterion in original:
                            other_pass = all(v for k, v in original.items() if k != criterion)
                            if other_pass and original[criterion] != alternative[criterion]:
                                direction = "recovered" if alternative[criterion] else "excluded"
                                filter_counts[fam, kind][f"{criterion}:{direction}"] += 1
                                variants.append(f"{criterion}:{direction}")
                        if not all(original.values()): filter_counts[fam, kind]["legacy_local_mismatch"] += 1
                        for criterion, field in (("host", "host__iri"), ("source_organism", "epitope__source_organism_iri")):
                            tax = re.search(r"(?:_|/)([0-9]+)$",raw.get(field,""))
                            status = "missing_taxon" if not tax else "exact_species_taxon" if tax[1]==TAXON[org] else "other_taxon_or_strain"
                            filter_counts[fam,kind][f"{criterion}:{status}"] += 1
                        if variants:
                            writers["filter_differences"].writerow(dict(record, reasons="|".join(variants)))
                        if (change == "added" or (old and (not seq or modification))) and new not in s["impact_seen"]:
                            s["impact_seen"].add(new)
                            ref = proteins.get((org, new[4].replace("https://", "http://")), "")
                            if not ref:
                                continue
                            if seq and not modification and "missing_coordinates" in reasons and len(seq) <= 25:
                                loci = list(exact_possible(ref, seq))
                                if len(loci) == 1:
                                    potential[fam]["missing_coordinate_unique_parent_events"] += 1
                                    s["potential_peptides"].add(seq)
                                    s["potential_proteins"].add(new[4])
                                    for pos in windows(loci[0], len(seq), len(ref)):
                                        missing_windows[fam].add((new[4], pos))
                                elif loci: potential[fam]["missing_coordinate_multiple_parent_events"] += 1
                            if old and (not seq or modification) and old[1].isdecimal() and old[2].isdecimal():
                                a,b=map(int,old[1:3])
                                if 1<=a<=b<=len(ref) and ref[a-1:b]==old[0] and len(old[0])<=25:
                                    s["legacy_quarantine_exact_parent_events"].add(old)
                                    for pos in windows(a,len(old[0]),len(ref)):
                                        legacy_windows[fam].add((old[4],pos))
                print("READ", member.name, types[fam,kind]["records"], flush=True)
        while proc.stdout.read(1024*1024): pass
        if proc.wait():
            raise RuntimeError("Archive integrity check failed")
    missing = expected_members - seen_members
    if missing:
        raise ValueError(f"Missing archive members: {', '.join(sorted(missing))}")
    if archive.stat().st_mtime_ns != mtime:
        raise ValueError("Archive changed during the comparison")
    table = []
    for _, _, fam in FAMILIES:
        c, s = counts[fam], family[fam]
        if s["legacy_events"] != old_archive[fam]:
            raise ValueError(f"Legacy replay differs from archived merged event set in {fam}")
        row = {"family":fam, **dict(c), **{k:len(v) for k,v in s.items() if k not in {
            "old_to_new", "impact_seen", "added_emitted", "modified_emitted", "quarantine_emitted"}},
            **dict(potential[fam]),"possible_windows_unique_parent_missing_coordinates":len(missing_windows[fam]),
            "legacy_exact_parent_windows_for_quarantined_events":len(legacy_windows[fam]),
            "legacy_merge_matches_archive":True,
        }
        table.append(row)
    def save_csv(name, rows):
        columns = list(dict.fromkeys(k for row in rows for k in row))
        with (output/name).open("w",newline="") as h:
            w=csv.DictWriter(h,fieldnames=columns,restval=0);w.writeheader();w.writerows(rows)
    save_csv("by_family.csv",table)
    save_csv("by_family_assay_type.csv",[dict(family=f,kind=k,**c) for (f,k),c in sorted(types.items())])
    save_csv("qualitative.csv",[dict(family=f,kind=k,value=v,records=n) for (f,k),c in sorted(labels.items()) for v,n in c.items()])
    save_csv("filters.csv",[dict(family=f,kind=k,criterion=d,records=n) for (f,k),c in sorted(filter_counts.items()) for d,n in c.items()])
    write_json(output/"summary.json",dict(archive=str(archive),archive_size=archive.stat().st_size,
                                        families=table,filter_changes={f"{f}/{k}":dict(c) for (f,k),c in filter_counts.items()}))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,default=BASE)
    p.add_argument("--fasta",type=Path,default=FASTA)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if any(a.output.resolve().is_relative_to(root.resolve()) for root in (a.archive.parent,a.fasta)):
        p.error("Output must be separate from input files")
    audit(a.archive,a.output,a.fasta)

if __name__=="__main__":
    main()
