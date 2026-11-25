#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
slim_raw_export.py — Proyeccion de columnas sobre los CSV crudos de IEDB.

QUE HACE, Y SOBRE TODO QUE NO HACE
----------------------------------
Es un paso de LIMPIEZA DE COLUMNAS, no de filtrado de filas.

  * NO elimina ninguna fila. El numero de filas de la salida es identico al de
    la entrada, y el script lo verifica y lo aborta si no coincide.
  * NO aplica ningun criterio cientifico: no filtra por `Positive`, ni por
    organismo fuente, ni por `object_type`, ni por codigo de evidencia. Todas
    esas decisiones se toman despues, sobre la tabla de peptidos
    (`build_peptide_table.py`), con los datos delante.
  * SOLO descarta columnas que no aportan informacion: constantes por
    construccion de la consulta, vacias en todas las familias, o duplicados IRI
    de una columna legible que ya se conserva.

La lista de columnas que se conservan es CURADA Y FIJA, no se deriva de la tasa
de relleno de un fichero concreto. Motivo: una columna vacia en H2-K puede estar
rellena en HLA-A o en clase II. Decidir por fichero produciria esquemas
distintos por familia e imposibilitaria concatenarlos.

El criterio de inclusion es deliberadamente generoso: "puede interesar en el
futuro" basta para conservar una columna. Adelgazar de 113 a ~50 columnas ya
reduce el volumen en un orden de magnitud; apurar mas no compensa el riesgo de
tirar algo que luego haga falta volver a descargar.

PROCEDENCIA
-----------
Escribe un `manifest_slim.json` con, por fichero: filas de entrada y de salida,
columnas conservadas con su tasa de relleno y cardinalidad, columnas descartadas
con el motivo, SHA-256 y bytes de entrada y salida, y el commit de git.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u data_pipeline/scripts/data_processing/slim_raw_export.py \
        --raw data/data_raw_full_20261124 \
        --out data/data_raw_full_20261124_slim

    # una sola familia, y en CSV en lugar de Parquet:
    $P -u ... --only mouse/mhc-I/H2-K --format csv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Columnas que se conservan de `mhc_export`.
#
# Cada bloque lleva el motivo por el que se conserva. Las tasas de relleno que
# se citan son de H2-K (94.689 filas) y son orientativas: la decision es
# conceptual, no estadistica.
# --------------------------------------------------------------------------- #
KEEP_MHC: dict[str, list[str]] = {
    # Claves. `assay_id` es unico y es la clave de procedencia y deduplicacion;
    # `epitope__epitope_iri` es el id estable del epitopo, mejor clave de join
    # que la secuencia (dos epitopos distintos pueden compartir secuencia).
    "claves": [
        "assay_id",
        "epitope__epitope_iri",
    ],
    # El peptido. `modifications` marca 8,6 % de filas (oxidacion 7.542,
    # cisteinilacion 413): un peptido modificado no es el mismo objeto quimico
    # y hay que poder excluirlo o tratarlo aparte.
    "peptido": [
        "epitope__name",
        "epitope__reference_name",
        "epitope__modifications",
        "epitope__modified_residues",
        "epitope__comments",
    ],
    # Proteina madre y coordenadas. `molecule_parent_iri` lleva el accession de
    # UniProt, que es lo que permite descargar el FASTA; `molecule_parent` es
    # solo el nombre y no sirve para eso. Los tres (parent + start + end) estan
    # a la vez en el 98,22 % de las filas: es el requisito para reconstruir
    # ventanas y para generar senuelos del mismo proteoma.
    "proteina_madre": [
        "epitope__molecule_parent",
        "epitope__molecule_parent_iri",
        "epitope__source_molecule",
        "epitope__source_molecule_iri",
        "epitope__starting_position",
        "epitope__ending_position",
    ],
    # Origen del epitopo. Se conservan las DOS: `species` es el taxon agregado
    # (122 valores) y es lo que hay que usar para `source_is_self`, porque
    # agrupa las cepas; `source_organism` es la cepa (231 valores) y es lo que
    # hace falta para desglosar patogenos.
    "origen": [
        "epitope__source_organism",
        "epitope__species",
    ],
    # Alelo literal y COMO se le atribuyo. El codigo de evidencia es obligatorio
    # para excluir filas circulares (alelo asignado por un predictor) y para
    # separar atribucion directa de atribucion por anticuerpo de elucion.
    "alelo": [
        "mhc_restriction__name",
        "mhc_restriction__evidence_code",
    ],
    # El ensayo. `response_measured` discrimina mejor que `method`: separa
    # `ligand presentation` (87.681) de `dissociation constant KD (~IC50)`
    # (3.015) en 11 valores, frente a los 21 de `method`. Se conservan los dos.
    # La medida cuantitativa NO se puede usar sin `units` (de 4.776 valores solo
    # 4.321 son nM; el resto angstroms, minutos, grados) ni sin
    # `measurement_inequality` (385 de las nM son `>`, censuradas).
    "ensayo": [
        "assay__method",
        "assay__response_measured",
        "assay__qualitative_measurement",
        "assay__quantitative_measurement",
        "assay__units",
        "assay__measurement_inequality",
        "assay__comments",
        # Vacias en H2-K pero rellenas en el 3,36 % del conjunto (100.289 filas):
        # permiten una etiqueta graduada y detectar un "Positive" de 1/10 sujetos.
        "assay__number_of_subjects_responded",
        "assay__number_of_subjects_tested",
        "assay__response_frequency_",
    ],
    # Contexto experimental. Es el sesgo tecnico: un solo estudio aporta un tipo
    # celular entero (hepatocito 29.979, esplenocito 20.979). Candidato a eje de
    # fuga adicional, junto con el pmid. `geolocation` esta vacia en H2-K pero
    # rellena en 49.300 filas, y la geografia del hospedador importa en humano:
    # las frecuencias alelicas de HLA son poblacionales.
    "contexto": [
        "host__name",
        "host__age",
        "host__sex",
        "host__geolocation",
        "host__mhc_types_present",
        "antigen_presenting_cell__name",
        "antigen_presenting_cell__source_tissue",
        "antigen_presenting_cell__culture_condition",
        "antigen_processing__comments",
        "in_vivo_process__process_type",
        "in_vivo_process__disease",
        "in_vivo_process__disease_stage",
    ],
    # Publicacion. `pmid` es el eje de fuga que la particion por proteina no
    # cubre (89 pmids distintos para 87.593 filas de H2-K). `date` habilita un
    # split temporal, que es un control de fuga que no estaba contemplado.
    # Publicacion. `pmid` es el eje de fuga que la particion por proteina no
    # cubre. `authors` se conserva aunque `pmid` ya identifique el estudio:
    # para medir fuga por LABORATORIO (un grupo publica varios articulos con el
    # mismo protocolo y sesgo de preparacion) el autor es mas informativo que el
    # pmid. `date` habilita un split temporal, control de fuga no contemplado.
    "publicacion": [
        "reference__pmid",
        "reference__date",
        "reference__type",
        "reference__journal",
        "reference__title",
        "reference__authors",
        "reference__submission_id",
        "assay__location_of_assay_data_in_reference",
    ],
    # Objeto relacionado. Solo 1,06 % de las filas en H2-K, pero es justo lo que
    # interesa a la linea de neoantigenos: `in-frame neo-epitope` (210) y
    # `analog` (777). Barato de conservar y caro de volver a descargar.
    "objeto_relacionado": [
        "related_object__name",
        "related_object__epitope_relation",
        "related_object__object_type",
        "related_object__molecule_parent",
        "related_object__molecule_parent_iri",
        "related_object__source_molecule",
        "related_object__source_molecule_iri",
        "related_object__source_organism",
        "related_object__species",
        "related_object__synonyms",
        "related_object__starting_position",
        "related_object__ending_position",
    ],
    # Antigeno administrado in vivo o in vitro. Relleno residual (0,29 % y
    # 0,67 %) y poco relevante en un ensayo de elucion, donde el peptido se
    # eluyo del MHC y no se administro. Se conserva el nucleo del bloque por
    # simetria con `tcell_export`, donde si es central.
    "antigeno_administrado": [
        "in_vivo_antigen__name",
        "in_vivo_antigen__object_type",
        "in_vivo_antigen__epitope_relation",
        "in_vivo_antigen__source_organism",
        "in_vivo_antigen__species",
        "in_vivo_antigen__route",
        "in_vivo_antigen__dose_schedule",
        "in_vivo_antigen__reference_name",
        "in_vitro_process__process_type",
        "in_vitro_process__name",
        "in_vitro_process__object_type",
        "in_vitro_process__epitope_relation",
        "in_vitro_process__source_organism",
        "in_vitro_process__species",
        "in_vitro_process__reference_name",
    ],
    # Estructura cristalografica del complejo, cuando existe (0,11 %). Util para
    # cualquier trabajo futuro sobre el surco de union.
    "estructura": [
        "assay__pdb_id",
    ],
}

# --------------------------------------------------------------------------- #
# Columnas que se conservan de `tcell_export`.
#
# Vocabulario distinto al de `mhc_export`: aqui se mide INMUNOGENICIDAD
# (ELISPOT, ICS, citotoxicidad), no presentacion ni afinidad.
# --------------------------------------------------------------------------- #
KEEP_TCELL: dict[str, list[str]] = {
    "claves": [
        "assay_id",
        "epitope__iedb_iri",
    ],
    "peptido": [
        "epitope__name",
        "epitope__reference_name",
        "epitope__modifications",
        "epitope__modified_residues",
        "epitope__epitope_comments",
    ],
    "proteina_madre": [
        "epitope__molecule_parent",
        "epitope__molecule_parent_iri",
        "epitope__source_molecule",
        "epitope__source_molecule_iri",
        "epitope__starting_position",
        "epitope__ending_position",
    ],
    "origen": [
        "epitope__source_organism",
        "epitope__species",
    ],
    # LO QUE DE VERDAD SE PROBO EN EL ENSAYO, que no siempre es el epitopo.
    # `assay_antigen__name` difiere de `epitope__name` en el 9,30 % de las filas
    # de H2-K: 519 filas tienen como antigeno un `Organism` entero, 271 una
    # proteina, 168 una celula tumoral. Sin `epitope_relation` (Epitope 14.165,
    # Structurally Related 387, Source Organism 276...) se etiquetaria un
    # peptido con el resultado de un ensayo que midio otra cosa.
    "antigeno_del_ensayo": [
        "assay_antigen__name",
        "assay_antigen__epitope_relation",
        "assay_antigen__object_type",
        "assay_antigen__source_organism",
        "assay_antigen__species",
        "assay_antigen__molecule_parent",
        "assay_antigen__molecule_parent_iri",
        # 82,9 % de relleno sobre las 11 familias: la molecula concreta que se
        # presento en el ensayo. Omitirla dejaria el bloque cojo.
        "assay_antigen__source_molecule",
        "assay_antigen__source_molecule_iri",
        "assay_antigen__starting_position",
        "assay_antigen__ending_position",
        "assay_antigen__reference_name",
    ],
    "alelo": [
        "mhc_restriction__name",
        "mhc_restriction__evidence_code",
    ],
    # `number_of_subjects_positive` / `_tested` / `response_frequency_` (11,9 %)
    # permiten una etiqueta graduada en lugar de binaria, y detectar un
    # "Positive" que en realidad es 1 de 10 sujetos.
    "ensayo": [
        "assay__method",
        "assay__response_measured",
        "assay__qualitative_measurement",
        "assay__quantitative_measurement",
        "assay__units",
        "assay__measurement_inequality",
        "assay__number_of_subjects_positive",
        "assay__number_of_subjects_tested",
        "assay__response_frequency_",
        "assay__comments",
    ],
    # Celulas efectoras y presentadoras. `effector_cell__tcr_name` (180 TCRs)
    # es el gancho para cualquier trabajo futuro sobre reconocimiento por TCR.
    "celulas": [
        "effector_cell__name",
        "effector_cell__source_tissue",
        "effector_cell__culture_condition",
        "effector_cell__tcr_name",
        "antigen_presenting_cell__name",
        "antigen_presenting_cell__source_tissue",
        "antigen_presenting_cell__culture_condition",
        "in_vitro_responder_cell__name",
        "in_vitro_stimulator_cell__name",
    ],
    # Protocolo. Una transferencia adoptiva (317 filas) o una restimulacion in
    # vitro (2.267) no miden inmunogenicidad primaria.
    "protocolo": [
        "adoptive_transfer__flag",
        "adoptive_transfer__comments",
        "in_vitro_process__process_type",
        "immunization__comments",
    ],
    # Inmunogeno. `first_immunogen__object_type` da Organism 8.187 frente a
    # Linear peptide 2.995: inmunizar con un organismo y medir contra un peptido
    # es inmunogenicidad natural; inmunizar con el peptido es reactividad
    # inducida. Son fenomenos distintos y hoy estan mezclados.
    "inmunogeno": [
        "first_immunogen__name",
        "first_immunogen__object_type",
        "first_immunogen__epitope_relation",
        "first_immunogen__source_organism",
        "first_immunogen__species",
        "first_immunogen__route",
        "first_immunogen__adjuvants",
        "first_immunogen__dose_schedule",
        "first_immunogen__reference_name",
        "first_immunogen__source_molecule",
        "first_immunogen__source_molecule_iri",
        "first_immunogen__molecule_parent",
        "first_immunogen__molecule_parent_iri",
        "first_immunogen__starting_position",
        "first_immunogen__ending_position",
        "second_immunogen__name",
        "second_immunogen__object_type",
        "second_immunogen__epitope_relation",
        "second_immunogen__route",
        "second_immunogen__adjuvants",
        "second_immunogen__dose_schedule",
        "second_immunogen__reference_name",
        "second_immunogen__source_organism",
        "second_immunogen__species",
        "second_immunogen__molecule_parent",
        "second_immunogen__molecule_parent_iri",
        "second_immunogen__source_molecule",
        "second_immunogen__source_molecule_iri",
        "second_immunogen__starting_position",
        "second_immunogen__ending_position",
        # El inmunogeno in vitro esta relleno en el 23-31 % de las filas, muy
        # por encima del 17 % de H2-K: es la restimulacion, y sin su organismo y
        # su molecula no se puede saber contra que se restimulo.
        "in_vitro_immunogen__name",
        "in_vitro_immunogen__object_type",
        "in_vitro_immunogen__epitope_relation",
        "in_vitro_immunogen__reference_name",
        "in_vitro_immunogen__source_organism",
        "in_vitro_immunogen__species",
        "in_vitro_immunogen__source_molecule",
        "in_vitro_immunogen__source_molecule_iri",
        "in_vitro_immunogen__molecule_parent",
        "in_vitro_immunogen__molecule_parent_iri",
        "in_vitro_immunogen__starting_position",
        "in_vitro_immunogen__ending_position",
    ],
    # Estado del hospedador. En `tcell` hay 121 valores de `host__name` frente a
    # 13 en `mhc`: incluye transgenicos y knockouts, y un raton TCR-transgenico
    # no mide inmunogenicidad de poblacion.
    "contexto": [
        "host__name",
        "host__age",
        "host__sex",
        "host__geolocation",
        "host__mhc_present",
        "first_in_vivo_process__process_type",
        "first_in_vivo_process__disease",
        "first_in_vivo_process__disease_stage",
        "second_in_vivo_process__process_type",
        "second_in_vivo_process__disease",
        "second_in_vivo_process__disease_stage",
    ],
    "publicacion": [
        "reference__pmid",
        "reference__date",
        "reference__type",
        "reference__journal",
        "reference__title",
        "reference__authors",
        "reference__submission_id",
        "assay__location_of_assay_data_in_reference",
    ],
    "objeto_relacionado": [
        "related_object__name",
        "related_object__epitope_relation",
        "related_object__object_type",
        "related_object__molecule_parent",
        "related_object__molecule_parent_iri",
        "related_object__source_molecule",
        "related_object__source_molecule_iri",
        "related_object__source_organism",
        "related_object__species",
        "related_object__synonyms",
        "related_object__starting_position",
        "related_object__ending_position",
    ],
    "estructura": [
        "complex__pdb_id",
    ],
}

# --------------------------------------------------------------------------- #
# NUCLEO (`--columns core`, por omision). ~20 columnas por export: lo que se
# necesita para contar positivos, para filtrar y para construir los ejemplos.
#
# Criterio: entra una columna si (a) define el ejemplo (peptido, alelo,
# etiqueta), (b) es un filtro que vamos a aplicar o a decidir, o (c) hace falta
# para que otra columna sea interpretable. Todo lo demas se queda en
# `--columns full`, que sigue disponible sin volver a descargar.
# --------------------------------------------------------------------------- #
CORE_MHC: dict[str, list[str]] = {
    "claves": [
        "assay_id",                             # unico; procedencia y dedup
    ],
    "peptido": [
        "epitope__name",                        # la secuencia
        "epitope__modifications",               # 6,3 %: oxidado/cisteinilado
    ],
    "proteina_madre": [
        "epitope__molecule_parent_iri",         # accession UniProt: ventanas y senuelos
        "epitope__starting_position",
        "epitope__ending_position",
    ],
    "origen": [
        "epitope__species",                     # taxon agregado: source_is_self
        "epitope__source_organism",             # cepa: desglose de patogenos
    ],
    "alelo": [
        "mhc_restriction__name",                # alelo literal
        "mhc_restriction__evidence_code",       # excluir circularidad y anticuerpo
    ],
    "ensayo": [
        "assay__method",
        "assay__response_measured",             # presentacion / union / otro
        "assay__qualitative_measurement",       # LA ETIQUETA
        "assay__quantitative_measurement",
        "assay__units",                         # sin esto la anterior es basura
        "assay__measurement_inequality",        # valores censurados (>, <)
    ],
    "contexto": [
        "host__name",
    ],
    "publicacion": [
        "reference__pmid",
        "reference__submission_id",             # pmid no esta al 100 %
        "reference__date",                      # split temporal
    ],
}

CORE_TCELL: dict[str, list[str]] = {
    "claves": [
        "assay_id",
    ],
    "peptido": [
        "epitope__name",
        "epitope__modifications",
    ],
    "antigeno_del_ensayo": [
        "assay_antigen__name",                  # lo que se probo de verdad
        "assay_antigen__epitope_relation",      # hallazgo S: filtro a decidir
    ],
    "proteina_madre": [
        "epitope__molecule_parent_iri",
        "epitope__starting_position",
        "epitope__ending_position",
    ],
    "origen": [
        "epitope__species",
        "epitope__source_organism",
    ],
    "alelo": [
        "mhc_restriction__name",
        "mhc_restriction__evidence_code",       # 26,7 % 'MHC binding prediction'
    ],
    "ensayo": [
        "assay__method",
        "assay__response_measured",
        "assay__qualitative_measurement",
        "assay__number_of_subjects_positive",   # etiqueta graduada
        "assay__number_of_subjects_tested",
    ],
    "contexto": [
        "host__name",
        "first_immunogen__object_type",         # inmunogenicidad natural vs inducida
    ],
    "publicacion": [
        "reference__pmid",
        "reference__submission_id",
        "reference__date",
    ],
}

# --------------------------------------------------------------------------- #
# FILTRADO DE FILAS. Unico filtro que este script aplica, y solo porque no hay
# ninguna decision cientifica que tomar: un objeto que no es un peptido lineal
# no puede ser un ejemplo de este problema.
#
#   * `epitope__object_type`: ya es 100 % 'Linear peptide' porque la consulta a
#     IEDB lo filtra en origen. Aqui funciona como ASERCION: si apareciera otra
#     cosa, es que la descarga no es la que creemos.
#   * `assay_antigen__object_type` (solo `tcell_export`): este SI muerde. En
#     H2-K hay 519 filas cuyo antigeno es un `Organism` entero, 271 una
#     proteina y 168 una celula tumoral. Contar esas filas como positivos de
#     peptido falsea el recuento.
#
# Lo que NO se filtra, a proposito, porque es una decision abierta (§0.6.8.3):
# `assay_antigen__epitope_relation` (el 9,30 % no es `Epitope`),
# `mhc_restriction__evidence_code` (`MHC binding prediction` es circular) y el
# valor cualitativo. Esas columnas se conservan para que el filtro se aplique
# despues, con los recuentos delante.
# --------------------------------------------------------------------------- #
LINEAR_PEPTIDE = "Linear peptide"
FILTER_OBJECT_TYPE: dict[str, list[str]] = {
    "mhc": ["epitope__object_type"],
    "tcell": ["epitope__object_type", "assay_antigen__object_type"],
}

# --------------------------------------------------------------------------- #
# Columnas descartadas, con el motivo. Se registra en el manifiesto para que la
# decision quede documentada y sea revisable, no solo ejecutada.
# --------------------------------------------------------------------------- #
DROP_REASONS: dict[str, str] = {
    # Constantes por construccion de la consulta.
    "epitope__object_type": (
        "constante 'Linear peptide': la consulta ya filtra "
        "epitope__object_type=eq.Linear peptide en los dos perfiles"
    ),
    "mhc_restriction__class": (
        "constante ('I' o 'II'): la fija la consulta y se deriva del directorio"
    ),
    # Duplicados IRI de una columna legible que si se conserva. Se conservan en
    # cambio los IRI de molecula y de molecula madre, porque llevan el accession
    # de UniProt/NCBI, que es informacion y no un identificador de ontologia.
    "assay__iri": "IRI de ontologia; se conserva assay__method / __response_measured",
    "assay_id__iedb_iri": "URL derivable de assay_id",
    "epitope__iri": "vacia en todas las familias comprobadas",
    "epitope__source_organism_iri": "IRI NCBITaxon; se conserva epitope__source_organism",
    "epitope__species_iri": "IRI NCBITaxon; se conserva epitope__species",
    "host__iri": "IRI de ontologia; se conserva host__name",
    "mhc_restriction__iri": "IRI MRO; se conserva mhc_restriction__name",
    "mhc_restriction__evidence_iri": "IRI ECO; se conserva mhc_restriction__evidence_code",
    "reference__iedb_iri": "URL derivable de reference__pmid / __submission_id",
    "antigen_presenting_cell__iri": "IRI CL; se conserva antigen_presenting_cell__name",
    "antigen_presenting_cell__source_tissue_iri": "IRI UBERON; se conserva __source_tissue",
    "effector_cell__iri": "IRI CL; se conserva effector_cell__name",
    "effector_cell__source_tissue_iri": "IRI UBERON; se conserva __source_tissue",
    "in_vitro_responder_cell__iri": "IRI CL; se conserva __name",
    "in_vitro_stimulator_cell__iri": "IRI CL; se conserva __name",
    "in_vivo_process__disease_iri": "IRI DOID; se conserva in_vivo_process__disease",
    "first_in_vivo_process__disease_iri": "IRI DOID; se conserva __disease",
    "second_in_vivo_process__disease_iri": "IRI DOID; se conserva __disease",
    "epitope__synonyms": "vacia en todas las familias comprobadas",
    "host__geolocation_iri": "IRI de geolocalizacion; se conserva host__geolocation",
}
_DROP_SUFFIX_REASON = (
    "IRI de ontologia o taxon, redundante con la columna legible homonima que si se conserva"
)
_DROP_BLOCK_REASON = (
    "bloque de antigeno administrado con relleno residual (<1,5 %) y sin uso previsto; "
    "recuperable re-descargando, el CSV crudo se conserva"
)
# Bloques completos que no se conservan en mhc_export: describen el antigeno
# administrado in vivo o in vitro, que en un ensayo de elucion es irrelevante
# (el peptido se eluyo del MHC, no se administro).
DROP_PREFIXES_MHC = ("in_vivo_antigen__", "in_vitro_process__")


def _git_commit(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _sha256(path: Path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(buf):
            h.update(chunk)
    return h.hexdigest()


def _flatten(groups: dict[str, list[str]]) -> list[str]:
    """Aplana los bloques a una lista ordenada, abortando si hay duplicados."""
    seen: dict[str, str] = {}
    out: list[str] = []
    for block, cols in groups.items():
        for col in cols:
            if col in seen:
                raise SystemExit(
                    f"columna duplicada en la lista curada: {col!r} "
                    f"en los bloques {seen[col]!r} y {block!r}"
                )
            seen[col] = block
            out.append(col)
    return out


def _column_block(groups: dict[str, list[str]]) -> dict[str, str]:
    return {col: block for block, cols in groups.items() for col in cols}


def _drop_reason(col: str, kind: str) -> str:
    if col in DROP_REASONS:
        return DROP_REASONS[col]
    if col.endswith("_iri"):
        return _DROP_SUFFIX_REASON
    if kind == "mhc" and col.startswith(DROP_PREFIXES_MHC):
        return _DROP_BLOCK_REASON
    return (
        "no incluida en la lista curada: sin uso previsto y recuperable "
        "re-descargando; el CSV crudo se conserva"
    )


def _count_csv_rows(path: Path) -> int:
    """Cuenta filas de datos respetando comillas y saltos de linea embebidos."""
    n = 0
    for chunk in pd.read_csv(
        path, usecols=[0], dtype=str, chunksize=200_000, low_memory=False
    ):
        n += len(chunk)
    return n


def slim_one(
    src: Path,
    dst_dir: Path,
    kind: str,
    out_format: str,
    chunksize: int,
    profile: str = "core",
    filter_linear: bool = True,
) -> dict:
    """Proyecta un CSV crudo sobre la lista curada del perfil `profile`.

    El unico filtrado de filas es el de objeto no peptidico, y solo si
    `filter_linear`. Se registra cuantas filas quita cada condicion.
    """
    if profile == "core":
        groups = CORE_MHC if kind == "mhc" else CORE_TCELL
    else:
        groups = KEEP_MHC if kind == "mhc" else KEEP_TCELL
    wanted = _flatten(groups)
    blocks = _column_block(groups)

    header = pd.read_csv(src, nrows=0).columns.tolist()
    header_set = set(header)

    keep = [c for c in wanted if c in header_set]
    missing = [c for c in wanted if c not in header_set]

    # Columnas que hacen falta para filtrar aunque no se conserven.
    filt_cols = (
        [c for c in FILTER_OBJECT_TYPE[kind] if c in header_set]
        if filter_linear else []
    )
    read_cols = keep + [c for c in filt_cols if c not in keep]
    dropped = [c for c in header if c not in set(keep)]

    n_in = _count_csv_rows(src)

    frames = []
    for chunk in pd.read_csv(
        src, usecols=read_cols, dtype=str, chunksize=chunksize, low_memory=False
    ):
        frames.append(chunk)
    df = (
        pd.concat(frames, ignore_index=True)
        if frames else pd.DataFrame(columns=read_cols)
    )
    del frames

    if len(df) != n_in:
        raise SystemExit(
            f"ABORTADO: {src} tenia {n_in} filas y la lectura dio {len(df)}. "
            "La proyeccion de columnas no debe alterar el numero de filas."
        )

    # Filtrado de filas: objeto no peptidico.
    filtros: dict[str, dict] = {}
    for col in filt_cols:
        vc = df[col].fillna("(vacio)").value_counts()
        mask = df[col] == LINEAR_PEPTIDE
        filtros[col] = {
            "condicion": f'== "{LINEAR_PEPTIDE}"',
            "filas_antes": int(len(df)),
            "filas_eliminadas": int((~mask).sum()),
            "valores_eliminados": {
                k: int(v) for k, v in vc.items() if k != LINEAR_PEPTIDE
            },
        }
        df = df[mask]
    df = df.reset_index(drop=True)[keep]  # orden estable, el de la lista curada

    dst_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem + "_slim"
    # El Parquet es el artefacto de trabajo (tipado, columnar, ~10x mas
    # pequeno). El CSV es la copia inspeccionable a mano, y se emite siempre
    # que `out_format` lo pida porque leer el dato con los ojos es parte de
    # decidir los filtros que quedan abiertos.
    escritos: list[Path] = []
    if out_format in ("parquet", "both"):
        d = dst_dir / f"{stem}.parquet"
        df.to_parquet(d, index=False, compression="zstd")
        escritos.append(d)
    if out_format in ("csv", "both"):
        d = dst_dir / f"{stem}.csv"
        df.to_csv(d, index=False)
        escritos.append(d)
    dst = escritos[0]

    n = len(df)
    cols_info = {
        c: {
            "bloque": blocks[c],
            "relleno_pct": round(100.0 * df[c].notna().sum() / n, 4) if n else 0.0,
            "distintos": int(df[c].nunique(dropna=True)),
        }
        for c in keep
    }

    return {
        "entrada": str(src),
        "salida": str(dst),
        "tipo": kind,
        "perfil_columnas": profile,
        "filas_entrada": n_in,
        "filas_salida": n,
        "filas_eliminadas": n_in - n,
        "filtros_de_fila": filtros,
        "columnas_entrada": len(header),
        "columnas_salida": len(keep),
        "columnas_conservadas": cols_info,
        "columnas_descartadas": {c: _drop_reason(c, kind) for c in dropped},
        "columnas_curadas_ausentes_en_el_fichero": missing,
        "sha256_entrada": _sha256(src),
        "sha256_salida": _sha256(dst),
        "bytes_entrada": src.stat().st_size,
        "bytes_salida": dst.stat().st_size,
        "salidas": {
            str(d): {"sha256": _sha256(d), "bytes": d.stat().st_size}
            for d in escritos
        },
    }


def census(out: Path, manifest: dict, max_card: int = 80) -> dict:
    """Censo de valores de las columnas categoricas, agregado sobre las 11 familias.

    Es lo que hace falta para decidir los filtros que quedan abiertos: no se
    puede elegir entre presentacion, union e inmunogenicidad sin ver cuantas
    filas tiene cada `assay__method`, ni excluir las etiquetas circulares sin
    ver el reparto de `mhc_restriction__evidence_code`.
    """
    agg: dict[str, dict[str, dict[str, int]]] = {"mhc": {}, "tcell": {}}
    tot: dict[str, int] = {"mhc": 0, "tcell": 0}
    for info in manifest["ficheros"].values():
        kind = info["tipo"]
        df = pd.read_parquet(info["salida"])
        tot[kind] += len(df)
        for c in df.columns:
            if df[c].nunique(dropna=True) > max_card:
                continue
            vc = df[c].fillna("(vacio)").value_counts()
            d = agg[kind].setdefault(c, {})
            for k, v in vc.items():
                d[str(k)] = d.get(str(k), 0) + int(v)

    report: dict = {}
    for kind in ("mhc", "tcell"):
        if not tot[kind]:
            continue
        cols = {}
        for c, d in agg[kind].items():
            if len(d) > max_card:
                continue
            cols[c] = dict(sorted(d.items(), key=lambda kv: -kv[1]))
        report[kind] = {"filas": tot[kind], "columnas": cols}
        print(f"\n===== censo {kind}_export  (n={tot[kind]:,}) =====")
        for c, d in cols.items():
            print(f"\n[{c}]  {len(d)} valores")
            for k, v in list(d.items())[:25]:
                print(f"    {k[:62]:62s} {v:12,}  {100.0*v/tot[kind]:6.2f} %")
            if len(d) > 25:
                print(f"    ... y {len(d)-25} valores mas (el manifiesto los tiene todos)")
    return report


def audit_dropped(raw: Path, sources: list[Path]) -> dict:
    """Mide el relleno de las columnas DESCARTADAS sobre TODAS las familias.

    Es la comprobacion de seguridad de este script: una columna vacia en H2-K
    puede estar rellena en HLA-A o en clase II, de modo que mirar un solo
    fichero no basta para decidir que se descarta. Cualquier columna descartada
    con relleno apreciable es un error de curacion y hay que recuperarla.
    """
    agg: dict[str, dict[str, int]] = {"mhc": {}, "tcell": {}}
    tot: dict[str, int] = {"mhc": 0, "tcell": 0}
    for src in sources:
        kind = "tcell" if "tcell" in src.name else "mhc"
        groups = KEEP_MHC if kind == "mhc" else KEEP_TCELL
        kept = set(_flatten(groups))
        header = pd.read_csv(src, nrows=0).columns.tolist()
        dropped = [c for c in header if c not in kept]
        if not dropped:
            continue
        print(f"  auditando {src.relative_to(raw)} ... ", end="", flush=True)
        n = 0
        for ch in pd.read_csv(
            src, usecols=dropped, dtype=str, chunksize=300_000, low_memory=False
        ):
            n += len(ch)
            for c in dropped:
                agg[kind][c] = agg[kind].get(c, 0) + int(ch[c].notna().sum())
        tot[kind] += n
        print(f"{n:,} filas")

    report: dict = {}
    for kind in ("mhc", "tcell"):
        N = tot[kind]
        if not N:
            continue
        rows = sorted(agg[kind].items(), key=lambda kv: -kv[1])
        report[kind] = {
            "filas_auditadas": N,
            "columnas": {
                c: {"relleno_pct": round(100.0 * v / N, 4), "filas_no_nulas": v}
                for c, v in rows
            },
        }
        print(f"\n### {kind}_export — columnas descartadas (n={N:,})")
        vivas = [(c, v) for c, v in rows if v > 0]
        muertas = [c for c, v in rows if v == 0]
        for c, v in vivas:
            print(f"  {c:54s} {100.0*v/N:8.3f} %  {v:12,}")
        print(f"  vacias en TODAS las familias ({len(muertas)}): {', '.join(muertas)}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Proyecta los CSV crudos de IEDB sobre una lista curada de columnas. "
            "No elimina filas ni aplica ningun filtro cientifico."
        )
    )
    ap.add_argument("--raw", type=Path, default=None,
                    help=("directorio de la descarga cruda (con manifest.json). No hace falta "
                          "con --emit-csv o --census, que trabajan sobre la salida ya escrita."))
    ap.add_argument("--out", required=True, type=Path,
                    help="directorio de salida; replica la estructura especie/clase/familia")
    ap.add_argument("--only", action="append", default=None,
                    help="limita a una familia, p. ej. mouse/mhc-I/H2-K (repetible)")
    ap.add_argument("--format", choices=("parquet", "csv", "both"), default="both",
                    help=("formato de salida. Por omision 'both': el Parquet es el artefacto "
                          "de trabajo y el CSV la copia inspeccionable a mano."))
    ap.add_argument("--chunksize", type=int, default=200_000)
    ap.add_argument("--force", action="store_true",
                    help="reprocesa ficheros ya presentes en el manifiesto de salida")
    ap.add_argument("--columns", choices=("core", "full"), default="core",
                    help=("'core' (por omision) deja ~20 columnas por export: lo necesario "
                          "para contar positivos, filtrar y construir ejemplos. 'full' deja "
                          "la lista curada ancha (75 y 126 columnas)."))
    ap.add_argument("--keep-nonpeptide", action="store_true",
                    help=("NO filtra las filas cuyo objeto no es 'Linear peptide'. Por "
                          "omision se filtran, porque un organismo o una celula tumoral no "
                          "es un ejemplo de este problema."))
    ap.add_argument("--emit-csv", action="store_true",
                    help=("escribe el CSV equivalente al lado de cada Parquet ya existente, "
                          "sin releer los CSV crudos. Para anadir la copia inspeccionable a "
                          "una salida que se genero solo en Parquet."))
    ap.add_argument("--census", action="store_true",
                    help=("tras escribir, censa los valores de las columnas categoricas "
                          "sobre las 11 familias y lo anota en el manifiesto"))
    ap.add_argument("--audit-dropped", action="store_true",
                    help=("mide el relleno de las columnas descartadas sobre TODAS las "
                          "familias y lo anota en el manifiesto; es la comprobacion de "
                          "que la lista curada no tira nada que este relleno en otra familia"))
    args = ap.parse_args()

    out: Path = args.out.resolve()
    raw: Path = (args.raw or args.out).resolve()
    if not raw.is_dir():
        print(f"ERROR: no existe {raw}", file=sys.stderr)
        return 2
    if args.raw is not None and out == raw:
        print("ERROR: --out no puede ser el mismo directorio que --raw", file=sys.stderr)
        return 2

    repo = Path(__file__).resolve().parents[3]
    out.mkdir(parents=True, exist_ok=True)
    man_path = out / "manifest_slim.json"
    if man_path.exists():
        manifest = json.loads(man_path.read_text())
    else:
        manifest = {
            "generado_por": "data_pipeline/scripts/data_processing/slim_raw_export.py",
            "descarga_origen": str(raw),
            "formato": args.format,
            "perfil_columnas": args.columns,
            "filtro_linear_peptide": not args.keep_nonpeptide,
            "nota": (
                "Proyeccion de columnas mas un unico filtro de fila: objeto "
                "'Linear peptide'. NO se aplica ningun otro filtro: ni cualitativo, "
                "ni de organismo fuente, ni de codigo de evidencia, ni de relacion "
                "antigeno-epitopo. Esas decisiones quedan abiertas y las columnas "
                "necesarias para tomarlas se conservan."
            ),
            "ficheros": {},
        }
    manifest["fecha_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["commit_git"] = _git_commit(repo)

    sources = sorted(raw.rglob("*_export_full.csv")) + sorted(raw.rglob("*_export.csv"))
    if not sources:
        # Los modos que trabajan sobre la salida ya escrita no necesitan los
        # CSV crudos, que estan archivados y comprimidos.
        if not (args.emit_csv or args.census):
            print(f"ERROR: ningun *_export*.csv bajo {raw}", file=sys.stderr)
            return 2
        print(f"(sin CSV crudos bajo {raw}: se trabaja solo sobre la salida ya escrita)")

    tot_in = tot_out = 0
    tot_rows = 0
    for src in sources:
        rel = src.relative_to(raw)
        family = str(rel.parent)
        if args.only and family not in args.only:
            continue
        key = str(rel)
        if key in manifest["ficheros"] and not args.force:
            print(f"[salta] {key} (ya en el manifiesto; --force para rehacer)")
            continue

        kind = "tcell" if "tcell" in src.name else "mhc"
        print(f"[{kind:5s}] {key} ... ", end="", flush=True)
        info = slim_one(
            src, out / rel.parent, kind, args.format, args.chunksize,
            profile=args.columns, filter_linear=not args.keep_nonpeptide,
        )
        manifest["ficheros"][key] = info
        man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

        red = 100.0 * (1 - info["bytes_salida"] / info["bytes_entrada"])
        quitadas = info["filas_eliminadas"]
        marca = f" (-{quitadas:,} no peptido)" if quitadas else ""
        print(
            f"{info['filas_salida']:>9,} filas{marca}  "
            f"{info['columnas_entrada']}→{info['columnas_salida']} cols  "
            f"{info['bytes_entrada']/1e6:7.1f}→{info['bytes_salida']/1e6:6.1f} MB  "
            f"(-{red:.1f} %)"
        )
        tot_in += info["bytes_entrada"]
        tot_out += info["bytes_salida"]
        tot_rows += info["filas_salida"]

    if args.emit_csv:
        print("\n--- emitiendo CSV a partir de los Parquet ya escritos ---")
        for key, info in manifest["ficheros"].items():
            pq = Path(info["salida"])
            if pq.suffix != ".parquet" or not pq.exists():
                print(f"[salta] {key}: no hay Parquet en {pq}")
                continue
            csvp = pq.with_suffix(".csv")
            df = pd.read_parquet(pq)
            df.to_csv(csvp, index=False)
            info.setdefault("salidas", {})[str(csvp)] = {
                "sha256": _sha256(csvp), "bytes": csvp.stat().st_size,
            }
            print(f"[csv  ] {key} -> {csvp}  {csvp.stat().st_size/1e6:.1f} MB")
        man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    if args.census:
        manifest["censo_de_valores"] = census(out, manifest)
        man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    if args.audit_dropped:
        print("\n--- auditoria de columnas descartadas ---")
        selected = [
            s for s in sources
            if not args.only or str(s.relative_to(raw).parent) in args.only
        ]
        manifest["auditoria_columnas_descartadas"] = audit_dropped(raw, selected)
        man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    if tot_in:
        print(
            f"\nTOTAL  {tot_rows:,} filas  "
            f"{tot_in/1e6:,.1f} → {tot_out/1e6:,.1f} MB "
            f"(-{100.0*(1-tot_out/tot_in):.1f} %)"
        )
    print(f"Manifiesto: {man_path}")
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
