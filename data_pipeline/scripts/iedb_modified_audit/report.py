"""Summarize chemistry, corroboration levels, duplicates and historical sensitivity."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import json
from pathlib import Path
import re
import sqlite3

from data_pipeline.scripts.global_epitope_labels.build import FAMILIES, write_json


def n(v):
    return f"{v:,}".replace(",", ".")


def pct(a,b):
    return f"{100*a/b:.2f}%".replace(".",",") if b else "—"


def csv_write(path, rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,restval=0);w.writeheader();w.writerows(rows)


def run(output):
    e=json.loads((output/"entities.json").read_text())
    i=json.loads((output/"impact.json").read_text())
    chemistry={r["chemistry"]:r for r in i["chemistry"]}
    assert sum(r["records"] for r in i["chemistry"])==1985260
    assert i["retained_global_positive"]+i["modified_only"]+i["ambiguous"]==i["historical_global_positive"]
    assert sum(i["previous_167119"][k] for k in ("still_modified_only","ambiguous","retained_simple"))==167119
    counts={}
    components=defaultdict(lambda: (0,set()))
    aids={}
    with closing(sqlite3.connect((output/"audit_work.sqlite").resolve().as_uri()+"?mode=ro",uri=True)) as db:
        counts={f:dict(modified_records=nrows,modified_assays_distinct=nassays,records_with_no_structure_iri=unresolved)
                for f,nrows,nassays,unresolved in db.execute("""SELECT family,count(*),COUNT(DISTINCT NULLIF(assay,'')),SUM(eid='')
                     FROM records WHERE chemistry='modified' GROUP BY family""")}
        aids={k:nassays for k,nassays in db.execute("SELECT chemistry,COUNT(DISTINCT NULLIF(assay,'')) FROM records GROUP BY chemistry")}
        for annotation,eid in db.execute("SELECT modification,eid FROM records WHERE chemistry='modified'"):
            items={part.split("|",1)[0].strip() for part in re.split(r",\s*(?:and\s+)?|\s+and\s+",annotation) if part.strip()}
            if not items:
                items={"Categoría solo recuperada por enlace estructurado"}
            for item in items:
                count, ids=components[item]
                if eid:
                    ids.add(eid)
                components[item]=count+1,ids
    csv_write(output/"modification_components.csv", [
        {"component":part,"records":count,"unique_known_epitope_ids":len(ids)}
        for part,(count,ids) in sorted(components.items(),key=lambda x:-x[1][0])
    ])

    by_family=[]
    for _,_,f in FAMILIES:
        levels=e["equivalents_by_family"].get(f,{})
        known=levels.get("modified_ids",0)
        backed=levels.get("B",0)
        available=levels.get("with_backbone",0)
        row=dict(family=f,**counts.get(f,{}),modified_ids=known,
                 A_catalogue_simple=levels.get("A",0),
                 B_positive_simple_same_family=backed,
                 C_positive_simple_same_reference=levels.get("C",0),
                 D_positive_simple_same_verified_locus=levels.get("D",0),
                 no_B_with_backbone=available-backed,backbone_undetermined=known-available,
                 pct_no_B_among_known_ids=pct(available-backed,known),
                 **i["family"][f])
        by_family.append(row)
    csv_write(output/"by_family.csv",by_family)
    csv_write(output/"duplicate_sources.csv",[dict(origin=k,**v) for k,v in i["duplicates"].items()])
    occurrences=defaultdict(lambda:{"families":set(),"positive_families":set(),"locus_families":set(),
                                    "catalogue_ids":set(),"positive_simple_ids":set(),"backbone":set()})
    with (output/"modified_assays.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            eid=row["epitope_id"]
            if not eid:
                continue
            v=occurrences[eid]
            v["families"].add(row["family"])
            if row["backbone"]:
                v["backbone"].add(row["backbone"])
            if row["B_positive_simple"]=="1":v["positive_families"].add(row["family"])
            if row["D_verified_locus"]=="1":v["locus_families"].add(row["family"])
            v["catalogue_ids"].update(x for x in row["catalogue_simple_epitope_ids"].split("|") if x)
            v["positive_simple_ids"].update(x for x in row["B_simple_ids"].split("|") if x)
    ids=[]
    for eid,v in sorted(occurrences.items(),key=lambda x:int(x[0])):
        status=("positive_simple_same_family" if v["positive_families"] else
                "no_positive_simple_same_family_in_archived_data" if v["backbone"] else "backbone_unresolved")
        ids.append(dict(modified_epitope_id=eid,status=status,**{k:"|".join(sorted(x)) for k,x in v.items()}))
    csv_write(output/"epitope_equivalents.csv",ids)
    assert len(ids)==e["equivalents_global"]["modified_ids"]

    hist=i["historical_global_positive"]
    lost=i["modified_only"]
    amb=i["ambiguous"]
    retained=i["retained_global_positive"]
    footprint=i["footprint_total"]
    loss_rows=footprint.get("modified_only",0)
    amb_rows=footprint.get("ambiguous",0)
    initial_rows=i["original_rows"]
    initial_pos_rows=i["original_global_positive_rows"]
    globals_=[
        {"metric":"unique_global_positive","historical":hist,"scenario":retained,
         "difference":retained-hist,"pct_of_historical":pct(hist-retained,hist)},
        {"metric":"unique_global_unlabeled","historical":i["original_unique_sequences"]-hist,
         "scenario":i["original_unique_sequences"]-hist,"difference":0,"pct_of_historical":"0%"},
        {"metric":"positive_original_rows_global_label","historical":initial_pos_rows,
         "scenario":initial_pos_rows-loss_rows-amb_rows,"difference":-loss_rows-amb_rows,
         "pct_of_historical":pct(loss_rows+amb_rows,initial_pos_rows)},
        {"metric":"operational_unlabeled_original_rows","historical":initial_rows-initial_pos_rows,
         "scenario":initial_rows-initial_pos_rows,"difference":0,"pct_of_historical":"0%"},
        {"metric":"original_rows_in_scenario","historical":initial_rows,
         "scenario":initial_rows-loss_rows-amb_rows,"difference":-loss_rows-amb_rows,
         "pct_of_historical":pct(loss_rows+amb_rows,initial_rows)},
    ]
    csv_write(output/"global_comparison.csv",globals_)
    known=e["equivalents_global"].get("modified_ids",0)
    global_b=e["equivalents_global"].get("B",0)
    global_d=e["equivalents_global"].get("D",0)
    global_A=e["equivalents_global"].get("A",0)
    global_c=e["equivalents_global"].get("C",0)
    available=e["equivalents_global"].get("with_backbone",0)
    dup=e["earlier_verified_modified_groups"]
    prev=i["previous_167119"]
    api_problems={k:v for k,v in e.items() if isinstance(v,dict) and "failed" in v}
    cap=sum(len(json.loads(path.read_text()))>=1000 for path in (output/"cache").glob("*.json"))
    bpath=output/"blosum_address_sample.csv"
    sampled=list(csv.DictReader(bpath.open())) if bpath.is_file() else []
    sample_count=sum(int(r["archive_rows_verified"]) for r in sampled)
    lines=[
        "# Auditoría de la evidencia de péptidos modificados", "",
        "## Alcance y procesamiento histórico", "",
        "Se recorrieron los 1.985.260 registros de los 22 CSV MHC y T-cell archivados usando la tabla de procedencia "
        "que reproduce sus filas y claves originales. El descargador conservaba los metadatos químicos en el bruto. "
        "Al crear el CSV fusionado, la regex escogía el primer bloque de letras del nombre y descartaba el resto. "
        "La deduplicación por familia usaba ese bloque, inicio, fin, source y parent. La tabla fusionada perdía "
        "el identificador de estructura, la modificación y los vínculos de ensayo. Las referencias o posiciones distintas "
        "podían producir eventos diferentes incluso con la misma estructura. El signo + no se usó como clasificador.", "",
        "[Normalización histórica](../../data_pipeline/scripts/data_download/build_iedb_dataset.py#L133) · "
        "[Fusión histórica](../../data_pipeline/scripts/data_download/build_iedb_dataset.py#L208) · "
        "[Manual de curación de IEDB](https://curationwiki.iedb.org/wiki/index.php/Curation_Manual)", "",
        "## Entidades, esqueletos y equivalentes", "",
        f"Hay **{n(chemistry['modified']['records'])} registros modificados**, "
        f"**{n(aids.get('modified',0))} ensayos con IRI distinto**, **{n(known)} IDs de epítopo modificado** y "
        f"**{n(e['distinct_modified_backbones'])} esqueletos lineales** identificados. Entre los simples del archivo "
        f"se identificaron **{n(chemistry['simple']['identified_structures'])} IDs** y "
        f"**{n(chemistry['simple']['distinct_backbones'])} secuencias**. "
        f"Quedaron {n(chemistry['modified']['unresolved_structure_records'])} registros modificados sin ID y "
        f"{n(chemistry['modified']['missing_backbone_records'])} sin esqueleto lineal resoluble con los datos recuperados.", "",
        f"**{n(e['catalogue_shared_backbones'])} esqueletos modificados** tienen una entidad simple distinta en el catálogo consultado. "
        f"**{n(e['positive_archived_shared_backbones'])}** aparecen con respaldo positivo simple en los ensayos archivados. "
        "El nivel A consulta el catálogo de IEDB y mide existencia. B–D se limitan a positivos archivados de las once familias, "
        "con un IRI de ensayo independiente. La consulta del catálogo no demuestra positividad en una familia.", "",
        "| Familia | Modificados únicos | A, simple en catálogo | B, positivo simple | C, misma referencia | D, locus verificado | Sin B con esqueleto conocido | % sin B | No determinado |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    fields=("modified_ids","A_catalogue_simple","B_positive_simple_same_family","C_positive_simple_same_reference",
            "D_positive_simple_same_verified_locus","no_B_with_backbone")
    for r in by_family:
        lines.append("| "+r["family"]+" | "+" | ".join(n(r[k]) for k in fields)+" | "+
                     r["pct_no_B_among_known_ids"]+" | "+n(r["backbone_undetermined"])+" |")
    lines.extend([
        f"| **Global, IDs deduplicados** | {n(known)} | {n(global_A)} | {n(global_b)} | {n(global_c)} | "
        f"{n(global_d)} | {n(available-global_b)} | {pct(available-global_b,known)} | {n(known-available)} |", "",
        "C exige el mismo identificador source o parent con la versión y la isoforma intactas. D exige la misma referencia "
        "parent archivada, su hash y el mismo intervalo verificado para ambas evidencias. Se exige una anotación explícita "
        "para la referencia exacta, un remapeo previo validado o una proyección inequívoca desde la fuente. "
        "D es una cota de lo que se pudo verificar. La falta de coincidencia D no demuestra que no exista un locus equivalente.", "",
        f"Las consultas de IEDB registraron {sum(x['failed'] for x in api_problems.values())} lotes fallidos. "
        f"Se observaron {cap} respuestas con 1.000 o más filas en la caché. "
        "Los recuentos incompletos o las estructuras sin enlace quedan como desconocidos.", "",
        "[IDs con respaldo, sin respaldo o pendientes](epitope_equivalents.csv) · "
        "[Equivalentes y ensayos trazables por registro](modified_assays.csv) · "
        "[Distribución química original](modifications.csv) · [Componentes de modificación](modification_components.csv)", "",
        "## Origen de las duplicaciones", "",
        "| Tipo | Registros implicados | IDs de epítopo | Eventos familiares |", "|---|---:|---:|---:|",
    ])
    types={
       "multiple_assays_same_entity":"Varios ensayos del mismo epítopo y clave",
       "different_modified_entities_same_event":"Distintas entidades modificadas fusionadas en la misma clave",
       "mixed_simple_and_modified_different_entities":"Entidades simples y modificadas distintas fusionadas",
       "same_entity_different_reference_or_coordinate":"Mismo epítopo en referencias o posiciones distintas",
       "uncertain_chemistry_or_missing_structure_id_in_event":"Otros casos con química o ID incierto",
    }
    for k,row in i["duplicates"].items():
        lines.append("| "+types[k]+" | "+" | ".join(n(row[c]) for c in ("records","unique_iedb_epitopes","family_events"))+" |")
    mix=i["duplicates"]["mixed_simple_and_modified_different_entities"]
    lines.extend(["",
        f"Hay **{n(mix['family_events'])} claves mixtas demostradas** con IDs distintos. Añadir solo el estado simple/modificado "
        "a esas claves habría evitado al menos una fusión entre categorías por clave. Los registros implicados no son la cantidad "
        "de filas deduplicadas porque una clave puede reunir varios ensayos. Las categorías de auditoría pueden solaparse. "
        "Las referencias y posiciones distintas se conservaron como claves distintas y no producen duplicación en esa etapa.", "",
        "[Tabla de duplicaciones](duplicate_sources.csv)", "",
        "## Posiciones positivas históricas", "",
        "| Familia | Positivas históricas | Con simples | Con modificados | Ambas | Solo modificados | % solo modificados | Ambiguas sin simples |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    pos_fields=("historical_positive_positions","positions_with_simple","positions_with_modified","positions_with_both","positions_only_modified")
    for r in by_family:
        lines.append("| "+r["family"]+" | "+" | ".join(n(r.get(k,0)) for k in pos_fields)+" | "+
                     pct(r.get("positions_only_modified",0),r["historical_positive_positions"])+" | "+
                     n(r.get("positions_ambiguous_without_simple",0))+" |")
    lines.extend(["",
        "Se cotejaron las filas positivas reales con el FASTA archivado y los eventos que pueden explicar la anotación "
        "seleccionada en esa posición. El respaldo simple histórico conserva esa regla local y su trazabilidad. "
        "No equivale a revalidar la referencia source de todos los eventos históricos. Se incorporaron además los remapeos "
        "ya verificados que disponen de ensayo simple independiente. Un positivo simple en otra familia preserva la etiqueta global.", "",
        "## Impacto global y volumen de entrenamiento", "",
        f"De las **{n(hist)} secuencias positivas actuales**, **{n(retained)}** conservan respaldo simple, "
        f"**{n(lost)}** quedan respaldadas exclusivamente por evidencia modificada y **{n(amb)}** quedan ambiguas. "
        f"La pérdida inequívoca bajo la regla de excluir solo los modificados representa **{pct(lost,hist)}** de los positivos "
        f"y **{pct(lost,i['original_unique_sequences'])}** de las secuencias del índice completo. "
        "Las ambiguas se mantienen aparte para revisión. Ninguna se declara negativa experimental.", "",
        "| Métrica | Histórico | Escenario con evidencia simple y ambiguos aparte | Diferencia | % sobre el histórico |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in globals_:
        lines.append(f"| {row['metric']} | {n(row['historical'])} | {n(row['scenario'])} | {n(row['difference'])} | {row['pct_of_historical']} |")
    lines.extend(["",
        f"Se trazaron **{n(loss_rows)} filas originales** de secuencias que perderían su respaldo y **{n(amb_rows)}** "
        f"de secuencias ambiguas. De ellas, {n(footprint.get('original_family_positive_modified_only',0))} y "
        f"{n(footprint.get('original_family_positive_ambiguous',0))} respectivamente tenían una anotación familiar positiva. "
        "Todas las apariciones en estos grupos tenían etiqueta global positiva, incluso cuando la etiqueta familiar era 0.", "",
        f"El manifiesto de BLOSUM62 es consistente con 26 filas por grupo original. A partir de los identificadores de origen, "
        f"se estiman **{n(loss_rows*26)} filas** en grupos sin respaldo simple y **{n(amb_rows*26)}** en grupos ambiguos. "
        f"Se comprobó directamente en metadatos archivados la pertenencia y etiqueta familiar de **{n(sample_count)} filas** "
        f"de **{n(len(sampled))} grupos**. Las estimaciones no certifican cada grupo ni su asignación posterior a splits. "
        "Las variantes heredaron la etiqueta y carecen de respaldo experimental independiente.", "",
        "[Secuencias sin respaldo o ambiguas](sequence_loss.csv) · [Trazabilidad de filas originales](affected_original_groups.csv.gz) · "
        "[Muestra de direcciones BLOSUM62](blosum_address_sample.csv) · [Comparación global](global_comparison.csv)", "",
        "## Comparación con las auditorías anteriores", "",
        f"Se cruzaron **{n(dup.get('all',0))}** de los 42.809 grupos modificados previamente verificados. "
        f"**{n(dup.get('B',0))}** tienen un positivo simple de la misma secuencia y familia, y **{n(dup.get('D',0))}** "
        "tienen respaldo simple en el mismo locus verificado.", "",
        f"De las 167.119 secuencias del escenario estricto anterior, **{n(prev['still_modified_only'])}** continúan "
        f"sin otro respaldo conocido, **{n(prev['ambiguous'])}** quedan ambiguas y **{n(prev['retained_simple'])}** "
        f"conservan respaldo simple. Dentro de estas últimas, {n(prev['retained_legacy_simple'])} tienen evidencia "
        f"histórica identificable y {n(prev['retained_recovered_simple'])} quedan respaldadas solo tras incluir remapeos "
        "simples verificados. Los remapeos se agregaron por secuencia y no se sumaron como casos nuevos independientes.", "",
        "La auditoría no modifica etiquetas ni decide qué evidencia se usará para entrenar. Los conteos de sensibilidad son "
        "contrafactuales. Se preservaron los ficheros originales y no se reconstruyeron datasets, embeddings ni splits.", "",
        "[Resumen por familia](by_family.csv) · [Cobertura de entidades](entities.json) · [Impacto estructurado](impact.json)", "",
    ])
    (output/"report.md").write_text("\n".join(lines))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    run(p.parse_args().output)
