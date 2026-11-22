"""Compute counterfactual positions and global label changes without writing a dataset."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from data_pipeline.scripts.global_epitope_labels.build import FAMILIES, ROOT, row_path, write_json
from data_pipeline.scripts.iedb_download_audit.audit import event_id, windows
from data_pipeline.scripts.iedb_pending_audit.audit import INPUT, ORGANISM, exact, norm
from data_pipeline.scripts.rebuild_iedb.rebuild import load_archived

BOTH = {"simple_verified", "modified_backbone_and_parent_verified"}


def lookup(index, candidates):
    with closing(sqlite3.connect(index.resolve().as_uri()+"?mode=ro",uri=True)) as db:
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("PRAGMA cache_size=-262144")
        db.execute("CREATE TEMP TABLE selected (seq TEXT PRIMARY KEY) WITHOUT ROWID")
        db.executemany("INSERT INTO selected VALUES (?)",((seq,) for seq in sorted(candidates)))
        return dict(db.execute("SELECT s.seq,c.positive FROM selected s CROSS JOIN counts c ON c.sequence=s.seq"))


def run(output, inputs, previous, dataset):
    events=json.loads((output/"event_resolution.json").read_text())
    expected=json.loads((previous/"window_sensitivity.json").read_text())
    baseline=json.loads((dataset/"summary.json").read_text())
    refs=load_archived(inputs/"data_intermediate")
    sources={v["mhc_family"]:v for v in json.loads((dataset/"config.json").read_text())["sources"]}
    groups={(e["family"],e["old_event_id"]):e for e in events}
    assert len(groups)==len(events)==44907
    c=defaultdict(Counter)
    old_positives=Counter()
    touched=defaultdict(set)
    historical=defaultdict(set)
    mapped_plain=defaultdict(set)
    mapped_any=defaultdict(set)
    positions=defaultdict(set)
    mapped_positions=defaultdict(set)
    for e in events:
        fam=e["family"]
        c[fam]["groups"]+=1
        c[fam][e["state"]]+=1
        c[fam]["corrected"]+=int(e["corrected"])
        c[fam]["previous_coordinate_audit_overlap"]+=bool(e["prior_event_index"] != "")
        c[fam]["previous_coordinate_verified"]+=bool(e["prior_verified"])
        c[fam]["groups_with_iedb_structure"]+=bool(e["verified_structure_ids"])
        if e["state"] not in BOTH:
            continue
        c[fam]["groups_with_verified_parent_mapping"]+=1
        c[fam]["verified_mapping_also_exact_source"]+=any(v["source_exact"] for v in e["evidence"])
        c[fam]["verified_parent_with_changed_backbone"]+=any(v["peptide"]!=e["legacy_backbone"] for v in e["evidence"])
        ref=refs[ORGANISM[fam],norm(e["parent_iri"])]
        for v in e["evidence"]:
            a,b=v["parent_start"],v["parent_end"]
            assert exact(ref.sequence,v["peptide"],a,b)
            for start in windows(a,len(v["peptide"]),len(ref.sequence)):
                seq=ref.sequence[start-1:start+24]
                mapped_any[fam].add(seq)
                mapped_positions[fam].add((norm(e["parent_iri"]),start))
                if v["plain"]:
                    mapped_plain[fam].add(seq)
                touched[fam].add(seq)
    for org,mhc,fam in FAMILIES:
        file=inputs/"data_raw"/org/mhc/fam/"merged_unique_events.csv"
        affected_keys=set()
        with file.open(newline="") as handle:
            for r in csv.DictReader(handle):
                key=(r["epitope__name_canonical"],r["epitope__starting_position"],r["epitope__ending_position"],
                     r["source_id"],r["parent_id"])
                if (fam,event_id(key)) not in groups:
                    continue
                peptide,a,b,_,parent=key
                a,b=int(a),int(b)
                u=norm(parent)
                ref=refs.get((org,u))
                if not ref or len(ref.sequence)<25 or not exact(ref.sequence,peptide,a,b):
                    continue
                c[fam]["old_locally_accepted_groups"]+=1
                for start in windows(a,len(peptide),len(ref.sequence)):
                    seq=ref.sequence[start-1:start+24]
                    assert len(seq)==25
                    affected_keys.add((u,start,peptide))
                    historical[fam].add(seq)
                    touched[fam].add(seq)
                    positions[fam].add((u,start))
        affected_proteins={url for url,_,_ in affected_keys}
        supported_elsewhere=set()
        with file.open(newline="") as handle:
            for r in csv.DictReader(handle):
                url=norm(r["parent_id"])
                if url not in affected_proteins:
                    continue
                peptide=r["epitope__name_canonical"]
                a,b=r["epitope__starting_position"],r["epitope__ending_position"]
                key=peptide,a,b,r["source_id"],r["parent_id"]
                if (fam,event_id(key)) in groups:
                    continue
                ref=refs[org,url]
                a,b=int(a),int(b)
                if exact(ref.sequence,peptide,a,b):
                    for w in windows(a,len(peptide),len(ref.sequence)):
                        member=url,w,peptide
                        if member in affected_keys:
                            supported_elsewhere.add(member)
        retire=affected_keys-supported_elsewhere
        # Attribute removals to actual retained Parquet rows. Replaying legacy
        # events alone can overcount annotations duplicated or absent downstream.
        if retire:
            urls=pa.array(sorted({p+u for u in affected_proteins for p in ("http://","https://")}),type=pa.string())
            cols=["protein_url","window_start","selected_epitope","25aa_seq","contains_epitope"]
            actual_positions=set()
            table=pq.ParquetFile(row_path(dataset,sources[fam]))
            for batch in table.iter_batches(batch_size=100_000,columns=cols):
                selector=pc.and_(pc.equal(batch["contains_epitope"],1),pc.is_in(batch["protein_url"],value_set=urls))
                subset=pa.Table.from_batches([batch]).filter(selector)
                for url,w,pep,seq,_ in zip(*(v.to_pylist() for v in subset.columns)):
                    u=norm(url); w=int(w)
                    if (u,w,pep) in affected_keys:
                        actual_positions.add((u,w))
                    if (u,w,pep) in retire and exact(refs[org,u].sequence,seq,w,w+24):
                        old_positives[seq]+=1
                        c[fam]["attributed_existing_positive_rows"]+=1
            c[fam]["actual_positive_positions_with_matching_annotations"]=len(actual_positions)
        c[fam]["not_verified_as_simple_or_modified"] = c[fam]["groups"] - c[fam]["groups_with_verified_parent_mapping"]
        c[fam]["verified_mapped_positions"] = len(mapped_positions[fam])
        c[fam]["historical_positive_positions"] = len(positions[fam])
        c[fam]["historical_distinct_sequences"] = len(historical[fam])
        c[fam]["affected_distinct_sequences"] = len(touched[fam])
        assert c[fam]["historical_positive_positions"]==expected["families"][fam]["affected_legacy_positive_positions"]
        assert c[fam]["old_locally_accepted_groups"]==expected["families"][fam].get("removed_groups_accepted_by_legacy_local_fasta_check",0)
        print("IMPACT",fam,len(positions[fam]),len(touched[fam]),flush=True)
    candidates=set().union(*touched.values())
    old=lookup(dataset/"index.sqlite",candidates)
    assert all(old.get(seq,-1)>=count for seq,count in old_positives.items())
    old_independent={seq for seq,positive in old.items() if positive>old_positives[seq]}
    results={}
    scenario_map={}
    for name, mapped in (("verified_backbone_sensitivity",mapped_any),("strict_plain_sensitivity",mapped_plain)):
        rescued=set().union(*mapped.values())
        positive=old_independent|rescued
        keep={s for s in old if old[s]>0 and s in positive}
        loses={s for s in old if old[s]>0 and s not in positive}
        rises={s for s in old if not old[s] and s in positive}
        new=rescued-old.keys()
        results[name]={"affected_global_1_retained":len(keep),"global_1_to_0":len(loses),"global_0_to_1":len(rises),
                       "new_positive_sequences_outside_current_index":len(new),
                       "global_1_retained_by_independent_old_evidence":len(old_independent)}
        for fam in ORGANISM:
            for label,collection in (("affected_global_1_retained",keep),("global_1_to_0",loses),("global_0_to_1",rises)):
                c[fam][f"{name}_{label}"]=len(collection & touched[fam])
        scenario_map[name]=(keep,loses,rises,new)
    with (output/"global_scenarios.csv").open("w",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(("deterministic_sequence","current_global_label","verified_backbone_sensitivity","strict_plain_sensitivity"))
        for s in sorted(candidates):
            flags=[]
            for name in scenario_map:
                keep,loses,rises,new=scenario_map[name]
                flags.append("retained_1" if s in keep else "1_to_0" if s in loses else "0_to_1" if s in rises
                             else "new_positive_sequence" if s in new else "no_change_or_not_indexed")
            writer.writerow((s, int(old[s]>0) if s in old else "",*flags))
    fields=list(dict.fromkeys(f for counters in c.values() for f in counters))
    with (output/"by_family.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["family",*fields],restval=0);writer.writeheader()
        for fam in ORGANISM:
            writer.writerow(dict(family=fam,**c[fam]))
    totals=sum(c.values(),Counter())
    earlier=ROOT/"results/epitope_counterfactual_20261118/global_scenarios.csv"
    prior_rises=set()
    if earlier.is_file():
        with earlier.open(newline="") as f:
            prior_rises={r["sequence"] for r in csv.DictReader(f) if r["scenario"].startswith("0_to_1_")}
    for name,(_,_,rises,_) in scenario_map.items():
        results[name]["global_0_to_1_overlaps_previous_audit"] = len(rises & prior_rises)
    write_json(output/"impact.json",dict(family={fam:dict(counts) for fam,counts in c.items()},
              totals=dict(totals),scenarios=results,distinct_affected_sequences=len(candidates),
              distinct_historical_sequences=len(set().union(*historical.values())),distinct_affected_existing_sequences=len(old),
              global_index_sequences=baseline["unique_sequences"]))
    print("SCENARIOS",results,flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--inputs",type=Path,default=INPUT)
    p.add_argument("--previous",type=Path,default=ROOT/"results/iedb_download_audit_20261118")
    p.add_argument("--dataset",type=Path,default=ROOT/"data/global_epitope_labels")
    a=p.parse_args()
    run(a.output,a.inputs,a.previous,a.dataset)


if __name__=="__main__":
    main()
