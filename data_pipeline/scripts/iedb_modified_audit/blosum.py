"""Verify a stratified sample of affected original addresses in archived BLOSUM metadata."""

import argparse
import csv
from functools import lru_cache
import gzip
import json
from pathlib import Path

from data_pipeline.scripts.check_sampled_modalities import source_array
from data_pipeline.scripts.global_epitope_labels.build import ROOT


def run(output):
    manifest=json.loads((ROOT/"data/data_input_nn_shuffled_concatenate/reorder_manifest.json").read_text())
    sources={Path(x["master_index"]).parts[-3]:x for x in manifest["sources"]}
    sample={}
    with gzip.open(output/"affected_original_groups.csv.gz","rt",newline="") as f:
        for row in csv.DictReader(f):
            sample.setdefault((row["family"],row["reason"]),row)

    @lru_cache(maxsize=16)
    def vector(root,chunk,field):
        return source_array(root/f"chunk_{chunk:06d}_{field}.npy")

    items=[]
    for (family,status),row in sorted(sample.items()):
        group=int(row["group_id"]); label=int(row["original_family_label"])
        source=sources[family];root=Path(source["master_index"]).parent
        found=0; first_chunk,first_row=divmod((group-1)*26,manifest["chunk_rows"])
        for absolute in range((group-1)*26,group*26):
            chunk,idx=divmod(absolute,manifest["chunk_rows"])
            if vector(root,chunk,"group_id")[idx]!=group or vector(root,chunk,"y")[idx]!=label:
                raise ValueError(f"Archive row does not belong to group {family}/{group}")
            found+=1
        items.append(dict(family=family,reason=status,source_group_id=group,
                          source_dataset_id=source["id"],original_source_row=row["source_row_index"],
                          augmented_start_chunk=first_chunk,augmented_start_row=first_row,
                          original_family_label=label,archive_rows_verified=found))
    if items:
        with (output/"blosum_address_sample.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
    print("BLOSUM_SAMPLE",len(items),sum(x["archive_rows_verified"] for x in items),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    run(parser.parse_args().output)
