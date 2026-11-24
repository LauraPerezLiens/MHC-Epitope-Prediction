#!/usr/bin/env python3
"""Perfila un arbol de descarga IEDB: positivos, negativos, organismos,
alelos, peptidos, tipo de ensayo, evidencia y publicaciones."""
import collections
import glob
import json
import os
import re
import sys

import pandas as pd

COLS = ["assay__qualitative_measurement", "epitope__source_organism", "host__name",
        "mhc_restriction__name", "mhc_restriction__evidence_code", "assay__method",
        "epitope__name", "epitope__molecule_parent", "reference__pmid",
        "assay__quantitative_measurement", "assay__units"]

SELF = re.compile(r"Mus musculus|Homo sapiens", re.I)


def assay_class(m):
    if not isinstance(m, str) or not m.strip():
        return "unknown"
    t = m.lower()
    if any(k in t for k in ("t cell", "elispot", "ics", "elisa", "chromium", "multimer",
                            "tetramer", "thymidine", "brdu", "in vivo assay",
                            "in vitro assay", "biological activity", "bioassay",
                            "proliferation", "cytotox", "interferon", "cytokine")):
        return "tcell_funcional"
    if any(k in t for k in ("mass spectrometry", "coelution", "edman")):
        return "elucion_ms"
    if "crystallograph" in t or "nmr" in t:
        return "estructural"
    if any(k in t for k in ("competitive", "direct", "binding", "purified mhc",
                            "cellular mhc", "plasmon", "spr", "fluorescence",
                            "radioactivity")):
        return "union"
    return "otro"


def evidence_class(c):
    if not isinstance(c, str) or not c.strip():
        return "sin_codigo"
    t = c.lower()
    if "single allele present" in t:
        return "directa"
    if "elution with mhc specific antibody" in t:
        return "anticuerpo"
    if "prediction" in t:
        return "PREDICCION"
    if "inferred" in t:
        return "inferida_motivo"
    if "binding assay" in t:
        return "ensayo_union"
    if "t cell assay" in t:
        return "ensayo_tcell"
    if "cited reference" in t:
        return "citada"
    if "not determined" in t:
        return "no_determinada"
    return "otra"


def perfil(root, etiqueta):
    fams = sorted("/".join(p.split("/")[-3:]) for p in glob.glob(root + "/*/*/*")
                  if os.path.isdir(p))
    agg = collections.Counter()
    organismos = collections.Counter()
    hosts = collections.Counter()
    alelos = set()
    peptidos = set()
    proteinas = set()
    pmids = set()
    clases = collections.Counter()
    evid = collections.Counter()
    longs = collections.Counter()
    por_familia = {}

    for fam in fams:
        c = collections.Counter()
        for ex in ("mhc", "tcell"):
            p = os.path.join(root, fam, "%s_export_full.csv" % ex)
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                continue
            d = pd.read_csv(p, usecols=lambda x: x in COLS, dtype=str, low_memory=False)
            n = len(d)
            c["filas"] += n
            c["filas_" + ex] += n

            q = d.get("assay__qualitative_measurement", pd.Series(dtype=str)).fillna("")
            c["positivas"] += int(q.str.startswith("Positive").sum())
            c["negativas"] += int(q.str.startswith("Negative").sum())
            for v, k in q.value_counts().items():
                agg["tier::" + (v or "<vacio>")] += int(k)

            o = d.get("epitope__source_organism", pd.Series(dtype=str)).fillna("")
            c["propio"] += int(o.str.contains(SELF).sum())
            c["sin_organismo"] += int((o == "").sum())
            organismos.update(o[o != ""].value_counts().to_dict())

            h = d.get("host__name", pd.Series(dtype=str)).fillna("")
            hosts.update(h[h != ""].value_counts().to_dict())

            a = d.get("mhc_restriction__name", pd.Series(dtype=str)).dropna()
            alelos.update(a.unique())

            pep = d.get("epitope__name", pd.Series(dtype=str)).dropna().str.strip().str.upper()
            peptidos.update(pep.unique())
            longs.update(pep.str.len().value_counts().to_dict())

            pr = d.get("epitope__molecule_parent", pd.Series(dtype=str)).dropna()
            proteinas.update(pr.unique())
            c["sin_accession"] += int(d.get("epitope__molecule_parent",
                                            pd.Series(dtype=str)).isna().sum())

            pm = d.get("reference__pmid", pd.Series(dtype=str)).dropna()
            pmids.update(pm.unique())

            clases.update(d.get("assay__method", pd.Series(dtype=str)).map(assay_class)
                          .value_counts().to_dict())
            evid.update(d.get("mhc_restriction__evidence_code", pd.Series(dtype=str))
                        .map(evidence_class).value_counts().to_dict())

            u = d.get("assay__units", pd.Series(dtype=str)).fillna("")
            c["con_nM"] += int((u.str.strip() == "nM").sum())

        por_familia[fam] = dict(c)
        agg.update(c)

    return {
        "etiqueta": etiqueta,
        "familias": len(fams),
        "totales": dict(agg),
        "por_familia": por_familia,
        "alelos_distintos": len(alelos),
        "peptidos_unicos": len(peptidos),
        "proteinas_unicas": len(proteinas),
        "pmids_distintos": len(pmids),
        "organismos_distintos": len(organismos),
        "hosts": dict(hosts.most_common(10)),
        "organismos_top": dict(organismos.most_common(15)),
        "clase_ensayo": dict(clases),
        "clase_evidencia": dict(evid),
        "longitudes": {str(k): v for k, v in sorted(longs.items())},
    }


if __name__ == "__main__":
    out = perfil(sys.argv[1], sys.argv[2])
    print(json.dumps(out, ensure_ascii=False, indent=1))
