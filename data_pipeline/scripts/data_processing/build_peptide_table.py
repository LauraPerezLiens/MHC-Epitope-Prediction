#!/usr/bin/env python3
"""Procesado de una descarga IEDB a tabla canonica por PEPTIDO Y ALELO.

Que hace, y por que esta estructurado asi:

El pipeline historico iba de IEDB a ventanas de 25 aa en un solo paso, y
por el camino tiraba casi toda la informacion del ensayo: el alelo
quedaba colapsado en 11 etiquetas de familia, el metodo de ensayo y el
codigo de evidencia no se leian, y el PMID tampoco. Este script hace el
paso intermedio que faltaba: deja una tabla con UNA FILA POR
(alelo, peptido) y todas las covariables necesarias para decidir despues
que subconjunto define la tarea, sin volver a descargar nada.

No decide la tarea. Anota, clasifica y marca contradicciones. Las
decisiones (que alelos, que metodos, que evidencia, que longitudes)
quedan como filtros aplicables sobre la salida.

Columnas de salida y para que sirve cada una:

  allele_raw / allele_norm      alelo literal de IEDB y normalizado al
                                vocabulario de NetMHCpan.
  allele_resolution             4digit | serotype | mutant | other.
                                Los serotipos (HLA-A2...) no son alelos:
                                2,5 % de HLA-A, descartables.
  pseudosequence                34 aa del surco de union, de NetMHCpan.
                                ES LA COLUMNA QUE PERMITE PROBAR si meter
                                el alelo en la entrada mejora la red
                                (prioridad 0.5.3). Solo clase I: la tabla
                                de referencia no cubre clase II.
  label / label_tier            1/0 y el valor cualitativo original.
                                Positive-High/-Low/-Intermediate se
                                colapsan a 1 pero el matiz se conserva.
  assay_class                   elution_ms | binding | tcell | structural
                                | other. El 97,5 % de H2-K es elucion por
                                espectrometria: el dataset mide
                                PRESENTACION, no afinidad. Comparar con
                                NetMHCpan exige elegir su modelo de
                                ligando eluido, no el de afinidad.
  allele_evidence_class         direct | antibody | inferred | none.
                                En H2-K solo el 0,7 % es `direct`; el
                                95,9 % atribuye el alelo por el anticuerpo
                                de elucion, que no distingue alelos de la
                                misma familia. En HLA-A el 42,7 % es
                                inferencia por motivo, o sea un predictor:
                                entrenar sobre esas filas es circular.
  affinity_nm                   solo 0,16-0,68 % de relleno. Inservible
                                para regresion; se conserva por si acaso.
  parent_accession, start, end  proteina madre y coordenadas, para
                                reconstruir ventanas o negativos del mismo
                                proteoma.
  pmid                          eje de fuga NO cubierto por la particion
                                por proteina: 89 PMIDs para 87.593 filas
                                de H2-K. Un solo estudio aporta decenas de
                                miles de filas con el mismo sesgo tecnico.
  n_assays, conflicting         trazabilidad de la agregacion y marca de
                                contradiccion (mismo peptido y alelo con
                                ensayos positivos Y negativos).

Uso:
    python build_peptide_table.py --raw data/data_raw_20261124 \\
        --out data/peptide_table_20261124 [--only mouse/mhc-I/H2-K]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import pandas as pd

PSEUDO_DEFAULT = Path("/data/nap/lperez_nn/reference/pseudosequences/"
                      "pseudosequences.netmhcpan.34aa.csv")

USED_COLUMNS = [
    "assay_id", "epitope__name", "mhc_restriction__name",
    "mhc_restriction__class", "mhc_restriction__evidence_code",
    "assay__method", "assay__qualitative_measurement",
    "assay__quantitative_measurement", "assay__units",
    "assay__measurement_inequality", "epitope__molecule_parent",
    "epitope__source_molecule", "epitope__source_organism",
    "epitope__starting_position", "epitope__ending_position",
    "reference__pmid", "host__name",
]

log = logging.getLogger("peptides")


# --------------------------------------------------------------------------
# Normalizacion de alelo al vocabulario de NetMHCpan
# --------------------------------------------------------------------------
def normalize_allele(name: str) -> str | None:
    """IEDB -> NetMHCpan. HLA-A*02:01 -> HLA-A0201; H2-Kb -> H-2-Kb.

    Devuelve None si no es un alelo nombrable (serotipo, mutante, vacio).
    """
    if not isinstance(name, str) or not name.strip():
        return None
    value = name.strip()
    if "mutant" in value.lower():
        return None

    # Clase I humana de cuatro digitos: HLA-A*02:01 -> HLA-A0201
    match = re.fullmatch(r"HLA-([ABCEG])\*(\d+):(\d+)", value)
    if match:
        return "HLA-%s%s%s" % (match.group(1), match.group(2), match.group(3))

    # Raton: H2-Kb -> H-2-Kb
    match = re.fullmatch(r"H2-([A-Za-z0-9]+)", value)
    if match:
        return "H-2-%s" % match.group(1)

    return None


def allele_resolution(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        return "missing"
    value = name.strip()
    if "mutant" in value.lower():
        return "mutant"
    if re.fullmatch(r"HLA-[A-Z]+\*\d+:\d+", value):
        return "4digit"
    if re.fullmatch(r"HLA-[A-Z]+\*\d+", value):
        return "2digit"
    if re.fullmatch(r"HLA-[A-Z]+\d+", value):
        return "serotype"
    if re.fullmatch(r"H2-[A-Za-z0-9]+", value):
        return "4digit"  # el raton no tiene resolucion de 4 digitos: Kb ya es el alelo
    return "other"


# --------------------------------------------------------------------------
# Clasificacion de ensayo y de evidencia
# --------------------------------------------------------------------------
def assay_class(method: str) -> str:
    """Agrupa los metodos de IEDB en lo que realmente miden.

    `mhc_export` y `tcell_export` usan vocabularios DISTINTOS y hay que
    cubrir los dos: el primero habla de elucion y union competitiva, el
    segundo de ELISPOT, ICS, 51-cromo, tetrameros... Las tres cosas que
    se miden no son intercambiables como objetivo supervisado:

      elution_ms       presentacion (el peptido estaba en la superficie)
      binding          afinidad de union al MHC
      tcell_functional inmunogenicidad (el linfocito respondio)

    Mezclarlas en una sola etiqueta binaria es una de las razones de que
    la tarea actual sea difusa.
    """
    if not isinstance(method, str) or not method.strip():
        return "unknown"
    text = method.lower()

    # Primero los ensayos funcionales de celula T: algunos nombres
    # contienen tambien "cellular MHC" y se clasificarian mal.
    if any(k in text for k in (
            "t cell", "elispot", "ics", "elisa", "chromium", "multimer",
            "tetramer", "thymidine", "brdu", "in vivo assay", "in vitro assay",
            "biological activity", "bioassay", "proliferation", "cytotox",
            "interferon", "cytokine", "limiting dilution",
            # Vistos en el perfil completo del 24 nov 2026:
            "cytometric bead array", "cfse", "intracellular staining",
            "reporter gene", "skin test")):
        return "tcell_functional"
    # "High throughput multiplexed assay" son 468.553 filas del perfil `full`:
    # es union multiplexada y sin esta regla caia en "other", el 15 % del total.
    if "multiplexed" in text or "high throughput" in text:
        return "binding"
    if any(k in text for k in ("mass spectrometry", "coelution", "edman")):
        return "elution_ms"
    if "crystallograph" in text or "nmr" in text:
        return "structural"
    if any(k in text for k in (
            "competitive", "direct", "binding", "purified mhc", "cellular mhc",
            "plasmon", "spr", "fluorescence", "radioactivity")):
        return "binding"
    return "other"


def evidence_class(code: str) -> str:
    """Como se atribuyo el alelo a la fila. Decide si la etiqueta es medida.

    Las dos categorias que importan para la honestidad del dataset:

      direct      un solo alelo presente: atribucion inequivoca.
      prediction  el alelo lo asigno un PREDICTOR de union. Entrenar
                  sobre estas filas es circular: el modelo aprende la
                  salida de otro modelo, no un hecho experimental.
    """
    if not isinstance(code, str) or not code.strip():
        return "none"
    text = code.lower()
    if "single allele present" in text:
        return "direct"
    if "elution with mhc specific antibody" in text:
        return "antibody"
    if "prediction" in text:
        return "prediction"          # circularidad: lo puso un modelo
    if "inferred" in text:
        return "inferred_motif"
    if "binding assay" in text:
        return "binding_assay"
    if "t cell assay" in text:
        return "tcell_assay"
    if "cited reference" in text:
        return "cited"
    if "not determined" in text:
        return "not_determined"
    return "other"


def qualitative_label(value: str) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().lower()
    if text.startswith("positive"):
        return 1
    if text.startswith("negative"):
        return 0
    return None


# --------------------------------------------------------------------------
def load_pseudosequences(path: Path) -> dict[str, str]:
    table = pd.read_csv(path, dtype=str)
    return dict(zip(table["allele"].str.strip(), table["pseudosequence"].str.strip()))


def families(root: Path) -> list[str]:
    return sorted("/".join(p.parts[-3:]) for p in root.glob("*/*/*") if p.is_dir())


def load_raw(root: Path, family: str) -> pd.DataFrame:
    """Une mhc_export y tcell_export de una familia, anotando la procedencia."""
    frames = []
    for export in ("mhc", "tcell"):
        path = root / family / ("%s_export_full.csv" % export)
        if not path.exists() or path.stat().st_size == 0:
            continue
        frame = pd.read_csv(path, dtype=str, low_memory=False,
                            usecols=lambda c: c in USED_COLUMNS)
        frame["export"] = export
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def annotate(frame: pd.DataFrame, family: str, pseudo: dict[str, str]) -> pd.DataFrame:
    species, mhc_class, family_name = family.split("/")
    out = pd.DataFrame(index=frame.index)

    out["species"] = species
    out["mhc_class"] = mhc_class
    out["family"] = family_name          # solo enumeracion, NO etiqueta
    out["export"] = frame["export"]
    out["assay_id"] = frame.get("assay_id")

    out["peptide"] = frame["epitope__name"].str.strip().str.upper()
    out["peptide_len"] = out["peptide"].str.len()
    # El alfabeto importa: IEDB trae modificaciones y no-peptidos.
    out["peptide_canonical"] = out["peptide"].str.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]+")

    out["allele_raw"] = frame["mhc_restriction__name"].str.strip()
    out["allele_resolution"] = out["allele_raw"].map(allele_resolution)
    out["allele_norm"] = out["allele_raw"].map(normalize_allele)
    out["pseudosequence"] = out["allele_norm"].map(lambda a: pseudo.get(a) if a else None)

    out["label"] = frame["assay__qualitative_measurement"].map(qualitative_label)
    out["label_tier"] = frame["assay__qualitative_measurement"].str.strip()

    out["assay_method"] = frame["assay__method"].str.strip()
    out["assay_class"] = out["assay_method"].map(assay_class)
    out["allele_evidence_code"] = frame.get("mhc_restriction__evidence_code")
    out["allele_evidence_class"] = out["allele_evidence_code"].map(evidence_class)

    affinity = pd.to_numeric(frame.get("assay__quantitative_measurement"),
                             errors="coerce")
    units = frame.get("assay__units")
    # Solo tiene sentido en nM; el resto son angstroms, minutos, grados.
    out["affinity_nm"] = affinity.where(units.astype(str).str.strip() == "nM")
    out["affinity_inequality"] = frame.get("assay__measurement_inequality")

    out["source_organism"] = frame.get("epitope__source_organism")
    host = frame.get("host__name").astype(str)
    out["source_is_self"] = [
        bool(o) and isinstance(o, str) and o.split()[0] in h
        for o, h in zip(out["source_organism"].fillna(""), host)
    ]
    out["parent_accession"] = frame.get("epitope__molecule_parent")
    out["source_molecule"] = frame.get("epitope__source_molecule")
    out["start_pos"] = pd.to_numeric(frame.get("epitope__starting_position"),
                                     errors="coerce")
    out["end_pos"] = pd.to_numeric(frame.get("epitope__ending_position"),
                                   errors="coerce")
    out["pmid"] = frame.get("reference__pmid")
    return out


def aggregate(frame: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (alelo literal, peptido). Marca las contradicciones.

    Agrupa por `allele_raw`, no por `allele_norm`: perder los serotipos en
    la agrupacion los fundiria con alelos reales. La decision de
    descartarlos se toma luego, con la columna de resolucion.
    """
    labelled = frame[frame["label"].notna()].copy()
    if labelled.empty:
        return pd.DataFrame()

    grouped = labelled.groupby(["allele_raw", "peptide"], dropna=False, sort=False)
    out = grouped.agg(
        n_assays=("label", "size"),
        n_positive=("label", "sum"),
        label_tiers=("label_tier", lambda s: "|".join(sorted(set(s.dropna())))),
        assay_classes=("assay_class", lambda s: "|".join(sorted(set(s.dropna())))),
        evidence_classes=("allele_evidence_class",
                          lambda s: "|".join(sorted(set(s.dropna())))),
        exports=("export", lambda s: "|".join(sorted(set(s)))),
        pmids=("pmid", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
        n_pmids=("pmid", lambda s: s.dropna().nunique()),
        affinity_nm_min=("affinity_nm", "min"),
        # first() de los campos constantes por peptido/alelo
        species=("species", "first"),
        mhc_class=("mhc_class", "first"),
        family=("family", "first"),
        peptide_len=("peptide_len", "first"),
        peptide_canonical=("peptide_canonical", "first"),
        allele_resolution=("allele_resolution", "first"),
        allele_norm=("allele_norm", "first"),
        pseudosequence=("pseudosequence", "first"),
        parent_accession=("parent_accession", "first"),
        source_molecule=("source_molecule", "first"),
        source_organism=("source_organism", "first"),
        source_is_self=("source_is_self", "first"),
        start_pos=("start_pos", "min"),
        end_pos=("end_pos", "max"),
        assay_ids=("assay_id", lambda s: "|".join(sorted(set(s.dropna().astype(str))))[:2000]),
    ).reset_index()

    out["n_negative"] = out["n_assays"] - out["n_positive"]
    # Contradiccion: el MISMO peptido con el MISMO alelo medido positivo y
    # negativo. Esto es ruido de etiqueta real, no artefacto del colapso
    # por familia, y hay que cuantificarlo antes de entrenar.
    out["conflicting"] = (out["n_positive"] > 0) & (out["n_negative"] > 0)
    # Voto mayoritario; los empates se resuelven a positivo y quedan
    # marcados por `conflicting` para poder excluirlos.
    out["label"] = (out["n_positive"] >= out["n_negative"]).astype(int)
    out.loc[out["n_positive"] == 0, "label"] = 0
    return out


def summarize(table: pd.DataFrame, family: str) -> dict:
    total = len(table)
    if total == 0:
        return {"familia": family, "filas": 0}
    pct = lambda n: round(100.0 * n / total, 2)
    return {
        "familia": family,
        "filas_peptido_alelo": total,
        "peptidos_unicos": int(table["peptide"].nunique()),
        "alelos_distintos": int(table["allele_raw"].nunique()),
        "positivos": int((table["label"] == 1).sum()),
        "negativos": int((table["label"] == 0).sum()),
        "prevalencia_pct": pct(int((table["label"] == 1).sum())),
        "contradictorios": int(table["conflicting"].sum()),
        "contradictorios_pct": pct(int(table["conflicting"].sum())),
        "con_pseudosecuencia": int(table["pseudosequence"].notna().sum()),
        "con_pseudosecuencia_pct": pct(int(table["pseudosequence"].notna().sum())),
        "no_canonicos": int((~table["peptide_canonical"].fillna(False)).sum()),
        "con_accession": int(table["parent_accession"].notna().sum()),
        "pmids_distintos": int(pd.unique(
            table["pmids"].dropna().str.split("|").explode().dropna()).size),
        "resolucion_alelo": table["allele_resolution"].value_counts().to_dict(),
        "clase_ensayo": pd.Series(
            table["assay_classes"].str.split("|").explode()).value_counts().to_dict(),
        "clase_evidencia": pd.Series(
            table["evidence_classes"].str.split("|").explode()).value_counts().to_dict(),
        "longitudes_8_11_pct": pct(int(table["peptide_len"].between(8, 11).sum())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--pseudo", type=Path, default=PSEUDO_DEFAULT)
    parser.add_argument("--only", action="append", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s: %(message)s")

    pseudo = load_pseudosequences(args.pseudo)
    log.info("pseudosecuencias cargadas: %d alelos", len(pseudo))

    args.out.mkdir(parents=True, exist_ok=True)
    targets = args.only or families(args.raw)
    summaries = []

    for family in targets:
        frame = load_raw(args.raw, family)
        if frame.empty:
            log.warning("%s: sin datos", family)
            continue
        annotated = annotate(frame, family, pseudo)
        table = aggregate(annotated)
        if table.empty:
            log.warning("%s: sin filas con etiqueta", family)
            continue

        destination = args.out / family
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / "peptides.parquet"
        table.to_parquet(path, index=False)

        summary = summarize(table, family)
        summaries.append(summary)
        log.info("%s: %d filas (%d peptidos, %d alelos), prev=%.2f%%, "
                 "contradictorios=%d, pseudosec=%.1f%%",
                 family, summary["filas_peptido_alelo"], summary["peptidos_unicos"],
                 summary["alelos_distintos"], summary["prevalencia_pct"],
                 summary["contradictorios"], summary["con_pseudosecuencia_pct"])

    report = args.out / "summary.json"
    report.write_text(json.dumps(summaries, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    log.info("-> resumen en %s", report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
