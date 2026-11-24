#!/usr/bin/env python3
"""Re-descarga IEDB con los MISMOS filtros que build_iedb_dataset.py,
pero con paginacion por clave (assay_id) en vez de offset, y manifiesto."""
import csv, json, logging, sys, time
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = {"mhc": "https://query-api.iedb.org/mhc_export",
        "tcell": "https://query-api.iedb.org/tcell_export"}
OUT = Path("/data/nap/lperez_nn/data/data_raw_20261124")
LIMIT = 10000
HAPS = [("mouse", "mhc-I", "I", ["H2-K", "H2-D", "H2-L"]),
        ("mouse", "mhc-II", "II", ["H2-IA", "H2-IE"]),
        ("human", "mhc-I", "I", ["HLA-A", "HLA-B", "HLA-C"]),
        ("human", "mhc-II", "II", ["HLA-DR", "HLA-DQ", "HLA-DP"])]
SPQ = {"mouse": "Mus musculus", "human": "Homo sapiens"}

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s %(levelname)s: %(message)s")


def make_session():
    s = requests.Session()
    r = Retry(total=5, connect=5, read=5, backoff_factor=2,
              status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=r))
    return s


S = make_session()


def fetch_all(url, params):
    """Paginacion keyset sobre assay_id (unico y estable)."""
    rows, last, page = [], None, 0
    while True:
        p = dict(params)
        p["limit"] = LIMIT
        p["order"] = "assay_id.asc"
        if last is not None:
            p["assay_id"] = "gt.%d" % last
        t0 = time.time()
        resp = S.get(url, params=p, timeout=600)
        resp.raise_for_status()
        data = resp.json()
        logging.info("  page=%d n=%d %.1fs", page, len(data), time.time() - t0)
        if not data:
            break
        rows += data
        new_last = max(r["assay_id"] for r in data)
        if new_last == last:
            break
        last = new_last
        page += 1
        if len(data) < LIMIT:
            break
    return rows


def write_csv(rows, path):
    if not rows:
        path.write_text("", encoding="utf-8")
        return 0
    keys = sorted({k for r in rows for k in r})
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


manifest = {"downloaded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pagination": "keyset on assay_id.asc", "limit": LIMIT,
            "filters": "identical to build_iedb_dataset.py", "queries": {}}

for species, cls, num, fams in HAPS:
    for fam in fams:
        d = OUT / species / cls / fam
        d.mkdir(parents=True, exist_ok=True)
        entry = {}
        for mode in ("mhc", "tcell"):
            params = {"epitope__object_type": "eq.Linear peptide",
                      "assay__qualitative_measurement": "ilike.*Positive*",
                      "mhc_restriction__class": "eq.%s" % num,
                      "host__name": "ilike.*%s*" % SPQ[species],
                      "mhc_restriction__name": "ilike.*%s*" % fam,
                      "epitope__source_organism": "ilike.*%s*" % SPQ[species]}
            logging.info("=== %s %s %s %s ===", species, cls, fam, mode)
            rows = fetch_all(BASE[mode], params)
            n = write_csv(rows, d / ("%s_export_full.csv" % mode))
            entry[mode] = n
            logging.info("  -> %s_export_full.csv n=%d", mode, n)
        manifest["queries"]["%s/%s/%s" % (species, cls, fam)] = entry
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))

logging.info("DONE")
