#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetch_parent_proteins.py — Secuencias de las proteinas madre de los epitopos.

POR QUE HACE FALTA
------------------
El dataset limpio guarda `epitope__molecule_parent_iri`, que lleva el accession
de UniProt, pero no la secuencia. Sin la secuencia no se puede:

  * situar el epitopo en su proteina y recortar una ventana a su alrededor;
  * generar senuelos del mismo proteoma, que es la unica fuente de negativos
    disponible, porque la elucion no produce negativos experimentales.

Las secuencias historicas (`data/used_data/data_intermediate.tar.zst`,
ficheros `{human,mouse}_parent_protein_fasta.csv`) cubren el 95,5 % de los
accessions del dataset nuevo. Este script descarga el resto y consolida todo en
un unico almacen con procedencia.

QUE HACE
--------
1. Lee los accessions que el dataset limpio necesita.
2. Toma del almacen historico los que ya estan.
3. Descarga de UniProt los que falten, por lotes, con la API REST oficial.
4. Escribe un Parquet y un CSV con una fila por proteina, y un manifiesto con
   la fecha UTC, el commit, los recuentos y el SHA-256 de la salida.

Es reanudable: lo ya descargado no se vuelve a pedir salvo `--force`.

NOTA SOBRE LAS AUSENCIAS
------------------------
Un accession puede no resolverse porque UniProt lo haya retirado o fusionado.
Eso no es un fallo del script: se anota en el manifiesto y esas filas del
dataset no podran convertirse en ventanas. Se registran para que el recuento
cuadre y nadie las busque dos veces.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u data_pipeline/scripts/data_download/fetch_parent_proteins.py \\
        --clean data/data_raw_full_20261124_clean \\
        --historico data/_fa/data_intermediate \\
        --out data/parent_proteins_20261125
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

UNIPROT_STREAM = "https://rest.uniprot.org/uniprotkb/accessions"
LOTE = 100          # accessions por peticion; UniProt admite mas, 100 es conservador
PAUSA = 0.34        # ~3 peticiones por segundo, para no castigar el servicio
REINTENTOS = 4
# Cliente generico a proposito: no se envia ningun dato personal del usuario.
UA = "nap-cnb-pipeline/1.0 (academic research; parent protein retrieval)"


def _git_commit(repo: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        h = r.stdout.strip()
        if not h:
            return None
        # §19 pide el commit Y el estado del repositorio: devolver el hash a
        # secas con el arbol modificado senala un codigo que no es el que se
        # ejecuto, y quien reproduzca desde ese commit no vera los cambios.
        s = subprocess.run(["git", "-C", str(repo), "status", "--porcelain",
                            "--untracked-files=no"],
                           capture_output=True, text=True, timeout=10)
        return h + ("-sucio" if s.stdout.strip() else "")
    except Exception:
        return None


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def accessions_necesarios(clean: Path) -> dict[str, set[str]]:
    """Accessions que el dataset limpio necesita, separados por especie."""
    need: dict[str, set[str]] = {"human": set(), "mouse": set()}
    for f in sorted(clean.rglob("mhc_export_full_slim.parquet")):
        d = pd.read_parquet(f, columns=["epitope__molecule_parent_iri"])
        sp = "human" if "/human/" in str(f) else "mouse"
        ids = d["epitope__molecule_parent_iri"].dropna().map(
            lambda s: s.rsplit("/", 1)[-1]
        )
        need[sp].update(ids)
    return need


def del_historico(hist: Path, especie: str) -> dict[str, str]:
    """Secuencias ya disponibles en el almacen historico, por accession."""
    f = hist / f"{especie}_parent_protein_fasta.csv"
    if not f.exists():
        return {}
    t = pd.read_csv(f, dtype=str)
    out: dict[str, str] = {}
    for _, r in t.iterrows():
        seq = secuencia_de_fasta(r.get("fasta"))
        if not seq:
            continue
        for col in ("id_base", "resolved_id", "id_full"):
            v = r.get(col)
            if isinstance(v, str) and v.strip():
                out.setdefault(v.strip(), seq)
    return out


def secuencia_de_fasta(texto) -> str | None:
    """Extrae la secuencia de un FASTA de un solo registro."""
    if not isinstance(texto, str) or not texto.strip():
        return None
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    seq = "".join(l for l in lineas if not l.startswith(">"))
    return seq or None


def partir_fasta_multiple(texto: str) -> dict[str, str]:
    """Parte un FASTA con varios registros en {accession: secuencia}."""
    out: dict[str, str] = {}
    acc, buf = None, []
    for linea in texto.splitlines():
        if linea.startswith(">"):
            if acc and buf:
                out[acc] = "".join(buf)
            partes = linea[1:].split("|")
            acc = partes[1] if len(partes) > 2 else linea[1:].split()[0]
            buf = []
        elif linea.strip():
            buf.append(linea.strip())
    if acc and buf:
        out[acc] = "".join(buf)
    return out


def descargar(pendientes: list[str], ses: requests.Session) -> dict[str, str]:
    """Descarga de UniProt en lotes, con reintentos y espera entre peticiones."""
    out: dict[str, str] = {}
    total = (len(pendientes) + LOTE - 1) // LOTE
    for i in range(0, len(pendientes), LOTE):
        lote = pendientes[i:i + LOTE]
        params = {"accessions": ",".join(lote), "format": "fasta"}
        for intento in range(REINTENTOS):
            try:
                r = ses.get(UNIPROT_STREAM, params=params, timeout=120)
                if r.status_code == 200:
                    out.update(partir_fasta_multiple(r.text))
                    break
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** intento)
                    continue
                print(f"\n  lote {i//LOTE+1}: HTTP {r.status_code}", file=sys.stderr)
                break
            except requests.RequestException as e:
                if intento == REINTENTOS - 1:
                    print(f"\n  lote {i//LOTE+1}: {e}", file=sys.stderr)
                else:
                    time.sleep(2 ** intento)
        print(f"\r  lote {i//LOTE+1}/{total}  acumulado {len(out):,}",
              end="", flush=True)
        time.sleep(PAUSA)
    print()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", required=True, type=Path,
                    help="directorio del dataset limpio")
    ap.add_argument("--historico", type=Path, default=None,
                    help="directorio con {human,mouse}_parent_protein_fasta.csv")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--force", action="store_true",
                    help="vuelve a descargar lo que ya hubiera en la salida")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[3]
    args.out.mkdir(parents=True, exist_ok=True)
    dst = args.out / "parent_proteins.parquet"
    man_p = args.out / "manifest.json"

    previo: dict[str, dict[str, str]] = {}
    if dst.exists() and not args.force:
        t = pd.read_parquet(dst)
        for sp, g in t.groupby("especie"):
            previo[sp] = dict(zip(g.accession, g.secuencia))
        print(f"salida previa: {len(t):,} proteinas")

    need = accessions_necesarios(args.clean)
    filas, manifiesto = [], {}
    ses = requests.Session()
    ses.headers.update({"User-Agent": UA})

    for sp in ("human", "mouse"):
        n = need[sp]
        tengo = dict(previo.get(sp, {}))
        if args.historico:
            for k, v in del_historico(args.historico, sp).items():
                tengo.setdefault(k, v)
        tengo = {k: v for k, v in tengo.items() if k in n}
        faltan = sorted(n - set(tengo))
        print(f"\n{sp}: necesarios {len(n):,} | ya disponibles {len(tengo):,} | "
              f"a descargar {len(faltan):,}")
        bajados = descargar(faltan, ses) if faltan else {}
        tengo.update({k: v for k, v in bajados.items() if k in n})
        # Un accession fusionado se devuelve bajo su id nuevo: se acepta igual
        # y se anota, para que el recuento cuadre.
        extra = {k: v for k, v in bajados.items() if k not in n}
        sin_resolver = sorted(n - set(tengo))
        for acc, seq in sorted(tengo.items()):
            filas.append({"especie": sp, "accession": acc,
                          "longitud": len(seq), "secuencia": seq})
        manifiesto[sp] = {
            "necesarios": len(n),
            "resueltos": len(tengo),
            "descargados_ahora": len([k for k in bajados if k in n]),
            "devueltos_bajo_otro_id": len(extra),
            "sin_resolver": len(sin_resolver),
            "sin_resolver_ejemplos": sin_resolver[:50],
            "cobertura_pct": round(100.0 * len(tengo) / len(n), 4) if n else 0.0,
        }
        print(f"  resueltos {len(tengo):,} ({manifiesto[sp]['cobertura_pct']:.2f} %) "
              f"| sin resolver {len(sin_resolver):,}")

    t = pd.DataFrame(filas)
    t.to_parquet(dst, index=False, compression="zstd")
    csv_p = args.out / "parent_proteins.csv"
    t.to_csv(csv_p, index=False)

    man = {
        "generado_por": "data_pipeline/scripts/data_download/fetch_parent_proteins.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": _git_commit(repo),
        "fuente_descarga": UNIPROT_STREAM,
        "dataset_limpio": str(args.clean),
        "almacen_historico": str(args.historico) if args.historico else None,
        "por_especie": manifiesto,
        "proteinas_totales": len(t),
        "residuos_totales": int(t.longitud.sum()) if len(t) else 0,
        "longitud_mediana": int(t.longitud.median()) if len(t) else 0,
        "sha256_parquet": _sha256(dst),
        "sha256_csv": _sha256(csv_p),
    }
    man_p.write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(f"\nTOTAL {len(t):,} proteinas, {man['residuos_totales']:,} residuos")
    print(f"Salida: {dst}\nManifiesto: {man_p}\nDONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
