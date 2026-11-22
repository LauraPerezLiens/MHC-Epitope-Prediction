"""Measure historical support on real family rows and a sequence-level counterfactual."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import gzip
import json
from pathlib import Path
import sqlite3

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from data_pipeline.scripts.global_epitope_labels.build import FAMILIES, ROOT, row_path, write_json
from data_pipeline.scripts.iedb_download_audit.audit import event_id, windows
from data_pipeline.scripts.iedb_modified_audit.audit import DATASET, IN, PENDING, PRIOR, key, prior_mappings
from data_pipeline.scripts.iedb_pending_audit.audit import exact, norm
from data_pipeline.scripts.rebuild_iedb.rebuild import load_archived

SIMPLE, MODIFIED, UNKNOWN = 1, 2, 4


def row_filters(path, cols, positive=False, seqs=None):
    for batch in pq.ParquetFile(path).iter_batches(batch_size=100_000,columns=cols):
        mask=pc.equal(batch["contains_epitope"],1) if positive else None
        if seqs is not None:
            found=pc.is_in(batch["25aa_seq"],value_set=seqs)
            mask=found if mask is None else pc.and_(mask,found)
        if mask is not None:
            batch=pa.Table.from_batches([batch]).filter(mask)
        yield zip(*(v.to_pylist() for v in batch.columns))


def group_masks(db,family):
    rows=db.execute("""SELECT old_id,
      MAX(chemistry='simple'),MAX(chemistry='modified'),MAX(chemistry='uncertain')
      FROM records WHERE family=? AND old_id<>'' AND lower(qualitative) IN
      ('positive','positive-low','positive-intermediate','positive-medium','positive-high')
      GROUP BY old_id""",(family,))
    return {eid:int(a)*SIMPLE+int(b)*MODIFIED+int(c)*UNKNOWN for eid,a,b,c in rows}


def legacy_key(event):
    return (event["epitope__name_canonical"],event["epitope__starting_position"],event["epitope__ending_position"],
            event["source_id"],event["parent_id"])


def historical(db, prior):
    config=json.loads((DATASET/"config.json").read_text())
    sources={s["mhc_family"]:s for s in config["sources"]}
    refs=load_archived(IN/"data_intermediate")
    sequence_flags={}
    family_stats={}
    recovered_simple=set()
    for org,mhc,f in FAMILIES:
        flags=group_masks(db,f)
        # Per-protein matching by selected peptide and containment. Using event intervals
        # preserves independent evidence if several assays/entities have the same local locus.
        eligible=defaultdict(lambda:defaultdict(list))
        old=IN/"data_raw"/org/mhc/f/"merged_unique_events.csv"
        with old.open(newline="") as handle:
            for r in csv.DictReader(handle):
                peptide,a,b,src,par=legacy_key(r)
                u=norm(par)
                ref=refs.get((org,u))
                a,b=int(a),int(b)
                mask=flags.get(event_id(legacy_key(r)),UNKNOWN)
                if ref and len(peptide)<=25 and exact(ref.sequence,peptide,a,b):
                    eligible[u][peptide].append((a,b,mask))
                candidate=prior.get(key(f,peptide,src,par,a,b))
                if (mask&SIMPLE and ref and candidate and ref.sha256==candidate[2]
                        and exact(ref.sequence,peptide,*candidate[:2])):
                    for start in windows(candidate[0],len(peptide),len(ref.sequence)):
                        recovered_simple.add(ref.sequence[start-1:start+24])
        positions={}
        counts=Counter()
        pos_columns=["protein_url","window_start","selected_epitope","25aa_seq","contains_epitope"]
        for batch in row_filters(row_path(DATASET,sources[f]),pos_columns,positive=True):
            for parent,start,peptide,sequence,_ in batch:
                u=norm(parent); start=int(start)
                flags_here=0
                for a,b,chem in eligible.get(u,{}).get(peptide,()):
                    if start<=a<=b<start+25:
                        flags_here|=chem
                flags_here=flags_here or UNKNOWN
                if flags_here==UNKNOWN:counts["positive_rows_with_unresolved_chemical_support"]+=1
                pair=u,start
                positions[pair]=positions.get(pair,0)|flags_here
                sequence_flags[sequence]=sequence_flags.get(sequence,0)|flags_here
                counts["historical_positive_rows"]+=1
        counts["historical_positive_positions"]=len(positions)
        for mask in positions.values():
            if mask&SIMPLE:counts["positions_with_simple"]+=1
            if mask&MODIFIED:counts["positions_with_modified"]+=1
            if mask&3==3:counts["positions_with_both"]+=1
            if mask==MODIFIED:counts["positions_only_modified"]+=1
            if mask&UNKNOWN and not mask&SIMPLE:counts["positions_ambiguous_without_simple"]+=1
        family_stats[f]=dict(counts)
        print("FAMILY_POSITIONS",f,len(positions),flush=True)
    return sequence_flags,family_stats,recovered_simple,sources


def training_footprint(output, losses, ambiguous, sources):
    all_flags={s:"modified_only" for s in losses}
    all_flags.update({s:"ambiguous" for s in ambiguous})
    values=pa.array(sorted(all_flags),type=pa.string())
    cols=["25aa_seq","contains_epitope","group_id","source_row_index"]
    counts=defaultdict(Counter)
    # Provenance of affected rows proves original group membership. Expansion is estimated
    # from the recorded 26-per-group layout, rather than assuming a measured split count.
    with gzip.open(output/"affected_original_groups.csv.gz","wt",newline="") as fh:
        w=csv.writer(fh)
        w.writerow(("family","source_file","source_row_index","group_id","sequence","original_family_label","reason"))
        for f,source in sources.items():
            for batch in row_filters(row_path(DATASET,source),cols,seqs=values):
                for seq,y,gid,row in batch:
                    category=all_flags[seq]
                    counts[f][category]+=1
                    counts[f]["original_family_positive_"+category]+=y
                    counts[f]["group_id_follows_original_order"]+=int(int(gid)==row+1)
                    w.writerow((f,source["file"],row,gid,seq,y,category))
            print("TRAINING",f,dict(counts[f]),flush=True)
    return {f:dict(c) for f,c in counts.items()}


def duplicates(db):
    def query(sql):
        names=("records","unique_iedb_epitopes","family_events")
        return dict(zip(names,db.execute(sql).fetchone()))
    stats={}
    stats["multiple_assays_same_entity"]=query("""WITH g AS (
      SELECT family,old_id,eid FROM records NOT INDEXED WHERE old_id<>'' AND eid<>'' AND assay<>''
      GROUP BY family,old_id,eid HAVING COUNT(DISTINCT assay)>1)
      SELECT count(*),count(DISTINCT r.eid),count(DISTINCT r.family||':'||r.old_id)
      FROM g CROSS JOIN records r INDEXED BY rec_event ON r.family=g.family AND r.old_id=g.old_id AND r.eid=g.eid""")
    stats["different_modified_entities_same_event"]=query("""WITH g AS (
      SELECT family,old_id FROM records NOT INDEXED WHERE old_id<>'' AND eid<>'' AND chemistry='modified'
      GROUP BY family,old_id HAVING COUNT(DISTINCT eid)>1)
      SELECT count(*),count(DISTINCT r.eid),count(DISTINCT r.family||':'||r.old_id)
      FROM g CROSS JOIN records r INDEXED BY rec_event ON r.family=g.family AND r.old_id=g.old_id WHERE r.chemistry='modified'""")
    stats["mixed_simple_and_modified_different_entities"]=query("""WITH g AS (
      SELECT family,old_id FROM records NOT INDEXED WHERE old_id<>'' AND eid<>'' AND chemistry IN ('simple','modified')
      GROUP BY family,old_id HAVING min(chemistry)<>max(chemistry) AND min(eid)<>max(eid))
      SELECT count(*),count(DISTINCT r.eid),count(DISTINCT r.family||':'||r.old_id)
      FROM g CROSS JOIN records r INDEXED BY rec_event ON r.family=g.family AND r.old_id=g.old_id
      WHERE r.chemistry IN ('simple','modified')""")
    stats["same_entity_different_reference_or_coordinate"]=query("""WITH g AS (
      SELECT family,eid FROM records NOT INDEXED WHERE old_id<>'' AND eid<>''
      GROUP BY family,eid HAVING COUNT(DISTINCT src||'|'||par||'|'||a||'|'||b)>1)
      SELECT count(*),count(DISTINCT r.eid),count(DISTINCT r.family||':'||r.old_id)
      FROM g CROSS JOIN records r INDEXED BY rec_eid ON r.family=g.family AND r.eid=g.eid WHERE r.old_id<>''""")
    stats["uncertain_chemistry_or_missing_structure_id_in_event"]=query(f"""WITH g AS (
      SELECT family,old_id FROM records NOT INDEXED WHERE old_id<>''
      GROUP BY family,old_id HAVING COUNT(*)>1 AND MAX(eid='' OR chemistry='uncertain')=1)
      SELECT count(*),count(DISTINCT NULLIF(r.eid,'')),count(DISTINCT r.family||':'||r.old_id)
      FROM g CROSS JOIN records r INDEXED BY rec_event ON r.family=g.family AND r.old_id=g.old_id""")
    print("DUPLICATES", {k:v["family_events"] for k,v in stats.items()}, flush=True)
    return stats


def run(output):
    with closing(sqlite3.connect((output/"audit_work.sqlite").resolve().as_uri()+"?mode=ro",uri=True)) as db:
        db.execute("PRAGMA cache_size=-262144")
        db.execute("PRAGMA temp_store=MEMORY")
        dup=duplicates(db)
        prior=prior_mappings()
        sequence_flags, family, recovered, sources=historical(db,prior)
        chemical_counts=[dict(chemistry=k,records=n,identified_structures=i,distinct_backbones=s,
                              unresolved_structure_records=u,missing_backbone_records=b)
            for k,n,i,s,u,b in db.execute("""SELECT chemistry,COUNT(*),COUNT(DISTINCT NULLIF(eid,'')),
                 COUNT(DISTINCT NULLIF(seq,'')),SUM(eid=''),SUM(seq='') FROM records GROUP BY chemistry""")]
        modifications=list(db.execute("""SELECT modification, COUNT(*), COUNT(DISTINCT NULLIF(eid,'')) FROM records
                                              WHERE chemistry='modified' GROUP BY modification ORDER BY COUNT(*) DESC"""))
    expected=json.loads((DATASET/"summary.json").read_text())
    assert len(sequence_flags)==expected["global_positive_sequences"]
    assert sum(v["historical_positive_rows"] for v in family.values())==expected["original_positive_rows"]
    simple_legacy={s for s,m in sequence_flags.items() if m&SIMPLE}
    carry=simple_legacy | (recovered & sequence_flags.keys())
    losses={s for s,m in sequence_flags.items() if s not in carry and m==MODIFIED}
    ambiguous=sequence_flags.keys()-carry-losses
    assert len(carry)+len(losses)+len(ambiguous)==len(sequence_flags)
    with (PENDING/"global_scenarios.csv").open(newline="") as f:
        prior_loss={r["deterministic_sequence"] for r in csv.DictReader(f) if r["strict_plain_sensitivity"]=="1_to_0"}
    assert len(prior_loss)==167119
    with (output/"sequence_loss.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(("sequence","status","in_prior_167119"))
        for s in sorted(losses|ambiguous):
            w.writerow((s,"modified_only" if s in losses else "ambiguous",int(s in prior_loss)))
    with (output/"modifications.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(("archived_modification_annotation","records","known_epitope_ids"))
        w.writerows(modifications)
    footprint=training_footprint(output,losses,ambiguous,sources)
    tallies=sum(map(Counter,footprint.values()),Counter())
    assert tallies["group_id_follows_original_order"]==tallies["modified_only"]+tallies["ambiguous"]
    manifest=json.loads((ROOT/"data/data_input_nn_shuffled_concatenate/reorder_manifest.json").read_text())
    assert manifest["rows"]==expected["original_rows"]*26
    write_json(output/"impact.json",dict(family=family,duplicates=dup,chemistry=chemical_counts,
        historical_global_positive=len(sequence_flags),simple_legacy=len(simple_legacy),
        recovered_simple_among_current_positive_without_legacy_simple=len(carry-simple_legacy),
        retained_global_positive=len(carry),modified_only=len(losses),ambiguous=len(ambiguous),
        previous_167119=dict(still_modified_only=len(prior_loss&losses),ambiguous=len(prior_loss&ambiguous),
                             retained_simple=len(prior_loss&carry),retained_legacy_simple=len(prior_loss&simple_legacy),
                             retained_recovered_simple=len(prior_loss&(carry-simple_legacy))),
        footprint=footprint,footprint_total=dict(tallies),original_rows=expected["original_rows"],
        original_global_positive_rows=expected["global_positive_rows"],original_unique_sequences=expected["unique_sequences"],
        archive_blosum_rows=manifest["rows"]))
    print("IMPACT",len(carry),len(losses),len(ambiguous),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    run(p.parse_args().output)


if __name__=="__main__":
    main()
