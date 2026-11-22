"""Summarize a validated phase-one build without loading feature data."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

from data_pipeline.scripts.global_epitope_labels.build import write_json


def shifted_support(output, family):
    evidence_path = output / "evidence_verified" / f"{family}.parquet"
    columns = ["event_id", "source_start", "source_end", "parent_start", "parent_end"]
    shifted = set()
    for batch in pq.ParquetFile(evidence_path).iter_batches(columns=columns):
        for event, a, b, start, end in zip(*(column.to_pylist() for column in batch.columns)):
            if a is not None and (a, b) != (start, end):
                shifted.add(event)
    only_shifted = 0
    if shifted:
        trace = output / "provenance" / f"{family}.parquet"
        for batch in pq.ParquetFile(trace).iter_batches(columns=["contains_epitope", "verified_event_ids"]):
            positives = pc.filter(batch.column(1), pc.equal(batch.column(0), 1))
            only_shifted += sum(all(event in shifted for event in ids) for ids in positives.to_pylist())
    return dict(shifted_assay_records=len(shifted), positive_windows_supported_only_by_shifted_records=only_shifted)


def holdout_reasons(output, family):
    reasons = {}
    evidence = output / "evidence_pending" / f"{family}.parquet"
    for batch in pq.ParquetFile(evidence).iter_batches(columns=["event_id", "chemistry", "reason"]):
        for event, chemistry, reason in zip(*(column.to_pylist() for column in batch.columns)):
            if chemistry != "simple":
                reasons[event] = reason
    counts = Counter()
    holdouts = output / "holdouts" / f"{family}.parquet"
    for batch in pq.ParquetFile(holdouts).iter_batches(columns=["excluded_event_ids"]):
        for events in batch.column(0).to_pylist():
            counts[" + ".join(sorted({reasons[event] for event in events}))] += 1
    return counts


def structure_gaps(output, family):
    proteins = output / "proteins" / f"{family}.parquet"
    columns = ["parent_url", "parent_sha256", "expected_windows", "structure_status"]
    gaps = {
        row["parent_url"]: row
        for row in pq.read_table(proteins, columns=columns).to_pylist()
        if row["structure_status"] and row["structure_status"] != "matched"
    }
    if not gaps:
        return []
    holdouts = output / "holdouts" / f"{family}.parquet"
    excluded = Counter()
    for batch in pq.ParquetFile(holdouts).iter_batches(columns=["parent_url"]):
        excluded.update(url for url in batch.column(0).to_pylist() if url in gaps)
    return [
        dict(family=family, parent_url=url, parent_sha256=row["parent_sha256"],
             structure_status=row["structure_status"], binary_windows=row["expected_windows"] - excluded[url])
        for url, row in sorted(gaps.items())
    ]


def report(output):
    summary = json.loads((output / "summary.json").read_text())
    if summary["status"] != "validated":
        raise ValueError("A validated build is required.")
    totals = Counter()
    detail = {}
    structure_windows = Counter()
    remapping = Counter()
    excluded_reasons = Counter()
    gaps = []
    lines = [
        "# NAP-CNB v2 · ventanas originales y estructura secundaria",
        "",
        f"Destino: `{output.resolve()}`.",
        "",
        "| Familia | Proteínas elegibles | Ventanas generadas | Ventanas binarias | Positivos | Negativos | Holdouts | C/H/E verificada | Originales históricos | Posiciones históricas | Positivos históricos por posición |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for family, stats in summary["families"].items():
        previous = summary["previous"][family]
        windows = stats.get("windows", 0)
        positive = stats.get("positive_windows", 0)
        held_out = stats.get("held_out_windows", 0)
        fields = dict(
            eligible_proteins=stats.get("proteins_eligible", 0),
            generated_windows=windows + held_out, windows=windows, positive=positive,
            negative=windows - positive, held_out=held_out,
            structure_matched=stats.get("structural_windows_matched", 0),
            old_rows=previous.get("old_rows", 0),
            old_positions=previous.get("old_unique_positions", 0),
            old_positive_positions=previous.get("old_positive_positions", 0),
        )
        if fields["old_positions"] - previous.get("old_positions_missing_in_rebuild", 0) + previous.get(
            "new_positions", 0
        ) != windows:
            raise ValueError(f"Historical position counts do not reconcile for {family}.")
        totals.update(fields)
        by_structure = {k.removeprefix("structural_windows_"): v
                        for k, v in stats.items() if k.startswith("structural_windows_")}
        if sum(by_structure.values()) != windows:
            raise ValueError(f"Incomplete structural coverage accounting for {family}.")
        structure_windows.update(by_structure)
        family_gaps = structure_gaps(output, family)
        if sum(row["binary_windows"] for row in family_gaps) != windows - fields["structure_matched"]:
            raise ValueError(f"Incomplete protein-level structural accounting for {family}.")
        gaps.extend(family_gaps)
        lines.append("| " + " | ".join([family, *(f"{v:,}" for v in fields.values())]) + " |")
        shifted = shifted_support(output, family)
        reasons = holdout_reasons(output, family)
        if sum(reasons.values()) != fields["held_out"]:
            raise ValueError(f"Incomplete holdout accounting for {family}.")
        excluded_reasons.update(reasons)
        remapping.update(shifted)
        detail[family] = dict(fields, remapping=shifted, historical=previous, verification_methods=stats["methods"],
                              pending_candidate_windows=stats.get("pending_candidate_windows", 0),
                              holdout_reasons=reasons, modified_assay_records=stats.get("events_modified", 0),
                              structural_windows=by_structure,
                              structural_proteins={k.removeprefix("structural_proteins_"): v
                                                   for k, v in stats.items() if k.startswith("structural_proteins_")})
    global_stats = summary["global_index"]
    coverage = 100 * totals["structure_matched"] / max(1, totals["windows"])
    for folder in ("families", "holdouts"):
        for family in detail:
            rows = pq.ParquetFile(output / folder / f"{family}.parquet").metadata.num_rows
            key = "windows" if folder == "families" else "held_out"
            if rows != detail[family][key]:
                raise ValueError(f"Footer disagrees with the summary for {folder}/{family}.")
    comparison = Counter()
    methods = Counter()
    structural = Counter()
    for stats in detail.values():
        comparison.update(stats["historical"])
        methods.update(stats["verification_methods"])
        structural.update(stats["structural_proteins"])
    comparison["old_duplicate_position_rows"] = totals["old_rows"] - totals["old_positions"]
    lines += [
        "| **Total** | " + " | ".join(f"{v:,}" for v in totals.values()) + " |",
        "",
        f"- Secuencias primarias únicas: **{global_stats.get('unique_sequences', 0):,}**.",
        f"- Combinaciones únicas de secuencia y C/H/E verificada: **{global_stats.get('unique_primary_secondary_pairs', 0):,}**.",
        f"- Cobertura estructural: **{coverage:.3f} %**. Las cadenas faltantes se guardan como null con su motivo.",
        f"- Ventanas binarias con evidencia simple pendiente en una posible posición: "
        f"**{sum(stats['pending_candidate_windows'] for stats in detail.values()):,}**. "
        "La procedencia identifica los candidatos y su motivo.",
        f"- Ventanas por estado estructural: {dict(sorted(structure_windows.items()))}.",
        f"- Proteínas por familia con estado estructural: {dict(sorted(structural.items()))}. El detalle por proteína y las ventanas afectadas están en `structure_gaps.tsv`.",
        "",
        "## Cambios respecto al histórico",
        "",
        f"- El histórico contiene **{comparison['old_duplicate_position_rows']:,}** filas adicionales "
        "al contar cada posición una sola vez. "
        "V2 conserva una observación por familia–proteína–inicio y enlaza todas sus evidencias.",
        f"- Holdouts totales: **{totals['held_out']:,}**. De ellos, **{comparison['old_positive_positions_in_holdouts']:,}** "
        "coincidían con un positivo histórico por posición. Los motivos e IDs están en `holdouts/` y `evidence_pending/`.",
        f"- Holdouts por combinación de motivos: {dict(sorted(excluded_reasons.items()))}. Se excluyeron "
        f"**{sum(stats['modified_assay_records'] for stats in detail.values()):,}** registros de ensayo modificados "
        "como fuente de positivos.",
        f"- Salieron del conjunto binario **{comparison['old_positions_missing_in_rebuild']:,}** posiciones "
        "históricas. Este recuento incluye las reservas y las posiciones que el constructor ya no emite.",
        f"- Posiciones nuevas: **{comparison['new_positions']:,}**, incluidas **{comparison['positions_on_previously_omitted_proteins']:,}** "
        "en pares familia–proteína ausentes del histórico. Cambiaron de 0 a 1 "
        f"**{comparison['position_0_to_1']:,}** posiciones y de 1 a 0 **{comparison['position_1_to_0']:,}**.",
        f"- **{remapping['shifted_assay_records']:,}** registros de ensayo verificados tienen coordenadas parent "
        "distintas de las source originales. "
        f"**{remapping['positive_windows_supported_only_by_shifted_records']:,}** ventanas positivas se apoyan "
        "exclusivamente en registros remapeados con desplazamiento.",
        f"- Métodos de verificación por registro de ensayo: {dict(sorted(methods.items()))}. "
        "Los cambios por posición pueden combinar remapeos y exclusiones de evidencia.",
        "",
        "## Archivos",
        "",
        "- `families/` contiene una ventana por posición, su etiqueta familiar y el recorte C/H/E cuando se verificó.",
        "- `global_index.parquet` asigna etiqueta global 1 a cada secuencia con al menos una "
        "observación positiva entre las familias incluidas.",
        "- `references/`, `proteins/`, `provenance/`, `evidence_verified/`, `evidence_pending/` y `holdouts/` documentan las decisiones.",
    ]
    gap_path = output / "structure_gaps.tsv"
    partial_gap_path = gap_path.with_suffix(".partial")
    with partial_gap_path.open("w", encoding="utf-8", newline="") as sink:
        fields = ["family", "parent_url", "parent_sha256", "structure_status", "binary_windows"]
        writer = csv.DictWriter(sink, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(gaps)
    partial_gap_path.replace(gap_path)
    permanent = sum(p.stat().st_size for p in output.rglob("*") if p.is_file()
                    and p.name not in {"phase1_report.md", "phase1_metrics.json", ".run.lock", "global_work.sqlite"}
                    and not p.name.endswith(("-shm", "-wal", ".partial"))
                    and p.relative_to(output).parts[0] not in {"raw", ".family_work"})
    lines += ["", f"Tamaño lógico de datos y metadatos permanentes del destino, incluidos los checkpoints y la caché de referencias: **{permanent:,} bytes**.", ""]
    write_json(output / "phase1_metrics.json", dict(families=detail, totals=totals,
               global_index=global_stats, structure_coverage_percent=coverage,
               structural_proteins=structural, structural_windows=structure_windows,
               historical=comparison, remapping=remapping, holdout_reasons=excluded_reasons,
               permanent_bytes=permanent))
    (output / "phase1_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    report(parser.parse_args().output)
