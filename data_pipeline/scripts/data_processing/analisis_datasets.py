#!/usr/bin/env python3
"""Analisis exhaustivo y comparado de dos arboles de descarga IEDB.

Recorre las 113 columnas, mide relleno en ambos, y desglosa las que
tienen contenido informativo. Emite un markdown.
"""
import collections
import glob
import os
import sys

import pandas as pd

# Columnas que no aportan: IRIs, sinonimos y comentarios de texto libre.
IRRELEVANTES = ("__iri", "_iri", "iedb_iri", "__synonyms", "__comments",
                "location_of_assay_data")

CATEGORICAS = [
    "assay__qualitative_measurement", "assay__method", "assay__units",
    "assay__measurement_inequality", "assay__response_measured",
    "mhc_restriction__name", "mhc_restriction__class",
    "mhc_restriction__evidence_code",
    "epitope__object_type", "epitope__source_organism", "epitope__species",
    "epitope__modifications",
    "host__name", "host__mhc_types_present", "host__sex", "host__geolocation",
    "antigen_presenting_cell__name", "antigen_presenting_cell__source_tissue",
    "in_vivo_process__disease", "in_vivo_process__disease_stage",
    "in_vivo_process__process_type", "in_vitro_process__process_type",
    "in_vitro_process__epitope_relation", "in_vivo_antigen__epitope_relation",
    "in_vivo_antigen__route", "in_vivo_antigen__adjuvants",
    "reference__type", "reference__journal",
]

UNICOS = ["epitope__name", "epitope__molecule_parent", "epitope__source_molecule",
          "reference__pmid", "mhc_restriction__name", "assay_id"]


def recorrer(root):
    """Devuelve (relleno, categorias, unicos, por_familia, longitudes, nm)."""
    relleno = collections.Counter()
    filas = 0
    cat = {c: collections.Counter() for c in CATEGORICAS}
    uni = {c: set() for c in UNICOS}
    fam_stats = {}
    longs = collections.Counter()
    nm = collections.Counter()
    nm_vals = []
    columnas = None

    for d in sorted(glob.glob(root + "/*/*/*")):
        if not os.path.isdir(d):
            continue
        familia = "/".join(d.split("/")[-3:])
        f = collections.Counter()
        for ex in ("mhc", "tcell"):
            p = os.path.join(d, "%s_export_full.csv" % ex)
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                continue
            df = pd.read_csv(p, dtype=str, low_memory=False)
            if columnas is None:
                columnas = list(df.columns)
            filas += len(df)
            f["filas"] += len(df)
            f["filas_" + ex] += len(df)

            for c in df.columns:
                relleno[c] += int(df[c].notna().sum())

            for c in CATEGORICAS:
                if c in df:
                    cat[c].update(df[c].dropna().str.strip().value_counts().to_dict())

            for c in UNICOS:
                if c in df:
                    uni[c].update(df[c].dropna().str.strip().unique())

            q = df.get("assay__qualitative_measurement", pd.Series(dtype=str)).fillna("")
            for tier in ("Positive", "Positive-High", "Positive-Intermediate",
                         "Positive-Low", "Negative"):
                f["tier::" + tier] += int((q == tier).sum())

            pep = df.get("epitope__name", pd.Series(dtype=str)).dropna().str.strip()
            longs.update(pep.str.len().value_counts().to_dict())
            f["peptidos"] = f.get("peptidos", 0)

            u = df.get("assay__units", pd.Series(dtype=str)).fillna("").str.strip()
            mask = u == "nM"
            nm["filas"] += int(mask.sum())
            if mask.any():
                v = pd.to_numeric(df.loc[mask, "assay__quantitative_measurement"],
                                  errors="coerce").dropna()
                nm_vals.extend(v.tolist())
                nm.update(df.loc[mask, "assay__qualitative_measurement"]
                          .fillna("<vacio>").value_counts().to_dict())

            al = df.get("mhc_restriction__name", pd.Series(dtype=str)).dropna()
            f["alelos"] = len(set(f.get("_al", set())) | set(al.unique()))
            f["_al"] = set(f.get("_al", set())) | set(al.unique())

            del df
        f.pop("_al", None)
        fam_stats[familia] = dict(f)
    return {"filas": filas, "relleno": relleno, "columnas": columnas, "cat": cat,
            "uni": {k: len(v) for k, v in uni.items()}, "fam": fam_stats,
            "longs": longs, "nm": nm, "nm_vals": nm_vals}


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def tabla_cat(fh, titulo, clave, A, B, top=18, nota=None):
    ka = A["cat"][clave]
    kb = B["cat"][clave]
    if not ka and not kb:
        return
    fh.write("#### `%s`\n\n" % clave)
    if nota:
        fh.write("%s\n\n" % nota)
    claves = sorted(set(ka) | set(kb), key=lambda k: -(kb.get(k, 0) + ka.get(k, 0)))
    fh.write("| Valor | Histórico | % | Nuevo `full` | % |\n|---|---:|---:|---:|---:|\n")
    for k in claves[:top]:
        fh.write("| `%s` | %s | %.2f%% | %s | %.2f%% |\n" % (
            str(k)[:58], f"{ka.get(k,0):,}", pct(ka.get(k, 0), A["filas"]),
            f"{kb.get(k,0):,}", pct(kb.get(k, 0), B["filas"])))
    resto_a = sum(ka.get(k, 0) for k in claves[top:])
    resto_b = sum(kb.get(k, 0) for k in claves[top:])
    if resto_a or resto_b:
        fh.write("| *(otros %d valores)* | %s | %.2f%% | %s | %.2f%% |\n" % (
            len(claves) - top, f"{resto_a:,}", pct(resto_a, A["filas"]),
            f"{resto_b:,}", pct(resto_b, B["filas"])))
    fh.write("\n**Valores distintos:** histórico %d · nuevo %d\n\n" % (len(ka), len(kb)))


def main(root_a, root_b, salida):
    print("recorriendo historico...", flush=True)
    A = recorrer(root_a)
    print("recorriendo nuevo...", flush=True)
    B = recorrer(root_b)

    with open(salida, "w", encoding="utf-8") as fh:
        fh.write("# Análisis comparado de los dos datasets IEDB\n\n")
        fh.write("**Fecha:** 24 de noviembre de 2026. Recorre las **113 columnas** "
                 "de ambos árboles y desglosa las informativas.\n\n")
        fh.write("| | Histórico | Nuevo `full` |\n|---|---|---|\n")
        fh.write("| Origen | `data/used_data/data_raw.tar.zst` (10 nov 2026) | "
                 "`data/data_raw_full_20261124` (24 nov 2026) |\n")
        fh.write("| Qué alimentó | **`data_input_nn` y todo el pipeline histórico** | "
                 "Nada todavía |\n")
        fh.write("| Filtro cualitativo | `ilike.*Positive*` | **ninguno** |\n")
        fh.write("| Filtro de organismo fuente | `ilike.*<especie>*` | **ninguno** |\n")
        fh.write("| **Filas** | **%s** | **%s** |\n\n" % (f"{A['filas']:,}", f"{B['filas']:,}"))

        # --- 1. Etiqueta
        fh.write("---\n\n## 1. La etiqueta: positivos y negativos\n\n")
        fh.write("| Tipo de resultado | Histórico | % | Nuevo `full` | % |\n|---|---:|---:|---:|---:|\n")
        for tier in ("Positive", "Positive-High", "Positive-Intermediate",
                     "Positive-Low", "Negative"):
            a = A["cat"]["assay__qualitative_measurement"].get(tier, 0)
            b = B["cat"]["assay__qualitative_measurement"].get(tier, 0)
            marca = "**" if tier == "Negative" else ""
            fh.write("| %s`%s`%s | %s%s%s | %.2f%% | %s%s%s | %.2f%% |\n" % (
                marca, tier, marca, marca, f"{a:,}", marca, pct(a, A["filas"]),
                marca, f"{b:,}", marca, pct(b, B["filas"])))
        pa = sum(v for k, v in A["cat"]["assay__qualitative_measurement"].items()
                 if k.startswith("Positive"))
        pb = sum(v for k, v in B["cat"]["assay__qualitative_measurement"].items()
                 if k.startswith("Positive"))
        na = A["cat"]["assay__qualitative_measurement"].get("Negative", 0)
        nb = B["cat"]["assay__qualitative_measurement"].get("Negative", 0)
        fh.write("| **TOTAL positivas** | **%s** | %.2f%% | **%s** | %.2f%% |\n" % (
            f"{pa:,}", pct(pa, A["filas"]), f"{pb:,}", pct(pb, B["filas"])))
        fh.write("\n> El histórico tiene **%s negativos**. No es que tenga pocos: el "
                 "filtro `ilike.*Positive*` los excluía por construcción. "
                 "El nuevo trae **%s**, el %.1f %% de sus filas.\n\n" % (
                     f"{na:,}", f"{nb:,}", pct(nb, B["filas"])))

        # --- 2. Por familia
        fh.write("---\n\n## 2. Desglose por familia MHC\n\n")
        for etiqueta, D in (("Histórico", A), ("Nuevo `full`", B)):
            fh.write("### %s\n\n" % etiqueta)
            fh.write("| Familia | Filas | `mhc` | `tcell` | Positive | Pos-High | "
                     "Pos-Int | Pos-Low | **Negative** | Alelos |\n")
            fh.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
            for fam, s in sorted(D["fam"].items(), key=lambda x: -x[1].get("filas", 0)):
                fh.write("| %s | %s | %s | %s | %s | %s | %s | %s | **%s** | %s |\n" % (
                    fam, f"{s.get('filas',0):,}", f"{s.get('filas_mhc',0):,}",
                    f"{s.get('filas_tcell',0):,}",
                    f"{s.get('tier::Positive',0):,}", f"{s.get('tier::Positive-High',0):,}",
                    f"{s.get('tier::Positive-Intermediate',0):,}",
                    f"{s.get('tier::Positive-Low',0):,}",
                    f"{s.get('tier::Negative',0):,}", s.get("alelos", 0)))
            fh.write("\n")

        # --- 3. Columnas informativas
        fh.write("---\n\n## 3. Qué columnas traen información\n\n")
        fh.write("Relleno de las 113 columnas. Se omiten IRIs, sinónimos y comentarios.\n\n")
        fh.write("| Columna | Histórico | Nuevo `full` |\n|---|---:|---:|\n")
        cols = [c for c in (A["columnas"] or []) if not any(x in c for x in IRRELEVANTES)]
        for c in sorted(cols, key=lambda c: -pct(B["relleno"].get(c, 0), B["filas"])):
            ra, rb = pct(A["relleno"].get(c, 0), A["filas"]), pct(B["relleno"].get(c, 0), B["filas"])
            if ra < 0.01 and rb < 0.01:
                continue
            fh.write("| `%s` | %.2f%% | %.2f%% |\n" % (c, ra, rb))
        vacias = [c for c in cols
                  if pct(A["relleno"].get(c, 0), A["filas"]) < 0.01
                  and pct(B["relleno"].get(c, 0), B["filas"]) < 0.01]
        fh.write("\n**Vacías en ambos (%d):** %s\n\n" % (
            len(vacias), ", ".join("`%s`" % c for c in vacias) or "ninguna"))

        # --- 4. Categoricas
        fh.write("---\n\n## 4. Desglose de cada columna categórica\n\n")
        fh.write("### 4.1. El ensayo\n\n")
        tabla_cat(fh, "", "assay__method", A, B, top=22,
                  nota="Qué técnica se usó. Determina **qué se está midiendo**: "
                       "presentación, unión o respuesta de célula T.")
        tabla_cat(fh, "", "assay__units", A, B, top=8)
        tabla_cat(fh, "", "assay__measurement_inequality", A, B, top=6)
        tabla_cat(fh, "", "assay__response_measured", A, B, top=12)
        tabla_cat(fh, "", "in_vitro_process__process_type", A, B, top=10)
        tabla_cat(fh, "", "in_vivo_process__process_type", A, B, top=10)

        fh.write("### 4.2. El alelo MHC\n\n")
        tabla_cat(fh, "", "mhc_restriction__class", A, B, top=4)
        tabla_cat(fh, "", "mhc_restriction__evidence_code", A, B, top=14,
                  nota="**Cómo se atribuyó el alelo.** `Single allele present` es "
                       "atribución directa; `prediction` significa que lo puso un "
                       "modelo, no un experimento.")
        tabla_cat(fh, "", "mhc_restriction__name", A, B, top=25,
                  nota="Los 25 alelos más frecuentes.")

        fh.write("### 4.3. El epítopo\n\n")
        tabla_cat(fh, "", "epitope__object_type", A, B, top=6)
        tabla_cat(fh, "", "epitope__source_organism", A, B, top=25,
                  nota="**El origen del péptido.** Aquí es donde los dos datasets "
                       "divergen por completo.")
        tabla_cat(fh, "", "epitope__species", A, B, top=14)
        tabla_cat(fh, "", "epitope__modifications", A, B, top=10)

        fh.write("### 4.4. El hospedador y el contexto\n\n")
        tabla_cat(fh, "", "host__name", A, B, top=14)
        tabla_cat(fh, "", "host__mhc_types_present", A, B, top=8)
        tabla_cat(fh, "", "host__sex", A, B, top=5)
        tabla_cat(fh, "", "antigen_presenting_cell__name", A, B, top=12)
        tabla_cat(fh, "", "antigen_presenting_cell__source_tissue", A, B, top=10)
        tabla_cat(fh, "", "in_vivo_process__disease", A, B, top=14)
        tabla_cat(fh, "", "in_vivo_antigen__route", A, B, top=8)
        tabla_cat(fh, "", "in_vivo_antigen__adjuvants", A, B, top=8)

        fh.write("### 4.5. La referencia bibliográfica\n\n")
        tabla_cat(fh, "", "reference__type", A, B, top=6)
        tabla_cat(fh, "", "reference__journal", A, B, top=12)

        # --- 5. Cardinalidades
        fh.write("---\n\n## 5. Cardinalidades\n\n")
        fh.write("| Qué | Histórico | Nuevo `full` | Cambio |\n|---|---:|---:|---:|\n")
        nombres = {"epitope__name": "Péptidos únicos",
                   "mhc_restriction__name": "Alelos distintos",
                   "epitope__molecule_parent": "Proteínas madre únicas",
                   "epitope__source_molecule": "Moléculas fuente únicas",
                   "reference__pmid": "Publicaciones (PMID)",
                   "assay_id": "Ensayos únicos"}
        for c, nom in nombres.items():
            a, b = A["uni"].get(c, 0), B["uni"].get(c, 0)
            fh.write("| %s | %s | %s | %s |\n" % (
                nom, f"{a:,}", f"{b:,}", "×%.2f" % (b / a) if a else "—"))
        fh.write("\n")

        # --- 6. Longitudes
        fh.write("---\n\n## 6. Longitud del péptido\n\n")
        fh.write("| Longitud | Histórico | % | Nuevo `full` | % |\n|---|---:|---:|---:|---:|\n")
        ta, tb = sum(A["longs"].values()), sum(B["longs"].values())
        for L in sorted(set(A["longs"]) | set(B["longs"])):
            if L > 30:
                continue
            a, b = A["longs"].get(L, 0), B["longs"].get(L, 0)
            if a + b == 0:
                continue
            marca = "**" if 8 <= L <= 11 else ""
            fh.write("| %s%d aa%s | %s | %.2f%% | %s | %.2f%% |\n" % (
                marca, L, marca, f"{a:,}", pct(a, ta), f"{b:,}", pct(b, tb)))
        la = sum(v for k, v in A["longs"].items() if k > 30)
        lb = sum(v for k, v in B["longs"].items() if k > 30)
        fh.write("| > 30 aa | %s | %.2f%% | %s | %.2f%% |\n" % (
            f"{la:,}", pct(la, ta), f"{lb:,}", pct(lb, tb)))
        a8 = sum(v for k, v in A["longs"].items() if 8 <= k <= 11)
        b8 = sum(v for k, v in B["longs"].items() if 8 <= k <= 11)
        fh.write("\n**Rango canónico de MHC-I (8–11 aa):** histórico %.1f %% · "
                 "nuevo %.1f %%\n\n" % (pct(a8, ta), pct(b8, tb)))

        # --- 7. Afinidad
        fh.write("---\n\n## 7. Afinidad cuantitativa\n\n")
        fh.write("| | Histórico | Nuevo `full` |\n|---|---:|---:|\n")
        fh.write("| Filas con medida en nM | %s | **%s** |\n" % (
            f"{A['nm'].get('filas',0):,}", f"{B['nm'].get('filas',0):,}"))
        fh.write("| %% del total | %.2f%% | %.2f%% |\n" % (
            pct(A["nm"].get("filas", 0), A["filas"]), pct(B["nm"].get("filas", 0), B["filas"])))
        for d, k in ((A, "a"), (B, "b")):
            pass
        fh.write("\n**Reparto por etiqueta de las filas con nM:**\n\n")
        fh.write("| Etiqueta | Histórico | Nuevo `full` |\n|---|---:|---:|\n")
        for k in sorted(set(A["nm"]) | set(B["nm"]), key=lambda k: -B["nm"].get(k, 0)):
            if k == "filas":
                continue
            fh.write("| `%s` | %s | %s |\n" % (k, f"{A['nm'].get(k,0):,}", f"{B['nm'].get(k,0):,}"))
        for nombre, vals in (("Histórico", A["nm_vals"]), ("Nuevo", B["nm_vals"])):
            if vals:
                s = pd.Series(vals)
                fh.write("\n**%s** — mediana %.1f nM, p25 %.1f, p75 %.1f, "
                         "mín %.2f, máx %.0f, n=%s\n" % (
                             nombre, s.median(), s.quantile(.25), s.quantile(.75),
                             s.min(), s.max(), f"{len(s):,}"))
        fh.write("\n")
    print("escrito", salida)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
