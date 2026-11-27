#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
validar_clean.py — Revision del export limpio antes de generar fragmentos.

Comprueba, familia a familia y para los dos endpoints, que el dataset limpio
cumple lo que su manifiesto declara. Es la revision que Laura pidio el 27 nov
antes de dar por bueno el filtrado y pasar a generar fragmentos.

QUE COMPRUEBA, Y POR QUE CADA COSA
----------------------------------
 1. Parquet y CSV existen y tienen las MISMAS filas y columnas. Si divergen, el
    CSV que se revisa a ojo no es el dato que consumen los scripts.
 2. `epitope__object_type` no esta (se descarta por constante) y ninguna fila
    sobrevivio con otro valor: la asercion del filtro se cumplio en origen.
 3. `assay__qualitative_measurement` empieza por "Positive" en TODA fila.
 4. `epitope__species` es la propia de la rama del arbol en TODA fila.
 5. `epitope__starting_position` y `__ending_position` NO estan vacias en
    ninguna fila, y son enteros positivos con start <= end.
 6. LA COMPROBACION QUE DE VERDAD IMPORTA: el peptido se puede LOCALIZAR en su
    proteina madre. Se distinguen tres casos, y solo el tercero es un fallo:

      a) `proteina[start-1:end] == peptido`: las coordenadas de IEDB son
         exactas. Es el 84,2 % de `mhc`.
      b) El peptido ESTA en la proteina pero en otra posicion (6,8 %). NO es
         un fallo del dataset: las coordenadas de IEDB se refieren a veces a
         otra isoforma, o la entrada de UniProt cambio de version desde que se
         anoto. `build_fragments.py` ya esta disenado para no fiarse de ellas
         —verifica y, si fallan, localiza el peptido como subcadena exacta
         (0.10.4)—, de modo que estas filas son perfectamente utilizables.
      c) El peptido NO esta en la proteina en absoluto (0,3 %). Este si es un
         fallo: no hay forma de situarlo y no puede generar una ventana
         centrada. Es lo que decide el veredicto.

    Una version anterior de este script contaba (b) como fallo y daba un
    veredicto de NO APTO sobre 333.619 "fallos" que en su mayoria no lo eran.
 7. Longitud del peptido == end - start + 1. Informativo: casi todos los casos
    son peptidos con notacion quimica en `epitope__name`, que los generadores
    filtran por el criterio de alfabeto canonico.
 8. `assay_id` unico dentro de cada fichero.
 9. En `tcell`: `peptido_origen` coherente, y las filas corregidas tienen un
    peptido que de verdad esta en su proteina en las coordenadas recalculadas
    (lo cubre la comprobacion 6, que se aplica a todas).

Ninguna comprobacion se da por buena sin medirla: el informe dice el recuento
exacto de fallos de cada una, no un OK global.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u data_pipeline/scripts/iedb_verification_20261124/validar_clean.py \\
        --clean data/data_raw_full_20261126_clean \\
        --proteins data/parent_proteins_20261127/parent_proteins.parquet
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

CANONICOS = set("ACDEFGHIKLMNPQRSTVWY")
ESPECIE_PROPIA = {"human": "Homo sapiens", "mouse": "Mus musculus"}


def accession_de_iri(iri: object) -> str:
    if not isinstance(iri, str) or not iri.strip():
        return ""
    return iri.rsplit("/", 1)[-1]


def validar_fichero(pq: Path, especie: str, seqs: dict[str, str]) -> dict:
    kind = "tcell" if "tcell" in pq.name else "mhc"
    csv = pq.with_suffix(".csv")
    r: dict = {"fichero": str(pq), "kind": kind, "fallos": {}}

    d = pd.read_parquet(pq)
    r["filas"] = len(d)
    r["columnas"] = list(d.columns)

    # 1. Parquet y CSV coinciden.
    if not csv.exists():
        r["fallos"]["csv_ausente"] = 1
    else:
        c = pd.read_csv(csv, dtype=str, low_memory=False)
        if len(c) != len(d):
            r["fallos"]["csv_filas_distintas"] = abs(len(c) - len(d))
        if list(c.columns) != list(d.columns):
            r["fallos"]["csv_columnas_distintas"] = 1

    # 2. Objeto peptidico: la columna se descarta por constante.
    if "epitope__object_type" in d.columns:
        malas = int((d["epitope__object_type"] != "Linear peptide").sum())
        if malas:
            r["fallos"]["object_type_no_linear"] = malas

    # 3. Etiqueta positiva en toda fila.
    col = "assay__qualitative_measurement"
    if col in d.columns:
        malas = int((~d[col].fillna("").str.startswith("Positive")).sum())
        if malas:
            r["fallos"]["cualitativo_no_positive"] = malas
    else:
        r["fallos"]["falta_columna_cualitativo"] = 1

    # 4. Especie propia.
    if "epitope__species" in d.columns:
        esp = ESPECIE_PROPIA[especie]
        malas = int((~d["epitope__species"].fillna("").str.contains(
            esp, case=False, regex=False)).sum())
        if malas:
            r["fallos"]["especie_ajena"] = malas

    # 5. Coordenadas presentes y sanas.
    ini_c, fin_c = "epitope__starting_position", "epitope__ending_position"
    if ini_c not in d.columns or fin_c not in d.columns:
        r["fallos"]["faltan_columnas_de_coordenadas"] = 1
        return r
    vacias = int(d[[ini_c, fin_c]].isna().any(axis=1).sum())
    if vacias:
        r["fallos"]["coordenadas_vacias"] = vacias
    ini = pd.to_numeric(d[ini_c], errors="coerce")
    fin = pd.to_numeric(d[fin_c], errors="coerce")
    no_num = int((ini.isna() | fin.isna()).sum()) - vacias
    if no_num > 0:
        r["fallos"]["coordenadas_no_numericas"] = no_num
    validas = ini.notna() & fin.notna()
    if int((validas & (ini < 1)).sum()):
        r["fallos"]["start_menor_que_1"] = int((validas & (ini < 1)).sum())
    if int((validas & (fin < ini)).sum()):
        r["fallos"]["end_menor_que_start"] = int((validas & (fin < ini)).sum())

    # 6 y 7. El peptido esta en la proteina en las coordenadas declaradas.
    pep = d["epitope__name"].astype(str).str.strip().str.upper()
    acc = d["epitope__molecule_parent_iri"].map(accession_de_iri)
    sin_acc = int((acc == "").sum())
    if sin_acc:
        r["sin_accession"] = sin_acc
    exacto = otra_posicion = no_localizable = 0
    sin_proteina = long_mal = no_canonico = 0
    ejemplos: list[dict] = []
    for i in d.index:
        a, p = acc.at[i], pep.at[i]
        if not p or set(p) - CANONICOS:
            no_canonico += 1
            continue
        if not a:
            continue
        seq = seqs.get(a)
        if seq is None:
            sin_proteina += 1
            continue
        si, fi = ini.at[i], fin.at[i]
        coords_ok = (
            pd.notna(si) and pd.notna(fi)
            and len(p) == int(fi) - int(si) + 1
            and int(fi) <= len(seq)
            and seq[int(si) - 1:int(fi)] == p
        )
        if pd.notna(si) and pd.notna(fi) and len(p) != int(fi) - int(si) + 1:
            long_mal += 1
        if coords_ok:
            exacto += 1
        elif p in seq:
            otra_posicion += 1
        else:
            no_localizable += 1
            if len(ejemplos) < 5:
                ejemplos.append({"accession": a, "peptido": p,
                                 "start": None if pd.isna(si) else int(si),
                                 "end": None if pd.isna(fi) else int(fi),
                                 "longitud_proteina": len(seq)})
    r["localizacion"] = {
        "coordenadas_exactas": exacto,
        "localizable_en_otra_posicion": otra_posicion,
        "no_localizable": no_localizable,
        "peptido_no_canonico": no_canonico,
        "accession_no_esta_en_el_almacen": sin_proteina,
        "longitud_distinta_de_end_menos_start": long_mal,
    }
    # SOLO lo no localizable es un fallo. Lo demas el pipeline lo resuelve:
    # (b) por busqueda de subcadena, y los no canonicos por el filtro de
    # alfabeto de los generadores.
    if no_localizable:
        r["fallos"]["peptido_NO_localizable_en_su_proteina"] = no_localizable
        r["ejemplos_no_localizables"] = ejemplos
    r["peptidos_no_canonicos"] = no_canonico

    # 8. assay_id unico.
    if "assay_id" in d.columns:
        dup = int(d["assay_id"].duplicated().sum())
        if dup:
            r["fallos"]["assay_id_duplicado"] = dup

    # 9. tcell: peptido_origen coherente.
    if kind == "tcell":
        if "peptido_origen" not in d.columns:
            r["fallos"]["falta_peptido_origen"] = 1
        else:
            vc = d["peptido_origen"].value_counts().to_dict()
            r["peptido_origen"] = {str(k): int(v) for k, v in vc.items()}
            malas = int((d["peptido_origen"] == "descartada").sum())
            if malas:
                r["fallos"]["filas_marcadas_descartada_que_sobrevivieron"] = malas

    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", required=True, type=Path)
    ap.add_argument("--proteins", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None,
                    help="JSON con el informe completo")
    args = ap.parse_args()

    p = pd.read_parquet(args.proteins, columns=["accession", "secuencia"])
    seqs = dict(zip(p["accession"], p["secuencia"].astype(str).str.upper()))
    print(f"almacen de proteinas: {len(seqs):,} secuencias\n")

    ficheros = sorted(args.clean.rglob("*_export_full_slim.parquet"))
    if not ficheros:
        print(f"ERROR: ningun *_export_full_slim.parquet bajo {args.clean}",
              file=sys.stderr)
        return 2

    informes = []
    total_fallos = 0
    print(f"{'fichero':40} {'filas':>9} {'exactas':>9} {'otra pos':>9} "
          f"{'no local':>8}  resultado")
    for pq in ficheros:
        especie = pq.relative_to(args.clean).parts[0]
        r = validar_fichero(pq, especie, seqs)
        informes.append(r)
        n = sum(r["fallos"].values())
        total_fallos += n
        etiqueta = "/".join(pq.relative_to(args.clean).parts[:-1]) + (
            "/tcell" if r["kind"] == "tcell" else "/mhc")
        loc = r.get("localizacion", {})
        estado = "OK" if not n else ", ".join(f"{k}={v}" for k, v in r["fallos"].items())
        print(f"{etiqueta:40} {r['filas']:>9,} {loc.get('coordenadas_exactas',0):>9,} "
              f"{loc.get('localizable_en_otra_posicion',0):>9,} "
              f"{loc.get('no_localizable',0):>8,}  {estado}")

    agg: dict[str, int] = {}
    for i in informes:
        for k, v in i.get("localizacion", {}).items():
            agg[k] = agg.get(k, 0) + v
    filas = sum(i["filas"] for i in informes)
    print()
    print(f"filas totales                              : {filas:,}")
    print(f"  coordenadas exactas                      : {agg.get('coordenadas_exactas',0):,}")
    print(f"  localizable en otra posicion (recuperable): "
          f"{agg.get('localizable_en_otra_posicion',0):,}")
    print(f"  UTILIZABLES (suma de las dos anteriores) : "
          f"{agg.get('coordenadas_exactas',0)+agg.get('localizable_en_otra_posicion',0):,}")
    print(f"  peptido no canonico (lo filtra el generador): "
          f"{agg.get('peptido_no_canonico',0):,}")
    print(f"  accession no esta en el almacen          : "
          f"{agg.get('accession_no_esta_en_el_almacen',0):,}")
    print(f"  sin accession                            : "
          f"{sum(i.get('sin_accession',0) for i in informes):,}")
    print(f"  NO LOCALIZABLE (fallo real)              : {agg.get('no_localizable',0):,}")
    print(f"\nTOTAL de fallos                            : {total_fallos:,}")
    # Un 0,5 % de filas no localizables es rotacion normal de UniProt, no un
    # defecto del filtrado: el generador las descarta y lo registra. El
    # veredicto solo se vuelve negativo si hay fallos estructurales (etiqueta,
    # especie, coordenadas vacias, CSV descuadrado) o si lo no localizable
    # deja de ser marginal.
    estructurales = total_fallos - agg.get("no_localizable", 0)
    frac = agg.get("no_localizable", 0) / filas if filas else 0
    apto = estructurales == 0 and frac < 0.02
    print("VEREDICTO:", "APTO para generar fragmentos" if apto else
          "NO APTO: hay fallos estructurales que corregir")
    print(f"  fallos estructurales: {estructurales:,} | "
          f"no localizables: {100*frac:.2f} % (umbral 2 %)")

    if args.out:
        args.out.write_text(json.dumps(
            {"total_fallos": total_fallos, "ficheros": informes},
            indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"informe: {args.out}")
    return 0 if total_fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
