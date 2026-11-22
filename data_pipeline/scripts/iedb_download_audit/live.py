"""Optional present-day IEDB filter counts and a bounded pagination check."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

import requests

from data_pipeline.scripts.global_epitope_labels.build import FAMILIES, write_json

ENDPOINT = "https://query-api.iedb.org"
SPECIES = {"human": "Homo sapiens", "mouse": "Mus musculus"}
QUAL = "assay__qualitative_measurement"
POS_EXPR = "in.(Positive,Positive-Low,Positive-Intermediate,Positive-Medium,Positive-High)"
ORDER = ("assay_id__iedb_iri,epitope__name,epitope__source_molecule_iri,"
         "epitope__molecule_parent_iri,epitope__starting_position,epitope__ending_position")


def params_for(org, mhc, family):
    return {
        "epitope__object_type": "eq.Linear peptide",
        QUAL: "ilike.*Positive*",
        "mhc_restriction__class": f"eq.{mhc.removeprefix('mhc-')}",
        "host__name": f"ilike.*{SPECIES[org]}*",
        "epitope__source_organism": f"ilike.*{SPECIES[org]}*",
        "mhc_restriction__name": f"ilike.*{family}*",
    }


def get(kind, params, count=False):
    for attempt in range(2):
        try:
            response = requests.get(f"{ENDPOINT}/{kind}_export", params=params,
                                    headers={"Prefer": "count=exact"} if count else {}, timeout=28)
            response.raise_for_status()
            return response.json(), response.headers.get("Content-Range", "")
        except requests.RequestException:
            if attempt == 1:
                raise
            time.sleep(2)


def exact_count(kind, params):
    _, span = get(kind, {**params, "select": "assay_id__iedb_iri", "limit": 1}, count=True)
    total = re.search(r"/(\d+)$", span)
    if not total:
        raise ValueError(f"No exact count returned: {span}")
    return int(total[1])


def check_pages(fetch, total, page_size):
    output = []
    hashes = set()
    pages = []
    while len(output) < total:
        offset = len(output)
        page, span = fetch(offset, page_size)
        match = re.fullmatch(r"(\d+)-(\d+)/(\d+|\*)", span)
        if not page or not match or (int(match[1]), int(match[2])) != (offset, offset + len(page) - 1):
            raise ValueError(f"Unexpected pagination at {offset}: {span!r} ({len(page)} rows)")
        if match[3] != "*" and int(match[3]) != total:
            raise ValueError("Count changed in the middle of pagination")
        if len(page) > page_size or offset + len(page) > total:
            raise ValueError("Page overran the exact count")
        for row in page:
            key = json.dumps(row, sort_keys=True, separators=(",", ":"))
            if key in hashes:
                raise ValueError(f"Repeated payload at offset {offset}; seek a unique row key")
            hashes.add(key)
        output.extend(page)
        pages.append({"offset": offset, "records": len(page), "content_range": span})
    return output, pages


def variants(org, family, params):
    yield "legacy", params
    yield "exact_qualitative_only", {**params, QUAL: POS_EXPR}
    if org == "mouse":
        alias = family.replace("H2-", "H-2-")
        v = {k: value for k, value in params.items() if k != "mhc_restriction__name"}
        v["or"] = f"(mhc_restriction__name.ilike.*{family}*,mhc_restriction__name.ilike.*{alias}*)"
        yield "mouse_family_alias_only", v


def run(output, broad=False):
    started = datetime.now(timezone.utc).isoformat()
    out_file = output / "live_counts.json"
    if out_file.exists():
        raise ValueError("Use a separate name for another live snapshot")
    tasks = [(family,kind,label,variant) for org,mhc,family in FAMILIES for kind in ("mhc","tcell")
             for label,variant in variants(org,family,params_for(org,mhc,family))] if broad else []
    if not broad:
        tasks = [("HLA-A", "mhc", label, {**variant, "assay_id__iedb_iri":
                  "eq.http://www.iedb.org/assay/699"})
                 for label,variant in variants("human","HLA-A",params_for("human","mhc-I","HLA-A"))]
    def measure(task):
        family, kind, label, variant = task
        r = dict(family=family, kind=kind, scenario=label, params=variant,
                 timestamp=datetime.now(timezone.utc).isoformat())
        try:
            r.update(count=exact_count(kind,variant),status="ok")
        except (requests.RequestException, ValueError) as exc:
            r.update(count=None,status=str(exc))
        return r
    with ThreadPoolExecutor(2) as pool:
        counts = []
        for row in pool.map(measure,tasks):
            counts.append(row)
            print(row["family"],row["kind"],row["scenario"],row["count"],flush=True)
    tests = []
    # Small indexed query against the same PostgREST service, with explicit PK ordering.
    probe = {"structure_id":"in.(4966,16587,33295,424582,42961,509391,62155,74794,75980)",
             "select":"structure_id,linear_sequence","order":"structure_id"}
    r = {"endpoint":"epitope_search", "page_size":3, "query":probe}
    try:
        def indexed(params, count=False):
            response=requests.get(f"{ENDPOINT}/epitope_search",params=params, timeout=15,
                                  headers={"Prefer":"count=exact"} if count else {})
            response.raise_for_status()
            return response.json(), response.headers.get("Content-Range","")
        _, span=indexed({**probe,"limit":1},count=True)
        total=int(span.rsplit("/",1)[-1])
        data,pages=check_pages(lambda offset,limit:indexed({**probe,"offset":offset,"limit":limit}),total,3)
        _, checked_span=indexed({**probe,"limit":1},count=True)
        if checked_span.rsplit("/",1)[-1] != str(total):
            raise ValueError("Exact count changed during pagination")
        r.update(status="validated",expected=total,pages=pages,downloaded=len(data))
        write_json(output/"live_pagination_probe.json",data)
    except (requests.RequestException,ValueError) as exc:
        r["status"]=str(exc)
    tests.append(r)
    write_json(out_file,dict(started_utc=started,finished_utc=datetime.now(timezone.utc).isoformat(),
                             counts=counts,pagination=tests))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--broad",action="store_true",help="Try count-only queries for all live family filters.")
    a=p.parse_args()
    run(a.output,a.broad)

if __name__=="__main__":
    main()
