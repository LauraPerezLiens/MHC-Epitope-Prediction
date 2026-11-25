#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
attach_secondary_structure.py — Estructura secundaria Q3 sobre los fragmentos.

POR QUE UN SCRIPT NUEVO
-----------------------
`secondary_structure_prediction/add_secondary_structure.py` mapea al formato de
ventanas historico (`protein_group_id`, `group_id`, `25aa_seq`, `window_start`),
que el pipeline nuevo ya no produce. Este hace lo mismo sobre los fragmentos de
`build_fragments.py`.

EL PUNTO DE DISENO QUE IMPORTA
------------------------------
La estructura secundaria se predice sobre **la proteina completa** y luego se
**corta** por las coordenadas del fragmento. NO se predice sobre el fragmento
aislado, y la diferencia no es menor: ProteinUnet necesita contexto, y un
fragmento de 21 aa sacado de su proteina da una prediccion distinta —y peor—
que el mismo tramo predicho dentro de la proteina. Ademas cortar es gratis:
32.443 predicciones en lugar de 4,15 millones.

Esto es lo que ya hacia el pipeline historico y conviene conservarlo:
`predict_secondary_structure.py` corre sobre la proteina entera, con ventanas de
1.024 residuos y 200 de solape, promediando probabilidades antes de asignar
estados.

LO QUE SE VERIFICA, Y NO ES OPCIONAL
------------------------------------
Cortar por coordenadas solo es valido si la secuencia almacenada es la misma
sobre la que se calcularon esas coordenadas. Por eso, para cada fragmento:

  1. La cadena de estructura y la secuencia de la proteina miden lo mismo.
  2. El tramo `[frag_inicio-1 : frag_fin]` de la proteina es **identico** al
     fragmento. Si no lo es, la fila se marca `sequence_mismatch` y NO se le
     asigna estructura: asignarla seria alinear mal el dato estructural con el
     dato de secuencia, que es un error silencioso y grave.

Comprobado al construir: las 30.933 proteinas con estructura historica tienen
secuencia **identica** a la nuestra, cero discrepancias.

Los senuelos no llevan coordenadas (`frag_inicio` vacio), asi que se localizan
buscando el fragmento como subcadena exacta de su proteina. Si aparece mas de
una vez se usa la primera: el tramo de estructura puede diferir entre
ocurrencias, y eso se marca en `ss_ocurrencias`.

ESTADOS DE `ss_status`
----------------------
  `ok`                       estructura asignada y verificada
  `protein_not_found`        la proteina no tiene estructura calculada
  `protein_non_canonical`    la proteina trae B, U, X o Z: ProteinUnet la
                             rechaza. Son 190 proteinas, el 0,16 % de los
                             fragmentos. Esas filas se quedan sin estructura.
  `length_mismatch`          estructura y secuencia de distinta longitud
  `sequence_mismatch`        el tramo de la proteina no es el fragmento
  `not_located`              senuelo que no se encuentra en su proteina

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u data_pipeline/scripts/data_download/attach_secondary_structure.py \\
        --fragments data/fragments_w21 \\
        --structure data/secondary_structure_20261125/secondary_structure.parquet \\
        --out data/fragments_w21_ss
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CANONICAL_AA = set("ACDEFGHIKLMNPQRSTVWY")
Q3 = set("CHE")


def _git_commit(repo: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except Exception:
        return None


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def una_familia(df: pd.DataFrame, seqs: dict[str, str], ss: dict[str, str],
                w: int) -> tuple[pd.DataFrame, Counter]:
    est = Counter()
    out_ss: list[str | None] = []
    out_oc: list[int | None] = []
    out_st: list[str] = []

    for r in df.itertuples(index=False):
        acc = r.accession
        prot = seqs.get(acc)
        estr = ss.get(acc)
        if estr is None:
            # Distinguir "no se calculo" de "no se puede calcular".
            motivo = ("protein_non_canonical"
                      if prot is not None and not set(prot) <= CANONICAL_AA
                      else "protein_not_found")
            out_ss.append(None); out_oc.append(None); out_st.append(motivo)
            est[motivo] += 1
            continue
        if prot is None or len(prot) != len(estr):
            out_ss.append(None); out_oc.append(None); out_st.append("length_mismatch")
            est["length_mismatch"] += 1
            continue

        if pd.notna(r.frag_inicio):
            a = int(r.frag_inicio) - 1
            b = int(r.frag_fin)
            oc = 1
        else:
            a = prot.find(r.fragmento)
            if a < 0:
                out_ss.append(None); out_oc.append(None); out_st.append("not_located")
                est["not_located"] += 1
                continue
            b = a + w
            oc = prot.count(r.fragmento)

        if prot[a:b] != r.fragmento:
            out_ss.append(None); out_oc.append(None); out_st.append("sequence_mismatch")
            est["sequence_mismatch"] += 1
            continue
        tramo = estr[a:b]
        if len(tramo) != w or not set(tramo) <= Q3:
            out_ss.append(None); out_oc.append(None); out_st.append("length_mismatch")
            est["length_mismatch"] += 1
            continue
        out_ss.append(tramo); out_oc.append(oc); out_st.append("ok")
        est["ok"] += 1

    df = df.copy()
    df["secondary_structure"] = out_ss
    df["ss_ocurrencias"] = out_oc
    df["ss_status"] = out_st
    return df, est


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True, type=Path)
    ap.add_argument("--structure", required=True, type=Path,
                    help="parquet con columnas accession, secuencia, estructura")
    ap.add_argument("--proteins", type=Path,
                    default=Path("data/parent_proteins_20261125/parent_proteins.parquet"))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--format", choices=("parquet", "csv", "both"), default="both")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[3]
    args.out.mkdir(parents=True, exist_ok=True)

    pt = pd.read_parquet(args.proteins)
    seqs = dict(zip(pt.accession, pt.secuencia))
    st = pd.read_parquet(args.structure)
    ss = dict(zip(st.accession, st.estructura))
    print(f"proteinas: {len(seqs):,} | con estructura: {len(ss):,} "
          f"({100*len(ss)/len(seqs):.2f} %)")

    man = {
        "generado_por": "data_pipeline/scripts/data_download/attach_secondary_structure.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": _git_commit(repo),
        "fragmentos": str(args.fragments),
        "estructura": str(args.structure),
        "metodo": ("la estructura se predice sobre la proteina completa y se CORTA por "
                   "las coordenadas del fragmento; no se predice sobre el fragmento "
                   "aislado, que daria una prediccion distinta y peor por falta de "
                   "contexto"),
        "verificacion": ("para cada fila se comprueba que el tramo de la proteina es "
                         "identico al fragmento; si no, no se asigna estructura"),
        "familias": {},
    }
    tot: Counter = Counter()
    for f in sorted(args.fragments.rglob("fragments.parquet")):
        rel = f.relative_to(args.fragments).parent
        df = pd.read_parquet(f)
        w = int(df.ventana.iloc[0]) if len(df) else 0
        out, est = una_familia(df, seqs, ss, w)
        tot.update(est)
        d = args.out / rel
        d.mkdir(parents=True, exist_ok=True)
        salidas = {}
        if args.format in ("parquet", "both"):
            p = d / "fragments_ss.parquet"
            out.to_parquet(p, index=False, compression="zstd")
            salidas[str(p)] = {"sha256": _sha256(p), "bytes": p.stat().st_size}
        if args.format in ("csv", "both"):
            p = d / "fragments_ss.csv"
            out.to_csv(p, index=False)
            salidas[str(p)] = {"sha256": _sha256(p), "bytes": p.stat().st_size}
        man["familias"][str(rel)] = {"filas": len(out), "ventana": w,
                                     "estados": dict(est), "salidas": salidas}
        ok = est.get("ok", 0)
        print(f"[{str(rel):22s}] {len(out):9,} filas | ok {ok:9,} "
              f"({100*ok/len(out) if len(out) else 0:6.2f} %) | "
              + " ".join(f"{k} {v:,}" for k, v in est.items() if k != "ok"))

    n = sum(tot.values())
    man["estados_totales"] = dict(tot)
    man["cobertura_pct"] = round(100.0 * tot.get("ok", 0) / n, 4) if n else 0.0
    (args.out / "manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(f"\nTOTAL {n:,} filas | con estructura {tot.get('ok',0):,} "
          f"({man['cobertura_pct']:.3f} %)")
    for k, v in sorted(tot.items(), key=lambda kv: -kv[1]):
        if k != "ok":
            print(f"  {k:24s} {v:9,}  ({100*v/n:.3f} %)")
    print(f"Manifiesto: {args.out/'manifest.json'}\nDONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
