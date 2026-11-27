#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epitope_classification.py — Ventanas deslizantes de la proteina madre.

CRITERIO (fijado por Laura el 26 nov 2026)
------------------------------------------
Para cada proteina madre se recorren TODAS las ventanas de `--window`
aminoacidos con paso `--stride` (1 por omision), y cada ventana produce
UNA SOLA FILA:

    label = 1  si la ventana contiene ENTERO al menos un epitopo
    label = 0  si no contiene ninguno entero

Da igual que contenga 1 o 3 epitopos: la etiqueta es 1 y se escribe una fila.
Los epitopos contenidos y sus alelos quedan como ANOTACION en columnas, no
multiplican filas.

QUE CAMBIA RESPECTO A LA VERSION ANTERIOR DE ESTE FICHERO
---------------------------------------------------------
La logica de ventaneo es la misma (contencion completa, paso 1) y se conservan
sus tres funciones con contenido real: el test de contencion,
`validate_exact_match` y `compute_epitope_position_score`. Lo que se reescribe:

1. UNA FILA POR VENTANA. La version anterior hacia
   `for ep_name, pos_score in positive_hits: rows.append(...)`, es decir una
   fila por cada epitopo contenido, con la MISMA secuencia y la MISMA
   etiqueta. Eso produjo 9,86 M de positivos historicos donde las ventanas
   positivas distintas son muchas menos, y sesgaba la perdida hacia las
   regiones densas en epitopos.

2. ENTRADA NUEVA. Antes leia `data_raw/<esp>/<clase>/<hap>/merged_unique_events.csv`
   y `{especie}_parent_protein_fasta.csv`, que el pipeline ya no genera. Ahora
   lee el export limpio (`slim_raw_export.py --columns core`) y el almacen de
   proteinas (`fetch_parent_proteins.py`).

3. SE CONSERVA EL ALELO. La version anterior no lo guardaba, y sin el no se
   puede hacer el paso de one-hot/pseudosecuencia.

4. COSTE. El bucle anterior era O(ventanas x epitopos) por proteina. Aqui se
   invierte: un epitopo de longitud L esta contenido exactamente en las
   ventanas cuyo inicio cae en [fin-w+1, inicio], que son como mucho w-L+1.
   Se marca ese rango y se evita recorrer todas las ventanas por cada epitopo.

5. PROCEDENCIA. Parquet por familia y `manifest.json` con SHA-256, recuentos,
   commit de git y los parametros exactos, como el resto del pipeline.

AVISO SOBRE EL ALELO, QUE NO RESUELVE ESTE SCRIPT
-------------------------------------------------
Las ventanas positivas llevan los alelos de los epitopos que contienen; las
negativas no llevan ninguno, porque no hay nada que anotar. Por tanto la
columna `alelos` NO puede usarse como feature tal cual: estaria perfectamente
correlacionada con la etiqueta (CLAUDE.md 0.10.6 y la medida del 26 nov:
100,00 % de positivos con alelo frente a 0,00 % de senuelos). Para el
experimento del alelo hay que derivar una tabla de pares (ventana, alelo) en
las dos clases. Los embeddings de ProtT5 no dependen del alelo y se indexan
por secuencia, asi que esa tabla se deriva despues sin recalcular nada.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u data_pipeline/scripts/data_classification/epitope_classification.py \
        --clean data/data_raw_full_20261126_clean \
        --proteins data/parent_proteins_20261126/parent_proteins.parquet \
        --out data/windows_w25_20261126 \
        --window 25

    # una sola familia
    $P -u ... --only mouse/mhc-I/H2-K
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CANONICOS = set("ACDEFGHIKLMNPQRSTVWY")
FLUSH_FILAS = 2_000_000

ESQUEMA = pa.schema([
    ("especie", pa.string()),
    ("clase", pa.string()),
    ("familia", pa.string()),
    ("accession", pa.string()),
    ("fragmento", pa.string()),
    ("frag_inicio", pa.int32()),
    ("frag_fin", pa.int32()),
    ("label", pa.int8()),
    ("n_epitopos", pa.int16()),
    ("epitopos", pa.string()),
    ("alelos", pa.string()),
    ("n_alelos", pa.int16()),
    ("epitopo_offset", pa.int16()),
    ("epitopo_long", pa.int16()),
    ("pos_score", pa.float32()),
    ("pmids", pa.string()),
])


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        stream=sys.stdout,
    )


def commit_git() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "desconocido"


def sha256_fichero(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Logica conservada de la version anterior de este fichero.
# --------------------------------------------------------------------------- #
def compute_epitope_position_score(
    window_start: int, window_end: int, ep_start: int, ep_end: int, window_size: int
) -> float:
    """Posicion relativa del epitopo dentro de la ventana, en [-1, 1].

    0.0  -> el centro del epitopo coincide con el de la ventana
    <0.0 -> desplazado hacia la izquierda;  >0.0 hacia la derecha
    """
    window_center = math.ceil(window_size / 2)
    max_center_dist = window_center - 1
    if max_center_dist == 0:
        return 0.0
    ep_center = (ep_start + ep_end) / 2.0
    ep_center_in_window = ep_center - window_start + 1
    signed_dist = ep_center_in_window - window_center
    score = min(1.0, abs(signed_dist) / max_center_dist)
    return round(math.copysign(score, signed_dist), 3)


def validate_exact_match(
    protein_seq: str, epitope_seq: str, ep_start: int, ep_end: int
) -> bool:
    """Las coordenadas de IEDB deben reproducir el peptido sobre la secuencia."""
    if not protein_seq or not epitope_seq:
        return False
    if ep_start < 1 or ep_end < 1 or ep_start > ep_end or ep_end > len(protein_seq):
        return False
    return protein_seq[ep_start - 1:ep_end] == epitope_seq


# --------------------------------------------------------------------------- #
def accession_de_iri(iri: object) -> str:
    """`http://www.uniprot.org/uniprot/Q13296` -> `Q13296`."""
    if iri is None or (isinstance(iri, float) and np.isnan(iri)):
        return ""
    s = str(iri).strip().rstrip("/")
    if not s:
        return ""
    return s.rsplit("/", 1)[-1]


def epitopos_de_familia(
    clean_dir: Path, especie: str, clase: str, familia: str,
    descartes: dict | None = None, drop_modified: bool = True,
) -> pd.DataFrame:
    """Lee el export limpio de una familia y deduplica a epitopos unicos.

    Descarta las filas que no se pueden situar en una proteina y, si se le
    pasa `descartes`, anota cuantas quita cada condicion. Importa desde el
    27 nov 2026: `slim_raw_export.py` dejo de filtrar por accession, de modo
    que esas filas ahora LLEGAN aqui y es este script el que las retira. Sin
    el registro, la perdida seria invisible (en la descarga del 24 eran
    503.288 filas, de ellas 445.756 de HLA-DR).
    """
    base = clean_dir / especie / clase / familia
    ficheros = sorted(base.glob("mhc_export*.parquet"))
    if not ficheros:
        return pd.DataFrame()

    partes = [pd.read_parquet(f) for f in ficheros]
    df = pd.concat(partes, ignore_index=True)

    df["accession"] = df["epitope__molecule_parent_iri"].map(accession_de_iri)
    df["peptido"] = df["epitope__name"].astype(str).str.strip().str.upper()
    for col, destino in (
        ("epitope__starting_position", "inicio"),
        ("epitope__ending_position", "fin"),
    ):
        df[destino] = pd.to_numeric(df[col], errors="coerce")

    sin_accession = (df["accession"] == "")
    sin_peptido = ~df["peptido"].str.len().gt(0)
    sin_coords = df["inicio"].isna() | df["fin"].isna()
    no_canonico = ~df["peptido"].map(
        lambda p: isinstance(p, str) and bool(p) and set(p) <= CANONICOS
    )
    # La modificacion quimica es el UNICO de estos descartes que es una
    # decision y no una necesidad tecnica: un peptido oxidado si se puede
    # situar en su proteina, pero su ventana saldria identica a la del no
    # modificado, de modo que entraria como si fuera otra molecula. Decision
    # de Laura del 25 nov; `--keep-modified` la revierte.
    modificado = (
        df["epitope__modifications"].notna()
        if drop_modified and "epitope__modifications" in df.columns
        else pd.Series(False, index=df.index)
    )
    if descartes is not None:
        descartes.update({
            "filas_de_entrada": int(len(df)),
            "sin_accession_de_proteina_madre": int(sin_accession.sum()),
            "sin_secuencia_de_peptido": int(sin_peptido.sum()),
            "sin_coordenadas": int((~sin_accession & sin_coords).sum()),
            "peptido_no_canonico": int((~sin_accession & ~sin_coords & no_canonico).sum()),
            "con_modificacion_quimica": int(
                (~sin_accession & ~sin_coords & ~no_canonico & modificado).sum()
            ),
        })
    df = df[
        ~sin_accession & ~sin_peptido & ~sin_coords & ~no_canonico & ~modificado
    ].copy()
    if descartes is not None:
        descartes["filas_conservadas"] = int(len(df))
    df["inicio"] = df["inicio"].astype(int)
    df["fin"] = df["fin"].astype(int)
    df["alelo"] = df["mhc_restriction__name"].astype(str).str.strip()
    df["pmid"] = df["reference__pmid"].astype(str).str.strip()

    # Un epitopo unico es (proteina, peptido, coordenadas). Los distintos
    # ensayos del mismo epitopo aportan alelos y publicaciones, no filas.
    agrupado = (
        df.groupby(["accession", "peptido", "inicio", "fin"], sort=False)
        .agg(
            alelos=("alelo", lambda s: sorted({x for x in s if x})),
            pmids=("pmid", lambda s: sorted({x for x in s if x and x.lower() != "nan"})),
        )
        .reset_index()
    )
    return agrupado


def posiciones_no_canonicas(seq: str) -> np.ndarray:
    """Prefijo acumulado de residuos no canonicos, para descartar ventanas."""
    malo = np.fromiter((c not in CANONICOS for c in seq), dtype=np.int8, count=len(seq))
    return np.concatenate(([0], np.cumsum(malo)))


def ventanas_de_proteina(
    acc: str, seq: str, epitopos: list[dict], w: int, stride: int
) -> tuple[list[list], dict[str, int]]:
    """Genera una fila por ventana de `seq`. Devuelve (filas, contadores)."""
    cont = {"ventanas": 0, "descartadas_no_canonico": 0, "positivas": 0,
            "duplicadas_misma_proteina": 0}
    n = len(seq)
    if n < w:
        return [], cont

    inicios = range(1, n - w + 2, stride)

    # Invertir el bucle: cada epitopo marca solo las ventanas que lo contienen.
    por_ventana: dict[int, list[int]] = {}
    for k, ep in enumerate(epitopos):
        a, b = ep["inicio"], ep["fin"]
        lo = max(1, b - w + 1)
        hi = min(a, n - w + 1)
        if lo > hi:
            continue  # el epitopo es mas largo que la ventana: no cabe entero
        primero = lo + ((stride - (lo - 1) % stride) % stride)
        for s in range(primero, hi + 1, stride):
            por_ventana.setdefault(s, []).append(k)

    prefijo = posiciones_no_canonicas(seq)
    filas: list[list] = []

    for s in inicios:
        cont["ventanas"] += 1
        e = s + w - 1
        if prefijo[e] - prefijo[s - 1] > 0:
            cont["descartadas_no_canonico"] += 1
            continue

        frag = seq[s - 1:e]
        idxs = por_ventana.get(s)

        if not idxs:
            filas.append([acc, frag, s, e, 0, 0, "", "", 0, -1, 0, float("nan"), ""])
            continue

        cont["positivas"] += 1
        conten = [epitopos[k] for k in idxs]
        # Representante: el epitopo mas centrado en la ventana.
        scores = [
            (abs(compute_epitope_position_score(s, e, c["inicio"], c["fin"], w)), i)
            for i, c in enumerate(conten)
        ]
        _, mejor = min(scores)
        rep = conten[mejor]
        alelos = sorted({a for c in conten for a in c["alelos"]})
        pmids = sorted({p for c in conten for p in c["pmids"]})

        filas.append([
            acc, frag, s, e, 1, len(conten),
            ";".join(c["peptido"] for c in conten),
            ";".join(alelos), len(alelos),
            rep["inicio"] - s,
            rep["fin"] - rep["inicio"] + 1,
            compute_epitope_position_score(s, e, rep["inicio"], rep["fin"], w),
            ";".join(pmids),
        ])

    # Deduplicacion dentro de la proteina (Laura, 27 nov): misma proteina,
    # misma secuencia y misma etiqueta -> una sola fila. Con paso 1 casi todas
    # las ventanas son distintas, pero una proteina con una region repetida
    # (colageno, repeticiones de baja complejidad) produce la misma ventana
    # varias veces, y serian ejemplos identicos con pesos distintos en la
    # perdida. Se conserva la PRIMERA ocurrencia, es decir la mas cercana al
    # extremo N, para que el resultado no dependa del orden de iteracion.
    #
    # Nota: con etiqueta por secuencia (0.20.2) una misma secuencia no puede
    # tener dos etiquetas distintas dentro de la familia —si contiene un
    # epitopo, lo contiene siempre—, de modo que deduplicar por (secuencia,
    # etiqueta) y por secuencia sola es lo mismo. Se incluye la etiqueta en la
    # clave de todos modos, para que la propiedad quede comprobada y no
    # asumida: si alguna vez difiere, la fila sobrevive y el conteo lo delata.
    vistos: set[tuple[str, int]] = set()
    unicas: list[list] = []
    for f in filas:
        clave = (f[1], f[4])          # (fragmento, label)
        if clave in vistos:
            cont["duplicadas_misma_proteina"] += 1
            if f[4] == 1:
                cont["positivas"] -= 1
            continue
        vistos.add(clave)
        unicas.append(f)

    return unicas, cont


def procesar_familia(
    clean_dir: Path, out_dir: Path, seqs: dict[str, str],
    especie: str, clase: str, familia: str, w: int, stride: int,
    drop_modified: bool = True, emit_csv: bool = False,
) -> dict:
    descartes: dict = {}
    eps = epitopos_de_familia(
        clean_dir, especie, clase, familia, descartes, drop_modified
    )
    if descartes:
        logging.info(
            "%s: %d filas del export; descartadas %d sin accession, %d sin "
            "coordenadas, %d no canonicas, %d modificadas -> %d utilizables",
            familia, descartes["filas_de_entrada"],
            descartes["sin_accession_de_proteina_madre"],
            descartes["sin_coordenadas"], descartes["peptido_no_canonico"],
            descartes["con_modificacion_quimica"], descartes["filas_conservadas"],
        )
    if eps.empty:
        logging.warning("%s/%s/%s: sin epitopos en el export limpio", especie, clase, familia)
        return {"familia": familia, "filas": 0, "descartes_del_export": descartes}

    # --- Catalogo de epitopos de la familia, por secuencia -------------------
    # La etiqueta se decide por SECUENCIA, no por la coordenada anotada. Si un
    # 9-mer es epitopo conocido de esta familia, una ventana que lo contenga lo
    # contiene, venga de la proteina donde se anoto o de otra. Etiquetarlo por
    # coordenada produce falsos negativos: medido el 26 nov, 40 de 70.605
    # negativas de H2-L/H2-IE contenian un epitopo conocido, todas por
    # ocurrencias en OTRA proteina de la familia. Es el mecanismo del 23,09 %
    # de contradicciones historicas (CLAUDE.md 11.1); aqui gana el positivo,
    # igual que en build_fragments.py.
    sin_secuencia = coord_invalida = no_cabe = coord_no_cuadra = 0
    por_seq: dict[str, dict[str, set]] = {}
    accs_con_epitopo: set[str] = set()

    for r in eps.itertuples(index=False):
        seq = seqs.get(r.accession)
        if seq is None:
            sin_secuencia += 1
            continue
        if len(r.peptido) > w:
            no_cabe += 1
            continue
        if r.peptido not in seq:
            coord_invalida += 1
            continue
        if not validate_exact_match(seq, r.peptido, r.inicio, r.fin):
            coord_no_cuadra += 1
        accs_con_epitopo.add(r.accession)
        d = por_seq.setdefault(r.peptido, {"alelos": set(), "pmids": set()})
        d["alelos"].update(r.alelos)
        d["pmids"].update(r.pmids)

    por_longitud: dict[int, set[str]] = {}
    for p in por_seq:
        por_longitud.setdefault(len(p), set()).add(p)
    longitudes = sorted(por_longitud)

    def epitopos_en(seq: str) -> list[dict]:
        """Todas las ocurrencias de cualquier epitopo de la familia en `seq`."""
        hallados: list[dict] = []
        n = len(seq)
        for L in longitudes:
            conjunto = por_longitud[L]
            for i in range(n - L + 1):
                sub = seq[i:i + L]
                if sub in conjunto:
                    info = por_seq[sub]
                    hallados.append({
                        "peptido": sub, "inicio": i + 1, "fin": i + L,
                        "alelos": sorted(info["alelos"]), "pmids": sorted(info["pmids"]),
                    })
        return hallados

    # Las proteinas a ventanear son las que aportan al menos un epitopo anotado,
    # igual que el pipeline historico (su lista de proteinas salia del fichero
    # de epitopos). Es tambien la razon de que los senuelos salgan solo de
    # proteinas con epitopos.
    por_proteina = {acc: epitopos_en(seqs[acc]) for acc in sorted(accs_con_epitopo)}
    ocurrencias_totales = sum(len(v) for v in por_proteina.values())

    destino = out_dir / especie / clase / familia
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / "windows.parquet"

    escritor = pq.ParquetWriter(salida, ESQUEMA, compression="zstd")
    # El CSV se escribe EN PARALELO al Parquet, no al final: estas tablas son
    # de millones de filas y releerlas para convertirlas costaria otra pasada
    # completa. El Parquet es lo que consumen los scripts rio abajo; el CSV es
    # la copia inspeccionable a ojo que pidio Laura el 27 nov 2026.
    salida_csv = destino / "windows.csv" if emit_csv else None
    csv_cabecera_escrita = False
    buffer: list[list] = []
    tot = {"ventanas": 0, "descartadas_no_canonico": 0, "positivas": 0,
           "duplicadas_misma_proteina": 0}
    filas_escritas = 0

    def volcar() -> None:
        nonlocal buffer, filas_escritas, csv_cabecera_escrita
        if not buffer:
            return
        df = pd.DataFrame(buffer, columns=[
            "accession", "fragmento", "frag_inicio", "frag_fin", "label", "n_epitopos",
            "epitopos", "alelos", "n_alelos", "epitopo_offset", "epitopo_long",
            "pos_score", "pmids",
        ])
        df.insert(0, "familia", familia)
        df.insert(0, "clase", clase)
        df.insert(0, "especie", especie)
        ordenado = df[[f.name for f in ESQUEMA]]
        escritor.write_table(pa.Table.from_pandas(
            ordenado, schema=ESQUEMA, preserve_index=False))
        if salida_csv is not None:
            ordenado.to_csv(
                salida_csv, index=False,
                mode="w" if not csv_cabecera_escrita else "a",
                header=not csv_cabecera_escrita,
            )
            csv_cabecera_escrita = True
        filas_escritas += len(df)
        buffer = []

    for i, (acc, lista) in enumerate(por_proteina.items(), start=1):
        filas, cont = ventanas_de_proteina(acc, seqs[acc], lista, w, stride)
        for k in tot:
            tot[k] += cont[k]
        buffer.extend(filas)
        if len(buffer) >= FLUSH_FILAS:
            volcar()
        if i % 2000 == 0:
            logging.info("  %s/%s/%s: %d/%d proteinas, %d filas",
                         especie, clase, familia, i, len(por_proteina), filas_escritas + len(buffer))

    volcar()
    escritor.close()

    pos = 0
    for lote in pq.ParquetFile(salida).iter_batches(columns=["label"]):
        pos += int(np.asarray(lote.column("label")).sum())

    res = {
        "familia": f"{especie}/{clase}/{familia}",
        "descartes_del_export": descartes,
        "proteinas": len(por_proteina),
        "epitopos_unicos": int(len(eps)),
        "epitopos_sin_secuencia": sin_secuencia,
        "epitopos_no_hallados_en_la_proteina": coord_invalida,
        "epitopos_mas_largos_que_ventana": no_cabe,
        "epitopos_con_coordenada_iedb_que_no_cuadra": coord_no_cuadra,
        "epitopos_distintos_usables": len(por_seq),
        "ocurrencias_totales_en_las_proteinas": ocurrencias_totales,
        "ventanas_generadas": tot["ventanas"],
        "ventanas_descartadas_no_canonico": tot["descartadas_no_canonico"],
        "filas": filas_escritas,
        "positivas": pos,
        "negativas": filas_escritas - pos,
        "prevalencia": round(pos / filas_escritas, 6) if filas_escritas else 0.0,
        "salida": str(salida),
        "sha256": sha256_fichero(salida),
        "bytes": salida.stat().st_size,
    }
    logging.info("%s: %d filas, %d positivas (%.2f %%)",
                 res["familia"], res["filas"], pos, 100 * res["prevalencia"])
    return res


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", required=True, type=Path,
                    help="salida de slim_raw_export.py --columns core")
    ap.add_argument("--proteins", required=True, type=Path,
                    help="parent_proteins.parquet de fetch_parent_proteins.py")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--window", type=int, default=25)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--csv", action="store_true",
                    help=("escribe tambien el CSV al lado del Parquet. Por omision SOLO "
                          "Parquet (decision de Laura del 27 nov): el CSV se pide cuando "
                          "hace falta mirar las columnas a ojo, y en estas tablas de "
                          "decenas de millones de filas pesa dos ordenes de magnitud mas."))
    ap.add_argument("--keep-modified", action="store_true",
                    help=("conserva los epitopos con modificacion quimica. Por omision "
                          "se descartan: su ventana saldria identica a la del peptido no "
                          "modificado (decision de Laura del 25 nov). Desde el 27 nov el "
                          "filtro vive aqui y no en slim_raw_export.py."))
    ap.add_argument("--only", action="append", default=None,
                    help="especie/clase/familia; repetible")
    args = ap.parse_args()

    prot = pd.read_parquet(args.proteins, columns=["accession", "secuencia"])
    seqs = dict(zip(prot["accession"], prot["secuencia"].astype(str).str.upper()))
    logging.info("proteinas en el almacen: %d", len(seqs))

    familias = []
    for esp_dir in sorted(p for p in args.clean.iterdir() if p.is_dir()):
        for cls_dir in sorted(p for p in esp_dir.iterdir() if p.is_dir()):
            for fam_dir in sorted(p for p in cls_dir.iterdir() if p.is_dir()):
                clave = f"{esp_dir.name}/{cls_dir.name}/{fam_dir.name}"
                if args.only and clave not in args.only:
                    continue
                familias.append((esp_dir.name, cls_dir.name, fam_dir.name))
    logging.info("familias a procesar: %d", len(familias))

    args.out.mkdir(parents=True, exist_ok=True)
    resultados = [
        procesar_familia(args.clean, args.out, seqs, esp, cls, fam, args.window,
                         args.stride, drop_modified=not args.keep_modified,
                         emit_csv=args.csv)
        for esp, cls, fam in familias
    ]

    filas = sum(r.get("filas", 0) for r in resultados)
    pos = sum(r.get("positivas", 0) for r in resultados)
    manifiesto = {
        "generado_por": "data_pipeline/scripts/data_classification/epitope_classification.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": commit_git(),
        "criterio": ("una fila por ventana; label=1 si la ventana contiene entero al "
                     "menos un epitopo, sin importar cuantos"),
        "parametros": {"ventana": args.window, "stride": args.stride,
                       "clean": str(args.clean), "proteins": str(args.proteins)},
        "totales": {"filas": filas, "positivas": pos, "negativas": filas - pos,
                    "prevalencia": round(pos / filas, 6) if filas else 0.0},
        "por_familia": resultados,
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("TOTAL: %d filas, %d positivas (%.2f %%)",
                 filas, pos, 100 * manifiesto["totales"]["prevalencia"])
    logging.info("manifiesto: %s", args.out / "manifest.json")


if __name__ == "__main__":
    main()
