#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_splits.py — Particion TRAIN / VALIDATION / TEST sin fuga.

POR QUE NO BASTA PARTIR POR PROTEINA
------------------------------------
Partir por `accession` evita que una proteina aparezca en dos particiones, pero
**no** evita que una misma SECUENCIA de fragmento lo haga: hay 18.219
fragmentos que salen de varias proteinas distintas. Si una de esas proteinas
cae en TRAIN y otra en TEST, el modelo ve en TEST un vector que ya memorizo.

La unidad de independencia correcta es por tanto la **componente conexa** del
grafo bipartito proteina–fragmento: dos proteinas quedan unidas si comparten
alguna secuencia de fragmento, y la componente entera va a una sola particion.
Eso garantiza las dos cosas a la vez:

  * ninguna proteina aparece en dos particiones;
  * **ninguna secuencia de fragmento aparece en dos particiones**.

Es la politica que §0.2 llama "particion por componentes de proteina", y la que
sustituye a la particion por fila de §10.1, responsable del 0,7955 contaminado.

LO QUE ADEMAS SE MIDE, Y NO SE CORRIGE
--------------------------------------
La fuga por publicacion (hallazgo O) **no** la cubre esta particion. Un solo
estudio de inmunopeptidomica aporta decenas de miles de fragmentos con el mismo
tipo celular, el mismo anticuerpo y el mismo sesgo de preparacion:
`HLA-B*15:02` tiene 20.643 positivos de 9 publicaciones. El script mide cuantos
`pmid` quedan repartidos entre particiones y lo deja en el manifiesto, para que
el solapamiento sea un numero declarado y no una sorpresa.

Con `--unit pmid` la particion se hace por publicacion en lugar de por
componente, lo que da el control complementario: si la metrica cae mucho al
pasar de una a otra, la fuga tecnica era el problema.

ESTRATIFICACION
---------------
Las componentes se reparten con un voraz que asigna cada componente a la
particion mas por debajo de su objetivo, de mayor a menor tamano. No se
estratifica por familia a proposito: una componente puede abarcar varias
familias, de modo que forzar la estratificacion romperia la independencia. El
reparto por familia resultante se mide y se reporta.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u data_pipeline/scripts/data_download/build_splits.py \\
        --fragments data/fragments_w21_ss --out data/splits_w21 --seed 42
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


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


class UnionFind:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        r = x
        while self.p[r] != r:
            r = self.p[r]
        while self.p[x] != r:          # compresion de camino
            self.p[x], x = r, self.p[x]
        return r

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def componentes(df: pd.DataFrame) -> pd.Series:
    """Componente conexa de cada fila del grafo proteina–fragmento.

    Se une cada proteina con las demas que comparten alguna secuencia de
    fragmento. El nodo de union es la propia secuencia, de modo que dos
    proteinas que comparten un fragmento quedan en la misma componente.
    """
    uf = UnionFind()
    for acc, frag in zip(df.accession.values, df.fragmento.values):
        uf.union("p:" + acc, "f:" + frag)
    return pd.Series([uf.find("p:" + a) for a in df.accession.values],
                     index=df.index)


def reparte(mat: pd.DataFrame, objetivos: dict[str, float],
            rng: np.random.Generator) -> dict[str, str]:
    """Voraz consciente de familia: minimiza el desvio relativo en TODAS ellas.

    `mat` tiene una fila por componente y una columna por familia, con el numero
    de filas que la componente aporta a cada una. Se recorren las componentes de
    mayor a menor y cada una va a la particion donde su incorporacion deja el
    desvio relativo agregado mas bajo.

    Un voraz que solo mire el total global desequilibra las familias pequenas:
    con reparto 80/10/10, HLA-DQ salia al 47,08 % de prevalencia en VALIDATION
    frente al 27,68 % de TRAIN, porque una sola componente grande de esa familia
    caia entera en VALIDATION. Mirando el desvio por familia eso no ocurre.
    """
    fams = list(mat.columns)
    tot = mat.sum(axis=0)                      # filas por familia
    cupo = {k: {f: objetivos[k] * tot[f] for f in fams} for k in objetivos}
    actual = {k: {f: 0.0 for f in fams} for k in objetivos}

    orden = mat.assign(_n=mat.sum(axis=1), _r=rng.random(len(mat)))
    orden = orden.sort_values(["_n", "_r"], ascending=[False, True])

    def coste(k: str, fila) -> float:
        """Grado de LLENADO relativo tras asignar, ponderado por aportacion.

        Se elige la particion relativamente mas vacia en las familias que esta
        componente alimenta. Usar el llenado y no la distancia absoluta al
        objetivo es lo que mantiene el 80/10/10: la distancia absoluta premia al
        cubo pequeno, porque al principio esta mucho mas lejos de su objetivo en
        terminos relativos, y manda todo a VALIDATION y TEST.
        """
        num = den = 0.0
        for f in fams:
            v = float(fila[f])
            if v <= 0:
                continue
            objetivo = cupo[k][f]
            if objetivo <= 0:
                continue
            num += v * (actual[k][f] + v) / objetivo
            den += v
        if den == 0:                      # componente de una familia sin cupo
            return sum(actual[k][f] / max(cupo[k][f], 1) for f in fams)
        return num / den

    asig: dict[str, str] = {}
    for comp, fila in orden.iterrows():
        k = min(objetivos, key=lambda s: coste(s, fila))
        asig[comp] = k
        for f in fams:
            actual[k][f] += fila[f]
    return asig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--unit", choices=("componente", "pmid"), default="componente",
                    help="componente proteina-fragmento (por omision) o publicacion")
    ap.add_argument("--train", type=float, default=0.80)
    ap.add_argument("--val", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[3]
    args.out.mkdir(parents=True, exist_ok=True)
    objetivos = {"train": args.train, "val": args.val,
                 "test": round(1.0 - args.train - args.val, 10)}
    if min(objetivos.values()) <= 0:
        print(f"ERROR: objetivos invalidos {objetivos}", file=sys.stderr)
        return 2

    cols = ["familia", "especie", "clase", "fragmento", "label", "alelo",
            "accession", "pmid", "ss_status"]
    # Tres formatos de entrada, por orden de preferencia. `windows.parquet` es
    # la salida del generador DESLIZANTE (epitope_classification.py), que no
    # tiene columna `alelo` —en una ventana deslizante los alelos de los
    # epitopos contenidos van en `alelos`, en plural y unidos por ';'— ni
    # `pmid` en singular. Se normalizan los nombres aqui para que el resto del
    # script no tenga que saber de que generador viene.
    partes = []
    for nombre, faltan in (("fragments_ss.parquet", ()),
                           ("fragments.parquet", ("ss_status",)),
                           ("windows.parquet", ("ss_status",))):
        for f in sorted(args.fragments.rglob(nombre)):
            disponibles = set(pq.ParquetFile(f).schema.names)
            pedidas = [c for c in cols if c not in faltan and c in disponibles]
            d = pd.read_parquet(f, columns=pedidas)
            if "alelo" not in d.columns:
                d["alelo"] = (pd.read_parquet(f, columns=["alelos"])["alelos"]
                              if "alelos" in disponibles else None)
            if "pmid" not in d.columns:
                d["pmid"] = (pd.read_parquet(f, columns=["pmids"])["pmids"]
                             if "pmids" in disponibles else None)
            partes.append(d)
        if partes:
            break
    if not partes:
        print(f"ERROR: ningun fragments_ss/fragments/windows.parquet bajo "
              f"{args.fragments}", file=sys.stderr)
        return 2
    D = pd.concat(partes, ignore_index=True)
    print(f"filas: {len(D):,} | proteinas {D.accession.nunique():,} | "
          f"fragmentos unicos {D.fragmento.nunique():,}")

    if args.unit == "componente":
        D["grupo"] = componentes(D)
    else:
        # Las filas sin pmid (envios directos a IEDB) forman grupo propio por
        # accession, para no amontonarlas todas juntas en una particion.
        D["grupo"] = np.where(D.pmid.notna(), "m:" + D.pmid.astype(str),
                              "a:" + D.accession.astype(str))
    tam = D.groupby("grupo").size()
    print(f"grupos ({args.unit}): {len(tam):,} | mayor {int(tam.max()):,} filas "
          f"({100*tam.max()/len(D):.2f} %) | mediana {int(tam.median())}")

    # Filas por (componente, familia, etiqueta). Hay que separar positivos de
    # senuelos: equilibrar solo filas por familia deja la PREVALENCIA desviada
    # —HLA-B salia al 45,54 % en TRAIN y al 57,01 % en TEST—, porque una
    # componente puede ser casi toda positiva o casi toda senuelo.
    mat = (D.groupby(["grupo", "familia", "label"]).size()
           .unstack(level=[1, 2], fill_value=0).astype(float))
    mat.columns = [f"{f}|{int(l)}" for f, l in mat.columns]
    rng = np.random.default_rng(args.seed)
    asig = reparte(mat, objetivos, rng)
    D["split"] = D.grupo.map(asig)

    # --- certificacion de ausencia de fuga ---
    cert: dict = {}
    for clave in ("fragmento", "accession"):
        n = D.groupby(clave).split.nunique()
        cruza = int((n > 1).sum())
        cert[clave] = {"claves": int(len(n)), "en_varias_particiones": cruza}
        print(f"  {clave:12s}: {cruza:,} de {len(n):,} en varias particiones")
    npm = D[D.pmid.notna()].groupby("pmid").split.nunique()
    cert["pmid"] = {"claves": int(len(npm)),
                    "en_varias_particiones": int((npm > 1).sum())}
    print(f"  {'pmid':12s}: {int((npm>1).sum()):,} de {len(npm):,} en varias "
          f"particiones  <- NO lo corrige esta particion, se declara")
    if args.unit == "componente" and cert["fragmento"]["en_varias_particiones"]:
        print("ABORTADO: con particion por componente ninguna secuencia puede "
              "cruzar", file=sys.stderr)
        return 1

    # --- tablas de reparto ---
    print("\nreparto global:")
    g = D.groupby("split").agg(filas=("label", "size"),
                               pos=("label", "sum")).reindex(["train", "val", "test"])
    g["neg"] = g.filas - g.pos
    g["pct"] = (100 * g.filas / len(D)).round(2)
    g["prev"] = (100 * g.pos / g.filas).round(2)
    print(g.to_string())
    print("\nprevalencia por familia y particion (%):")
    pv = (100 * D.pivot_table(index="familia", columns="split", values="label",
                              aggfunc="mean")).round(2)
    print(pv.reindex(columns=["train", "val", "test"]).to_string())

    p = args.out / "splits.parquet"
    D[["familia", "accession", "fragmento", "grupo", "split"]].to_parquet(
        p, index=False, compression="zstd")
    man = {
        "generado_por": "data_pipeline/scripts/data_download/build_splits.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": _git_commit(repo),
        "fragmentos": str(args.fragments),
        "unidad": args.unit,
        "objetivos": objetivos,
        "seed": args.seed,
        "filas": int(len(D)),
        "grupos": int(len(tam)),
        "grupo_mayor_filas": int(tam.max()),
        "certificacion_fuga": cert,
        "reparto": g.fillna(0).astype(object).to_dict(),
        "prevalencia_por_familia": pv.fillna(0).to_dict(),
        "sha256_parquet": _sha256(p),
        "nota_pmid": ("la particion por componente NO controla la fuga por "
                      "publicacion; el solapamiento de pmid se declara arriba. "
                      "Usar --unit pmid para el control complementario."),
    }
    (args.out / "manifest.json").write_text(json.dumps(man, indent=2,
                                                       ensure_ascii=False))
    print(f"\nSalida: {p}\nManifiesto: {args.out/'manifest.json'}\nDONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
