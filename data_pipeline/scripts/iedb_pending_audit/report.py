"""Render the pending-event audit with explicit counterfactual policies."""

import argparse
import csv
import gzip
import json
from pathlib import Path


def number(value):
    return f"{value:,}".replace(",", ".")


def run(output):
    load = lambda file: json.loads((output / file).read_text())
    coverage = load("coverage.json")
    impact = load("impact.json")
    events = load("event_resolution.json")
    total = impact["totals"]
    confirmed = {"simple_verified", "modified_backbone_and_parent_verified"}
    assert len(events) == 44907
    assert sum(coverage["states"].values()) == len(events)
    assert sum(r["raw_records"] for r in events) == coverage["raw_records"]
    assert total["historical_positive_positions"] == 491850
    assert total["old_locally_accepted_groups"] == 41427
    assert total["groups_with_verified_parent_mapping"] == sum(coverage["states"].get(s,0) for s in confirmed)
    assert coverage["overlap_previous"] == total["previous_coordinate_audit_overlap"]
    assert len({(e["family"],e["old_event_id"]) for e in events}) == len(events)
    names = {
        "simple_verified": "Péptido simple verificado",
        "modified_backbone_and_parent_verified": "Péptido modificado con esqueleto y locus parent verificados",
        "backbone_mapped_chemistry_pending": "Locus verificado, identidad química pendiente",
        "requires_iedb_structure_or_assay_link": "Necesita enlace a ensayo o estructura de IEDB",
        "requires_reference_or_backbone": "Necesita referencia o esqueleto resoluble",
        "mapping_not_verified": "Intervalo o proyección sin verificar",
        "conflicting_verified_loci_or_backbones": "Loci o esqueletos incompatibles entre evidencias",
        "incompatible_parent_reference": "Esqueleto ausente de la referencia parent",
    }
    scopes = {
        "verified_backbone_sensitivity": "Conservar de forma hipotética el respaldo de los modificados ya mapeados",
        "strict_plain_sensitivity": "Exigir respaldo simple para el péptido sin modificar",
    }
    n=number
    lines=[
        "# Verificación de los 44.907 eventos pendientes de IEDB", "",
        "## Alcance y cruce", "",
        f"Se recuperaron **{n(coverage['raw_records'])} registros de ensayo** para **{n(len(events))} grupos familiares**. "
        f"**{n(coverage['overlap_previous'])}** grupos ya aparecían en la auditoría de coordenadas. "
        f"**{n(total['previous_coordinate_verified'])}** tenían un mapeo verificado en esa auditoría. "
        "La unión se hizo por familia, esqueleto anterior, coordenadas y ambas referencias, conservando versiones e isoformas. "
        "Se equipararon los esquemas HTTP y HTTPS. Cada grupo se cuenta una sola vez en la tabla final. "
        "El cruce histórico por FASTA reproduce 41.427 grupos que pasaban el cotejo local y 491.850 posiciones positivas. "
        f"Se localizaron anotaciones compatibles atribuidas a esos grupos en {n(total['actual_positive_positions_with_matching_annotations'])} "
        "posiciones de los Parquet originales. El escenario de retirada usa filas realmente observadas.", "",
        "[Todos los vínculos de ensayo](assay_links.jsonl.gz) · [Estado por grupo](event_resolution.csv) · "
        "[Cobertura de consultas](coverage.json)", "",
        "## Estados finales y solapamientos", "",
        "| Estado mutuamente excluyente | Grupos |", "|---|---:|",
    ]
    lines.extend(f"| {names.get(s,s)} | {n(v)} |" for s,v in sorted(coverage["states"].items()))
    lines.extend(["",
        f"**{n(total['corrected'])}** grupos tienen una corrección de extremos comprobada y sin conflicto de locus. "
        "Esa marca se cruza con la identidad molecular y no forma una categoría excluyente.",
        f"De los grupos con evidencia simple o modificada mapeada, **{n(total['verified_mapping_also_exact_source'])}** "
        "también reproducen exactamente el intervalo en su referencia source. Cuando falta esa comprobación, "
        "solo se acepta el locus parent si existe una anotación explícita para la misma versión o secuencia o un mapeo "
        "previo verificado y vinculado a la estructura original. Las columnas de estructuras separan ambos controles.",
        f"Se obtuvieron **{n(coverage['returned_structure_ids'])} de {n(coverage['requested_structure_ids'])}** IDs solicitados a IEDB "
        f"y hubo **{n(coverage['failed_batches'])}** lotes sin respuesta utilizable. "
        "Los estados de referencia pendiente reflejan las fuentes y versiones recuperadas en esta ejecución. "
        "Un locus verificado para la entidad modificada conserva esa evidencia experimental. Aplicar esa positividad "
        "a la ventana sin modificar requeriría evidencia adicional. "
        "[Manual de curación de IEDB sobre residuos modificados](https://curationwiki.iedb.org/wiki/index.php/Curation_Manual)", "",
        "## Distribución por familia", "",
        "| Familia | Verificados simples o modificados | Coordenadas corregidas | No verificados | Posiciones históricas | Secuencias afectadas |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for fam,c in impact["family"].items():
        fields=("groups_with_verified_parent_mapping","corrected","not_verified_as_simple_or_modified",
                "historical_positive_positions","affected_distinct_sequences")
        lines.append("| "+fam+" | "+" | ".join(n(c.get(k,0)) for k in fields)+" |")
    lines.extend(["", "Las posiciones se deduplican dentro de familia, proteína e inicio. Las secuencias se "
        "deduplican en el agregado global. Los recuentos de secuencias por familia pueden solaparse.", "",
        "## Impacto sobre etiquetas globales", "",
        f"Las posiciones históricas cubren **{n(impact['distinct_historical_sequences'])}** secuencias distintas. "
        f"Al incluir loci remapeados, se evaluaron **{n(impact['distinct_affected_existing_sequences'])}** secuencias del índice actual. "
        "En ambos escenarios se conserva cualquier evidencia histórica independiente fuera de estos 44.907 grupos, "
        "en cualquiera de las 11 familias. Para atribuir retiradas se cotejaron filas positivas reales por proteína, "
        "inicio y epítopo seleccionado. Los loci con una anotación indistinguible aportada por otro evento "
        "se conservaron de forma conservadora. No se volvió a validar toda esa evidencia independiente.", "",
        "| Escenario hipotético | Global 1 que se conserva | Global 1 → 0 | Global 0 → 1 | Secuencias positivas nuevas fuera del índice |",
        "|---|---:|---:|---:|---:|",
    ])
    for name,s in impact["scenarios"].items():
        lines.append("| "+scopes[name]+" | "+" | ".join(n(s[k]) for k in (
            "affected_global_1_retained","global_1_to_0","global_0_to_1","new_positive_sequences_outside_current_index"))+" |")
    lines.extend(["",
        "El primer escenario excluye los grupos sin respaldo verificable, corrige los loci y permite que los "
        "modificados mapeados sostengan hipotéticamente la etiqueta histórica. El segundo conserva solo respaldo "
        "simple de los grupos auditados. El contraste cuantifica la decisión química pendiente. "
        "Una etiqueta operativa 0 expresa ausencia de respaldo elegible, no negatividad experimental.",
        f"Los ascensos del primer escenario comparten **{n(impact['scenarios']['verified_backbone_sensitivity']['global_0_to_1_overlaps_previous_audit'])}** "
        "secuencias con los ascensos de la auditoría anterior. No deben sumarse como conjuntos disjuntos.", "",
        "[Distribución y cambios globales por familia](by_family.csv) · [Escenarios por secuencia](global_scenarios.csv)", "",
        "## Ejemplos trazables", "",
    ])
    for state in names:
        example=next((e for e in events if e["state"]==state),None)
        if not example:
            continue
        e=example
        ev=next(iter(e["evidence"]),None)
        interval=f"parent {ev['parent_start']}–{ev['parent_end']}" if ev else "sin intervalo parent verificado"
        lines.append(f"- **{names[state]}.** {e['family']}, {e['original_names'][0]}, "
                     f"source {e['original_start']}–{e['original_end']}, {interval}. "
                     f"Ensayo {e['assay_iris'][0] if e['assay_iris'] else 'sin IRI'}, "
                     f"grupo {e['old_event_id']}.")
    lines.extend(["", "## Cambios que requieren los scripts originales", "",
        "1. **Descarga.** Conservar los resultados cualitativos, IRIs de ensayo y estructura, metadatos de modificación "
        "y coordenadas ausentes. Registrar fecha y controles de integridad por página.",
        "2. **Normalización.** Sustituir la extracción por regex por campos estructurados de IEDB. "
        "Distinguir la entidad modificada de su esqueleto lineal y conservar la relación muchos-a-muchos con los ensayos.",
        "3. **Clasificación.** Verificar la versión de la referencia y remapear los intervalos fuente al parent "
        "antes de crear ventanas. Separar evidencia de entidad modificada, respaldo simple, proyección y casos pendientes. "
        "Agregar por secuencia conservando las evidencias independientes.",
        "", "No se editaron los scripts principales ni sus datos, y no se reconstruyeron datasets completos ni se calcularon embeddings.", "",
    ])
    (output/"report.md").write_text("\n".join(lines))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    run(a.output)


if __name__=="__main__":
    main()
