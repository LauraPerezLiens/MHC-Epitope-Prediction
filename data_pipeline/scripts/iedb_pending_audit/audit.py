"""Resolve legacy groups held back by the experimental normalization audit."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from functools import lru_cache
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import time

import requests

from data_pipeline.scripts.global_epitope_labels.build import FAMILIES, ROOT, output_lock, write_json
from data_pipeline.scripts.rebuild_iedb.rebuild import fasta_records, load_archived, project_interval

DATA = ROOT / "results/iedb_download_audit_20261118"
PRIOR = ROOT / "results/epitope_counterfactual_20261118"
INPUT = ROOT / "results/source_audits_inputs_20261118"
ORGANISM = {fam: org for org, _, fam in FAMILIES}
VALID = re.compile(r"[ACDEFGHIKLMNPQRSTVWY]+")
ID = re.compile(r"/(epitope|assay)/(\d+)$")
VERSIONED = re.compile(r"[A-Z][A-Z0-9_]*\.\d+$")
PDB_CHAIN = re.compile(r"[0-9][A-Z0-9]{3}_[A-Z0-9]+$", re.I)


def norm(url):
    return re.sub(r"^https?://", "", url.strip()).rstrip("/")


def acc(url):
    return norm(url).rsplit("/", 1)[-1]


def numeric(iri, kind):
    match = ID.search(iri)
    return match[2] if match and match[1] == kind else ""


def event_key(row):
    return (row["family"], row.get("original_sequence", row.get("epitope")),
            int(row.get("start", row.get("original_start"))), int(row.get("end", row.get("original_end"))),
            norm(row.get("source_iri", row.get("source"))), norm(row.get("parent_iri", row.get("parent"))))


def group_key(row):
    return row["family"], row["old_event_id"]


def read_jsonl(path):
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f]


def link(output, previous):
    path = output / "assay_links.jsonl.gz"
    with gzip.open(previous / "removed_events.csv.gz", "rt", newline="") as f:
        groups = {group_key(r):r for r in csv.DictReader(f)}
    if not path.is_file():
        temporary = path.with_suffix(".partial")
        observed = set()
        with gzip.open(previous / "event_assay_provenance.csv.gz", "rt", newline="") as f, gzip.open(temporary, "wt") as h:
            for row in csv.DictReader(f):
                key = group_key(row)
                if key in groups:
                    h.write(json.dumps(row, ensure_ascii=False) + "\n")
                    observed.add(key)
        if observed != groups.keys():
            raise ValueError("Missing raw assay links for nominated groups")
        temporary.replace(path)
    links = defaultdict(list)
    for row in read_jsonl(path):
        links[group_key(row)].append(row)
    if links.keys() != groups.keys() or len(groups) != 44_907:
        raise ValueError("Unexpected audited population")
    return groups, links


def fetch(url, params, cache, extension):
    name = hashlib.sha256(json.dumps((url, params),sort_keys=True).encode()).hexdigest()
    path = cache / f"{name}.{extension}"
    if path.is_file():
        return path.read_text()
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=18)
            if r.status_code in {400,404}:
                return ""
            r.raise_for_status()
            temporary = path.with_suffix(".partial")
            temporary.write_text(r.text)
            temporary.replace(path)
            return r.text
        except requests.RequestException:
            if attempt < 2:
                time.sleep(1 + attempt)
    return None


def batches(items, n):
    items = sorted(items)
    return [items[i:i+n] for i in range(0,len(items),n)]


def fetch_iedb(links, old, cache):
    api = json.loads((old / "iedb_records.json").read_text())
    direct = {numeric(r["epitope_iri"],"epitope") for rows in links.values() for r in rows} - {""}
    sequences = {r["original_sequence"] for rows in links.values() for r in rows
                 if not numeric(r["epitope_iri"],"epitope") and VALID.fullmatch(r["original_sequence"])}
    fields = "structure_id,linear_sequence,curated_source_antigens,tcell_ids,elution_ids,iedb_assay_ids,e_modification"
    tasks = [(field, b) for field,values in (("structure_id",direct-api.keys()),("linear_sequence",sequences))
             for b in batches(values,80)]
    def one(task):
        field, values = task
        text = fetch("https://query-api.iedb.org/epitope_search",
                     {field:"in.("+",".join(values)+")","select":fields},cache,"json")
        return json.loads(text) if text else None
    failures=0
    with ThreadPoolExecutor(5) as pool:
        for i, rows in enumerate(pool.map(one,tasks),1):
            if rows is None:
                failures+=1
            else:
                api.update({str(row["structure_id"]):row for row in rows})
            if i%40==0 or i==len(tasks):
                print("IEDB",i,"/",len(tasks),"failed",failures,flush=True)
    by_sequence = defaultdict(list)
    for row in api.values():
        if row.get("linear_sequence") in sequences:
            by_sequence[row["linear_sequence"]].append(row)
    return api, by_sequence, dict(requested_batches=len(tasks), failed_batches=failures,
                                  requested_structure_ids=len(direct), returned_structure_ids=len(direct & api.keys()))


def observed_references(old, archive):
    refs = {}
    for path in (old / "source_batches").glob("*.fasta"):
        for ref in fasta_records(path.read_text()):
            refs.setdefault(ref.accession,ref.sequence)
    alias = old / "parent_alias_lookup/source_batches"
    for path in alias.glob("*.fasta"):
        for ref in fasta_records(path.read_text()):
            refs.setdefault(ref.accession,ref.sequence)
    name = old / "source_uniprot_sequences.json"
    if name.is_file():
        refs.update(json.loads(name.read_text()))
    for (_,url),ref in archive.items():
        if ref.version and "uniprot.org/" in url and "." not in ref.accession and "-" not in ref.accession:
            refs.setdefault(f"{ref.accession}.{ref.version}",ref.sequence)
        elif VERSIONED.fullmatch(ref.accession):
            refs.setdefault(ref.accession,ref.sequence)
    return refs


def extend_references(groups, refs, cache):
    missing = {acc(row["source_iri"]) for row in groups.values()
               if VERSIONED.fullmatch(acc(row["source_iri"])) or PDB_CHAIN.fullmatch(acc(row["source_iri"]))} - refs.keys()
    failed=0
    def ncbi(batch):
        text = fetch("https://www.ncbi.nlm.nih.gov/sviewer/viewer.fcgi",
                     {"db":"protein","id":",".join(batch),"report":"fasta","retmode":"text"},cache,"fasta")
        if text and text.startswith(">"):
            return text
        if text == "" and len(batch)>8:
            mid=len(batch)//2
            return (ncbi(batch[:mid]) or "") + "\n" + (ncbi(batch[mid:]) or "")
        return None
    tasks=batches(missing,35)
    with ThreadPoolExecutor(3) as pool:
        for i,text in enumerate(pool.map(ncbi,tasks),1):
            if text:
                for ref in fasta_records(text):
                    if ref.accession in missing:
                        refs.setdefault(ref.accession,ref.sequence)
            else:
                failed+=1
            if i%25==0 or i==len(tasks):
                print("NCBI",i,"/",len(tasks),"without payload",failed,flush=True)
    candidates={acc(r["source_iri"]) for r in groups.values() if "uniprot.org/" in r["source_iri"]
                and VERSIONED.fullmatch(acc(r["source_iri"])) and acc(r["source_iri"]) not in refs}
    def uniprot(batch):
        return fetch("https://rest.uniprot.org/uniprotkb/search", {
            "query":"("+" OR ".join(f"accession:{a}" for a in batch)+")","format":"tsv",
            "fields":"accession,sequence_version,sequence","size":100},cache,"tsv")
    with ThreadPoolExecutor(3) as pool:
        for text in pool.map(uniprot,batches({a.rsplit(".",1)[0] for a in candidates},35)):
            if text:
                for row in csv.DictReader(io.StringIO(text),delimiter="\t"):
                    token=row["Entry"]+"."+row["Sequence version"]
                    if token in candidates and row["Sequence"]:
                        refs.setdefault(token,row["Sequence"])
    return dict(targeted_source_accessions=len(missing), resolved_targeted_sources=len(missing & refs.keys()),
                ncbi_batches_without_payload=failed)


def exact(sequence, peptide, a, b):
    return isinstance(a,int) and isinstance(b,int) and 1<=a<=b<=len(sequence) and sequence[a-1:b]==peptide


def borrowed_key(e):
    return event_key(e)


def curated(row, api, by_sequence):
    eid=numeric(row["epitope_iri"],"epitope")
    if eid:
        record=api.get(eid)
        return [record] if record else []
    aid=numeric(row["assay_iri"],"assay")
    if not aid:
        return []
    return [r for r in by_sequence[row["original_sequence"]] if any(
        str(value)==aid for field in ("tcell_ids","elution_ids","iedb_assay_ids") for value in r.get(field) or []
    )]


@lru_cache(maxsize=14000)
def sha(sequence):
    return hashlib.sha256(sequence.encode()).hexdigest()


def verify_group(row, links, api, by_sequence, archive, refs, prior_event):
    fam=row["family"]; org=ORGANISM[fam]
    start,end=int(row["start"]),int(row["end"])
    source_url,parent_url=norm(row["source_iri"]),norm(row["parent_iri"])
    parent=archive.get((org,parent_url))
    source_id=acc(source_url)
    parent_sequence=parent.sequence if parent else ""
    legacy=row["original_sequence"]
    observed={}
    for link in links:
        for ep in curated(link,api,by_sequence):
            ep_id=str(ep["structure_id"])
            modified = bool(link["modification"] or ep.get("e_modification"))
            plain = bool(link["corrected_sequence"] and not modified)
            key=ep_id,plain,modified
            if key not in observed:
                observed[key]={"record":ep,"assays":set()}
            observed[key]["assays"].add(link["assay_iri"])
    evidence=[]
    statements=Counter()
    observed_ids=set()
    structures=[]
    for (ep_id,plain,modified), observation in observed.items():
        record=observation["record"]; peptide=record.get("linear_sequence")
        observed_ids.add(ep_id)
        structure=dict(epitope_id=ep_id,linear_sequence=peptide,modified=modified,plain=plain,
                       source_exact=False,parent_exact=False)
        structures.append(structure)
        if not peptide or not VALID.fullmatch(peptide):
            statements["canonical_nonstandard_or_absent"]+=1
            continue
        if peptide!=legacy:
            statements["backbone_changed"]+=1
        annotated=record.get("curated_source_antigens") or []
        archived_source=archive.get((org,source_url))
        source_sequence=refs.get(source_id)
        actual_source_id=source_id
        if not source_sequence and VERSIONED.fullmatch(source_id) and archived_source:
            source_sequence=archived_source.sequence
        # Unversioned source is used only with a unique, versioned, archived IEDB witness.
        if not source_sequence and source_id:
            witnesses={(a.get("accession"),refs.get(a.get("accession"))) for a in annotated
                       if str(a.get("accession","")).startswith(source_id+".")
                       and (a.get("starting_position"),a.get("ending_position"))==(start,end)
                       and refs.get(a.get("accession"))}
            if len(witnesses)==1:
                actual_source_id,source_sequence=next(iter(witnesses))
        source_exact=bool(source_sequence and exact(source_sequence,peptide,start,end))
        structure.update(source_accession=actual_source_id,source_exact=source_exact)
        if source_sequence:
            statements["source_interval_exact" if source_exact else "source_interval_incompatible"]+=1
        else:
            statements["source_reference_unverified"]+=1
        if not parent:
            statements["parent_reference_unavailable"]+=1
            continue
        if peptide not in parent_sequence:
            statements["peptide_absent_from_parent"]+=1
            continue
        explicit=set()
        for a in annotated:
            lo,hi=a.get("starting_position"),a.get("ending_position")
            target=a.get("accession")
            same_version=bool(parent.version and a.get("iri")==f"UNIPROT:{parent.accession}.{parent.version}")
            identical_sequence=bool(target and refs.get(target)==parent_sequence)
            if (same_version or identical_sequence) and exact(parent_sequence,peptide,lo,hi):
                explicit.add((lo,hi))
        prior=None
        if (prior_event and prior_event["confidence"]=="verified" and peptide==prior_event["epitope"]
                and prior_event["parent_sequence_sha256"]==parent.sha256
                and ep_id in set(prior_event["ids"].split("|")) | set(prior_event["supporting_iedb_ids"].split("|"))
                and exact(parent_sequence,peptide,prior_event["corrected_start"],prior_event["corrected_end"])):
            prior=prior_event["corrected_start"],prior_event["corrected_end"]
        # Conflicting verified loci are not settled by isolated peptide matching.
        if len(explicit | ({prior} if prior else set()))>1:
            statements["conflicting_explicit_or_prior_loci"]+=1
            continue
        if explicit:
            coords, method=next(iter(explicit)),"iedb_exact_parent_reference"
        elif prior:
            coords, method=prior,"previous_validated_mapping"
        elif source_exact and source_sequence==parent_sequence:
            coords, method=(start,end),"whole_reference_identity"
        elif source_exact:
            coords, method=project_interval(source_sequence,parent_sequence,start,end,peptide),"full_reference_alignment"
        else:
            coords, method=None,""
        if not coords:
            statements["no_unambiguous_parent_mapping"]+=1
            continue
        structure.update(parent_exact=True,parent_start=coords[0],parent_end=coords[1],method=method)
        evidence.append(dict(epitope_id=ep_id,assay_iris=sorted(observation["assays"]),plain=plain,modified=modified,peptide=peptide,
                             parent_start=coords[0],parent_end=coords[1],method=method,
                             source_accession=actual_source_id,source_exact=source_exact,
                             source_sha256=sha(source_sequence) if source_sequence else "",
                             parent_sha256=parent.sha256,coordinates_corrected=coords!=(start,end)))
    distinct={(e["peptide"],e["parent_start"],e["parent_end"]) for e in evidence}
    if len(distinct)>1:
        state="conflicting_verified_loci_or_backbones"
    elif any(e["plain"] for e in evidence):
        state="simple_verified"
    elif any(e["modified"] for e in evidence):
        state="modified_backbone_and_parent_verified"
    elif evidence:
        state="backbone_mapped_chemistry_pending"
    elif observed and statements["peptide_absent_from_parent"]==len(observed):
        state="incompatible_parent_reference"
    elif not observed:
        state="requires_iedb_structure_or_assay_link"
    elif statements["canonical_nonstandard_or_absent"] or statements["parent_reference_unavailable"] or statements["source_reference_unverified"]:
        state="requires_reference_or_backbone"
    else:
        state="mapping_not_verified"
    return dict(family=fam,old_event_id=row["old_event_id"],state=state,legacy_backbone=legacy,
                source_iri=row["source_iri"],parent_iri=row["parent_iri"],original_start=start,original_end=end,
                old_exact_parent=bool(parent and exact(parent_sequence,legacy,start,end)),
                corrected=bool(len(distinct)==1 and any(e["coordinates_corrected"] for e in evidence)),
                raw_records=len(links),assay_iris=sorted({r["assay_iri"] for r in links if r["assay_iri"]}),
                original_epitope_iris=sorted({r["epitope_iri"] for r in links if r["epitope_iri"]}),
                verified_structure_ids=sorted(observed_ids),normalized_backbones=sorted({e["peptide"] for e in evidence}),
                original_names=sorted({r["original_name"] for r in links}),
                modifications=sorted({r["modification"] for r in links if r["modification"]}),
                prior_event_index=prior_event["event_index"] if prior_event else "",
                prior_verified=bool(prior_event and prior_event["confidence"]=="verified"),
                evidence=evidence,structure_observations=structures,observations=dict(statements))


def run(output, previous, old, inputs):
    output.mkdir(parents=True,exist_ok=True)
    cache=output/"cache";cache.mkdir(exist_ok=True)
    with output_lock(output):
        groups,links=link(output,previous)
        print("LINKED",len(groups),"groups",sum(map(len,links.values())),"records",flush=True)
        api,by_sequence,iedb_stats=fetch_iedb(links,old,cache)
        archive=load_archived(inputs/"data_intermediate")
        refs=observed_references(old,archive)
        ref_stats=extend_references(groups,refs,cache)
        needed={}
        for key,row in groups.items():
            source_id=acc(row["source_iri"])
            parent_id=acc(row["parent_iri"]).split("-")[0].split(".")[0]
            for assay_row in links[key]:
                for record in curated(assay_row,api,by_sequence):
                    for a in record.get("curated_source_antigens") or []:
                        token=a.get("accession","")
                        if not VERSIONED.fullmatch(token) or token in refs:
                            continue
                        base=token.rsplit(".",1)[0]
                        source_witness=base==source_id and (a.get("starting_position"),a.get("ending_position"))==(
                            int(row["start"]),int(row["end"]))
                        if not source_witness and base!=parent_id:
                            continue
                        provider="www.uniprot.org/uniprot/" if a.get("iri","").startswith("UNIPROT:") else "www.ncbi.nlm.nih.gov/protein/"
                        needed[token]={"source_iri":provider+token}
        hint_stats=extend_references(needed,refs,cache)
        ref_stats["versioned_iedb_witness_lookup"]=hint_stats
        with (old/"event_resolution.csv").open(newline="") as f:
            wanted={event_key(row) for row in groups.values()}
            earlier={borrowed_key(e):dict(e, corrected_start=int(e["corrected_start"]) if e["corrected_start"] else None,
                                        corrected_end=int(e["corrected_end"]) if e["corrected_end"] else None)
                     for e in csv.DictReader(f) if borrowed_key(e) in wanted}
        result=[verify_group(row,links[key],api,by_sequence,archive,refs,earlier.get(event_key(row)))
                for key,row in groups.items()]
        states=Counter(r["state"] for r in result)
        write_json(output/"event_resolution.json",result)
        write_json(output/"coverage.json",dict(groups=len(result),states=dict(states),raw_records=sum(map(len,links.values())),
                                                overlap_previous=len(earlier),**iedb_stats,**ref_stats))
        with (output/"event_resolution.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader()
            for r in result:
                w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
        print("RESOLVED",states,flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--download-audit",type=Path,default=DATA)
    p.add_argument("--prior",type=Path,default=PRIOR)
    p.add_argument("--inputs",type=Path,default=INPUT)
    a=p.parse_args()
    if any(a.output.resolve().is_relative_to(x.resolve()) for x in (a.download_audit,a.prior,a.inputs)):
        p.error("Output must be separate from the source audits.")
    run(a.output,a.download_audit,a.prior,a.inputs)


if __name__=="__main__":
    main()
