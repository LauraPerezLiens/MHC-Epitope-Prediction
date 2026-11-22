"""Audit modified IEDB entities and independent simple-peptide evidence."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
import gzip
import itertools
import json
from pathlib import Path
import re
import sqlite3

from data_pipeline.scripts.global_epitope_labels.build import FAMILIES, ROOT, output_lock, write_json
from data_pipeline.scripts.iedb_pending_audit.audit import (
    acc, batches, exact, fetch, norm, numeric, observed_references,
)
from data_pipeline.scripts.rebuild_iedb.rebuild import load_archived, project_interval

IN = ROOT / "results/source_audits_inputs_20261118"
DOWNLOAD = ROOT / "results/iedb_download_audit_20261118"
PENDING = ROOT / "results/iedb_pending_evidence_20261118"
PRIOR = ROOT / "results/epitope_counterfactual_20261118"
DATASET = ROOT / "data/global_epitope_labels"
ORG = {f:o for o,_,f in FAMILIES}
AA = re.compile(r"[ACDEFGHIKLMNPQRSTVWY]+$")
POSITIVE = {"positive","positive-low","positive-intermediate","positive-medium","positive-high"}


def database(output):
    db=sqlite3.connect(output/"audit_work.sqlite")
    db.executescript("""
      PRAGMA journal_mode=WAL;
      PRAGMA synchronous=NORMAL;
      PRAGMA cache_size=-131072;
      CREATE TABLE IF NOT EXISTS records(
        family TEXT, kind TEXT, file TEXT, ord INTEGER, assay TEXT, eid TEXT, name TEXT,
        seq TEXT, chemistry TEXT, modification TEXT, src TEXT, par TEXT, a INTEGER, b INTEGER,
        old_id TEXT, qualitative TEXT, legacy TEXT,
        PRIMARY KEY(file,ord)
      ) WITHOUT ROWID;
      CREATE TABLE IF NOT EXISTS checkpoints(stage TEXT PRIMARY KEY);
    """)
    return db


def integer(value):
    try:
        return int(value)
    except (TypeError,ValueError):
        return None


def classify(row):
    if row["modification"].strip():
        return "modified"
    if AA.fullmatch(row["corrected_sequence"]):
        return "simple"
    return "uncertain"


def ingest(db):
    if db.execute("SELECT 1 FROM checkpoints WHERE stage='ingested'").fetchone():
        return
    batch=[]
    with gzip.open(DOWNLOAD/"event_assay_provenance.csv.gz","rt",newline="") as f:
        for r in csv.DictReader(f):
            chemistry=classify(r)
            batch.append((r["family"],r["kind"],r["source_file"],int(r["record_index"]),
                r["assay_iri"],numeric(r["epitope_iri"],"epitope"),r["original_name"],r["corrected_sequence"]
                if chemistry=="simple" else "",chemistry,r["modification"],r["source_iri"],r["parent_iri"],
                integer(r["start"]),integer(r["end"]),r["old_event_id"],r["qualitative"],r["original_sequence"]))
            if len(batch)==35000:
                with db:
                    db.executemany("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",batch)
                batch.clear()
    with db:
        db.executemany("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",batch)
        db.execute("INSERT INTO checkpoints VALUES ('ingested')")
    expected=json.loads((DOWNLOAD/"summary.json").read_text())
    assert db.execute("SELECT COUNT(*) FROM records").fetchone()[0] == sum(
        r.get("mhc_records",0)+r.get("tcell_records",0) for r in expected["families"])


def cache_records():
    api=json.loads((PRIOR/"iedb_records.json").read_text())
    enriched=set()
    for path in (PENDING/"cache").glob("*.json"):
        for row in json.loads(path.read_text()):
            eid=str(row["structure_id"])
            api[eid]=row
            if "e_modification" in row:
                enriched.add(eid)
    return api,enriched


def api_lookup(field, items, cache, api, *, fields, size=75):
    work=batches(items,size)
    failed=0
    def one(batch):
        text=fetch("https://query-api.iedb.org/epitope_search", {
            field:"in.("+",".join(batch)+")","select":fields,
        },cache,"json")
        return json.loads(text) if text else None
    returned=set()
    with ThreadPoolExecutor(5) as pool:
        for i,rows in enumerate(pool.map(one,work),1):
            if rows is None:failed+=1
            else:
                for row in rows:
                    eid=str(row["structure_id"])
                    api[eid]={**api.get(eid,{}),**row}
                    returned.add(eid)
            if i%50==0 or i==len(work):
                print("IEDB",field,i,"/",len(work),"failed",failed,flush=True)
    return dict(batches=len(work),failed=failed,returned=len(returned)),returned


FIELDS="structure_id,linear_sequence,e_modification,curated_source_antigens,tcell_ids,elution_ids,iedb_assay_ids"


def enrich(db,output):
    cache=output/"cache";cache.mkdir(exist_ok=True)
    api,enriched=cache_records()
    ids={r[0] for r in db.execute("SELECT DISTINCT eid FROM records WHERE chemistry='modified' AND eid<>''")}
    # T-cell exports omit the structure IRI. Link exact sequence candidates by assay ID.
    tcell={r[0] for r in db.execute("SELECT DISTINCT legacy FROM records WHERE eid='' AND kind='tcell'") if AA.fullmatch(r[0])}
    stats={}
    stats["missing_modified_ids"],_=api_lookup("structure_id",ids-api.keys(),cache,api,fields=FIELDS)
    stats["tcell_candidates"],_=api_lookup("linear_sequence",tcell,cache,api,fields=FIELDS)
    assay_ids=defaultdict(set)
    for eid,r in api.items():
        if r.get("linear_sequence") not in tcell:continue
        for key in ("tcell_ids","elution_ids","iedb_assay_ids"):
            for a in r.get(key) or []:
                assay_ids[str(a)].add(eid)
    if not db.execute("SELECT 1 FROM checkpoints WHERE stage='enriched'").fetchone():
        db.execute("CREATE INDEX IF NOT EXISTS rec_eid ON records(eid)")
        updates=[]
        for file,ord_,assay,legacy,chemistry in db.execute(
                "SELECT file,ord,assay,legacy,chemistry FROM records WHERE eid=''"):
            options={e for e in assay_ids[numeric(assay,"assay")] if api[e].get("linear_sequence")==legacy}
            if len(options)==1:
                eid=next(iter(options));r=api[eid]
                if chemistry=="simple" and r.get("e_modification"):
                    chemistry="modified"
                updates.append((eid,chemistry,file,ord_))
        with db:
            db.executemany("UPDATE records SET eid=?,chemistry=? WHERE file=? AND ord=?",updates)
            target_ids={r[0] for r in db.execute("SELECT DISTINCT eid FROM records WHERE chemistry='modified' AND eid<>''")}
            seqs=[(api[eid]["linear_sequence"],eid) for eid in target_ids if eid in api
                  and AA.fullmatch(api[eid].get("linear_sequence") or "")]
            db.executemany("UPDATE records SET seq=? WHERE eid=? AND chemistry='modified'",seqs)
            db.execute("INSERT INTO checkpoints VALUES ('enriched')")
    stats["modified_ids_requested"]=len(ids)
    stats["modified_ids_available"]=len(ids&api.keys())
    return api,stats


def key(f,seq,src,par,a,b):
    return f,seq,norm(src),norm(par),a,b


def prior_mappings():
    recovered={}
    with (PRIOR/"event_resolution.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            if r["confidence"]=="verified":
                recovered[key(r["family"],r["epitope"],r["source"],r["parent"],
                              int(r["original_start"]),int(r["original_end"]))]=(
                    int(r["corrected_start"]),int(r["corrected_end"]),r["parent_sequence_sha256"])
    return recovered


def verified_locus(f,seq,src,par,a,b,eid,api,refs,archive,recovered):
    parent=archive.get((ORG[f],norm(par)))
    if not parent or not seq:
        return None
    explicit=set()
    for item in api.get(eid,{}).get("curated_source_antigens") or []:
        s,t=item.get("starting_position"),item.get("ending_position")
        if (parent.version and item.get("iri")==f"UNIPROT:{parent.accession}.{parent.version}"
                or refs.get(item.get("accession"))==parent.sequence) and exact(parent.sequence,seq,s,t):
            explicit.add((s,t))
    prior=recovered.get(key(f,seq,src,par,a,b))
    if prior and prior[2]==parent.sha256 and exact(parent.sequence,seq,*prior[:2]):
        explicit.add(prior[:2])
    if len(explicit)==1:
        return norm(par),parent.sha256,*next(iter(explicit))
    if explicit:
        return None
    source=refs.get(acc(src))
    if source and exact(source,seq,a,b):
        if source==parent.sequence:
            return norm(par),parent.sha256,a,b
        interval=project_interval(source,parent.sequence,a,b,seq)
        if interval:
            return norm(par),parent.sha256,*interval
    return None


def create_indexes(db):
    db.executescript("""
      CREATE INDEX IF NOT EXISTS rec_chem_seq ON records(chemistry,seq);
      CREATE INDEX IF NOT EXISTS rec_eid ON records(eid);
      CREATE INDEX IF NOT EXISTS rec_event ON records(family,old_id);
    """)


def compare_entities(db,api,output,stats):
    modified=list(db.execute("""SELECT family,seq,src,par,a,b,eid,assay,file,ord,modification,old_id,name,qualitative
                  FROM records WHERE chemistry='modified'"""))
    targets={m[1] for m in modified if m[1]}
    # Level A also looks outside these archived assays. The catalogue lookup is separate from positive evidence.
    catalogue={}
    stats["catalogue_exact_sequences"],_=api_lookup("linear_sequence",targets,output/"cache",catalogue,
        fields="structure_id,linear_sequence,e_modification")
    cat_simple=defaultdict(set)
    for eid,r in catalogue.items():
        if r.get("linear_sequence") and r.get("e_modification") in (None,[],{},""):
            cat_simple[r["linear_sequence"]].add(eid)
    pairs=defaultdict(list)
    simple_ids=set()
    for row in db.execute("""SELECT family,seq,src,par,a,b,eid,assay FROM records
                        WHERE chemistry='simple' AND seq<>'' AND lower(qualitative) IN
                        ('positive','positive-low','positive-intermediate','positive-medium','positive-high')"""):
        if row[1] in targets:
            pairs[row[:2]].append(row)
            if row[6] and row[6] not in api:
                simple_ids.add(row[6])
    stats["simple_locus_reference_records"],_=api_lookup("structure_id",simple_ids,output/"cache",api,fields=FIELDS)
    archive=load_archived(IN/"data_intermediate")
    refs=observed_references(PRIOR,archive)
    recovered=prior_mappings()
    d_index=defaultdict(set)
    for (fam,seq),rows in pairs.items():
        for row in set(rows):
            f,s,src,par,a,b,eid,assay=row
            if not assay or api.get(eid,{}).get("e_modification"):
                continue
            locus=verified_locus(f,s,src,par,a,b,eid,api,refs,archive,recovered)
            if locus:
                d_index[f,s,locus].add((eid,assay))
    with (output/"modified_assays.csv").open("w",newline="") as h:
        w=csv.writer(h)
        w.writerow(("family","epitope_id","assay_iri","source_file","source_row_index","backbone","source_iri","parent_iri",
                    "original_start","original_end","original_name","qualitative","modification","catalogue_simple_epitope_ids",
                    "B_positive_simple","B_simple_ids","C_same_reference","C_simple_ids","D_verified_locus",
                    "D_simple_evidence","verified_parent_start","verified_parent_end"))
        per=defaultdict(lambda:defaultdict(set))
        global_e=defaultdict(set)
        earlier_rows=[r for r in json.loads((PENDING/"event_resolution.json").read_text())
                      if r["state"]=="modified_backbone_and_parent_verified"]
        earlier_scoped={(r["family"],r["old_event_id"]) for r in earlier_rows}
        earlier_loci={}
        for r in earlier_rows:
            for e in r["evidence"]:
                earlier_loci[r["family"],r["old_event_id"],e["epitope_id"],e["peptide"]]=(
                   norm(r["parent_iri"]),e["parent_sha256"],e["parent_start"],e["parent_end"])
        prior_support=defaultdict(set)
        for f,s,src,par,a,b,eid,assay,fi,ord_,mod,old,name,qualitative in modified:
            pool=pairs[f,s] if s else []
            # Independent assay IDs and exact reference identifiers (only URI scheme is normalized).
            p=[x for x in pool if assay and x[7] and x[7]!=assay
               and not api.get(x[6],{}).get("e_modification")]
            c=[x for x in p if (src and norm(src)==norm(x[2])) or (par and norm(par)==norm(x[3]))]
            previous=earlier_loci.get((f,old,eid,s))
            loc=verified_locus(f,s,src,par,a,b,eid,api,refs,archive,recovered)
            if loc and previous and loc!=previous:
                loc=None
            elif previous:
                loc=previous
            d=sorted((i,j) for i,j in d_index.get((f,s,loc),()) if assay and j!=assay) if loc else []
            A=cat_simple[s]-{eid} if s else set()
            flags={"modified_ids":bool(eid),"with_backbone":bool(s),"A":bool(A),"B":bool(p),"C":bool(c),"D":bool(d)}
            for name,on in flags.items():
                if on and eid:
                    per[f][name].add(eid);global_e[name].add(eid)
            if (f,old) in earlier_scoped:
                prior_support["all"].add((f,old))
                if p:prior_support["B"].add((f,old))
                if d:prior_support["D"].add((f,old))
            w.writerow((f,eid,assay,fi,ord_,s,src,par,a,b,name,qualitative,mod,"|".join(sorted(A)),int(bool(p)),
                        "|".join(sorted({x[6] for x in p if x[6]})),int(bool(c)),
                        "|".join(sorted({x[6] for x in c if x[6]})),int(bool(d)),json.dumps(d),
                        loc[2] if loc else "",loc[3] if loc else ""))
    stats["earlier_verified_modified_groups"]={k:len(v) for k,v in prior_support.items()}
    stats["equivalents_by_family"]={f:{k:len(v) for k,v in c.items()} for f,c in per.items()}
    stats["equivalents_global"]={k:len(v) for k,v in global_e.items()}
    stats["catalogue_missing_backbone_count"]=sum(not m[1] for m in modified)
    stats["distinct_modified_backbones"]=len(targets)
    modified_catalogue_ids=defaultdict(set)
    for m in modified:
        if m[1] and m[5]:modified_catalogue_ids[m[1]].add(m[5])
    stats["catalogue_shared_backbones"]=sum(bool(cat_simple[s]-modified_catalogue_ids[s]) for s in targets)
    stats["positive_archived_shared_backbones"]=len({s for (_,s),r in pairs.items()
                                                     if any(not api.get(x[6],{}).get("e_modification") for x in r)})
    return recovered


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    output=parser.parse_args().output
    if any(output.resolve().is_relative_to(p.resolve()) for p in (IN,DOWNLOAD,PENDING,PRIOR,DATASET)):
        parser.error("Output must be separate from the inputs")
    output.mkdir(parents=True,exist_ok=True)
    with output_lock(output), closing(database(output)) as db:
        ingest(db)
        print("INGEST",db.execute("SELECT chemistry,COUNT(*) FROM records GROUP BY chemistry").fetchall(),flush=True)
        api,stats=enrich(db,output)
        create_indexes(db)
        compare_entities(db,api,output,stats)
        write_json(output/"entities.json",stats)
        print("ENTITIES",stats["equivalents_global"],flush=True)


if __name__=="__main__":
    main()
