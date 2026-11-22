"""Resolve candidate epitope loci against the original archived FASTA."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from data_pipeline.scripts.global_epitope_labels.build import ROOT, write_json
from data_pipeline.scripts.source_audits.omitted_epitopes import archived_proteins, protein_url, resolve_parent


def occurrences(sequence, peptide):
    start = sequence.find(peptide)
    while start >= 0:
        yield start + 1, start + len(peptide)
        start = sequence.find(peptide, start + 1)


def coordinates(start, end):
    try:
        values = Decimal(start), Decimal(end)
        if all(x.is_finite() and x == x.to_integral_value() for x in values):
            return tuple(map(int, values))
    except InvalidOperation:
        pass
    return 0, 0


def coordinate_state(start, end):
    missing = [value.strip().lower() in {"", "nan", "na", "null"} for value in (start, end)]
    return ("both_absent" if all(missing) else
            "partially_absent" if any(missing) else "contradictory_or_invalid")


def run(dataset, raw, fasta, previous, output):
    config = json.loads((dataset / "config.json").read_text())
    baseline = json.loads((previous / "summary.json").read_text())
    if baseline["scope"] != "full":
        raise ValueError("The input must be the full previous audit.")
    if any(output.resolve().is_relative_to(root.resolve()) for root in (dataset, raw, fasta, previous)):
        raise ValueError("Use a separate report directory.")
    output.mkdir(parents=True, exist_ok=False)
    families = {s["mhc_family"]: s for s in config["sources"]}
    archived = archived_proteins(fasta, sorted({s["organism"] for s in families.values()}))
    counts = Counter()
    by_family = defaultdict(Counter)
    recovered = defaultdict(set)
    recovered_states = defaultdict(set)
    fasta_absent = 0
    displacements = Counter()
    coordinate_defects = Counter()
    event_fields = ("family", "event_index", "protein_url", "epitope", "original_start", "original_end",
                    "coordinate_status", "occurrence_count", "fasta_intervals", "resolution")
    with (output / "events.csv").open("w", newline="") as sink:
        writer = csv.writer(sink)
        writer.writerow(event_fields)
        for family, source in families.items():
            path = raw / Path(source["file"]).parent / "merged_unique_events.csv"
            with path.open(newline="", encoding="utf-8-sig") as handle:
                for i, row in enumerate(csv.DictReader(handle)):
                    url = protein_url(row["parent_id"])
                    peptide = row["epitope__name_canonical"].strip().upper()
                    if not url or not 1 <= len(peptide) <= 25:
                        continue
                    key, protein, _ = resolve_parent(archived, source["organism"], url)
                    if protein is None:
                        continue
                    raw_start, raw_end = (row[f"epitope__{s}_position"] for s in ("starting", "ending"))
                    start, end = coordinates(raw_start, raw_end)
                    if 1 <= start <= end <= len(protein) and protein[start - 1:end] == peptide:
                        continue
                    loci = list(occurrences(protein, peptide))
                    resolution = ("unique_in_fasta" if len(loci) == 1 else
                                  "multiple_in_fasta" if loci else "absent_from_fasta")
                    if not loci:
                        fasta_absent += 1
                    state = coordinate_state(raw_start, raw_end)
                    counts[resolution] += 1
                    counts[state] += 1
                    by_family[family][resolution] += 1
                    by_family[family][state] += 1
                    if not loci:
                        # The previous audit counted this as a separate evidence reason.
                        counts[f"outside_target_{state}"] += 1
                    if loci:
                        defect = ("outside_fasta_or_invalid_order" if not 1 <= start <= end <= len(protein)
                                  else "span_length_mismatch" if end - start + 1 != len(peptide)
                                  else "correct_length_wrong_residues")
                        coordinate_defects[defect] += 1
                    if len(loci) == 1:
                        recovered_start, recovered_end = loci[0]
                        displacements[recovered_start - start, recovered_end - end] += 1
                        class_key = key, peptide, loci[0]
                        recovered[class_key].add(family)
                        recovered_states[class_key, family].add(state)
                    writer.writerow((family, i, url, peptide, raw_start, raw_end, state, len(loci),
                                     "|".join(f"{a}-{b}" for a, b in loci), resolution))
            print(f"{family}: {by_family[family]['unique_in_fasta']:,} unique event loci", flush=True)

    previous_issues = baseline["evidence_issues"]
    if (counts["unique_in_fasta"] + counts["multiple_in_fasta"] !=
            previous_issues["missing_or_conflicting_epitope_coordinates"]
            or fasta_absent != previous_issues["epitope_absent_from_archived_fasta"]):
        raise ValueError("Raw-event counts do not reproduce the previous audit categories.")
    affected_rows = Counter()
    affected_sequences = set()
    distinct_windows = set()
    conflict_rows = 0
    examples = []
    previous_address = None
    row_conflict = False
    with (previous / "hits.csv").open(newline="") as src, (output / "matched_candidates.csv").open("w", newline="") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=[*reader.fieldnames, "inferred_start_1based", "inferred_end_1based",
                                                 "recovery_evidence_families", "has_original_coordinate_conflict"])
        writer.writeheader()
        for row in reader:
            if row["evidence"] != "sequence_only":
                continue
            family = row["family"]
            key, protein, _ = resolve_parent(archived, families[family]["organism"], row["protein_url"])
            start = int(row["window_start_1based"])
            window = row["window"]
            if protein is None or start < 1 or protein[start - 1:start - 1 + len(window)] != window:
                continue
            peptide = row["epitope"]
            ep_start = start + int(row["offset_0based"])
            ep_end = ep_start + len(peptide) - 1
            if ep_end >= start + len(window) or window[ep_start-start:ep_end-start+1] != peptide:
                continue
            class_key = key, peptide, (ep_start, ep_end)
            evidence = recovered.get(class_key, set()).intersection(row["evidence_families"].split("|"))
            if not evidence:
                continue
            conflict = any("contradictory_or_invalid" in recovered_states[class_key, fam] for fam in evidence)
            row.update(inferred_start_1based=ep_start, inferred_end_1based=ep_end,
                       recovery_evidence_families="|".join(sorted(evidence)), has_original_coordinate_conflict=int(conflict))
            writer.writerow(row)
            address = row["source_file"], row["source_row_index"]
            if address != previous_address:
                affected_rows[family] += 1
                conflict_rows += int(row_conflict)
                row_conflict = False
                previous_address = address
            row_conflict |= conflict
            affected_sequences.add(window)
            distinct_windows.add((key, start, window))
            if len(examples) < 4 and all(example["protein_url"] != row["protein_url"] for example in examples):
                examples.append(row)
    conflict_rows += int(row_conflict)
    summary = {
        "target_events": previous_issues["missing_or_conflicting_epitope_coordinates"],
        "event_counts": dict(counts), "target_original_coordinate_states": {
            state: counts[state] - counts[f"outside_target_{state}"]
            for state in ("both_absent", "partially_absent", "contradictory_or_invalid")
        },
        "target_coordinate_defects": dict(coordinate_defects),
        "unique_locus_displacements": [
            {"start_delta": a, "end_delta": b, "events": n}
            for (a, b), n in displacements.most_common()
        ],
        "events_by_family": {k: dict(v) for k, v in by_family.items()},
        "candidate_rows_reviewed": baseline["totals"]["candidate_rows"],
        "matched_rows": sum(affected_rows.values()), "matched_distinct_windows": len(distinct_windows),
        "matched_distinct_sequences": len(affected_sequences), "matched_rows_with_coordinate_conflict": conflict_rows,
        "matched_rows_by_family": dict(affected_rows), "examples": examples,
    }
    write_json(output / "summary.json", summary)
    lines = ["# Recuperación de coordenadas de epítopos", "",
             f"Se reprodujeron los **{summary['target_events']:,}** eventos del grupo original. "
             "La búsqueda mantuvo la URL completa y la versión del FASTA archivado de cada proteína.", "",
             "| Ocurrencias exactas en la proteína FASTA | Eventos |",
             "|---|---:|",
             f"| Una | {counts['unique_in_fasta']:,} |",
             f"| Varias | {counts['multiple_in_fasta']:,} |",
             "| Ninguna dentro del grupo de 102.654 | 0 |",
             f"| Ninguna, categoría separada de la auditoría original | {fasta_absent:,} |", "",
             "## Coordenadas fuente", ""]
    lines.extend(f"- `{state}`: {n:,} eventos del grupo original."
                 for state, n in summary["target_original_coordinate_states"].items())
    lines.extend(f"- `{defect}`: {n:,} eventos."
                 for defect, n in coordinate_defects.items())
    lines.extend(["", "Desplazamientos más frecuentes entre el intervalo fuente y el inferido: "
                  + ", ".join(f"({a:+d}, {b:+d}) en {n:,}" for (a, b), n in displacements.most_common(5))
                  + ". Los desplazamientos no son uniformes."])
    lines.extend(["", "Las coordenadas contradictorias o inválidas requieren revisión aunque la secuencia "
                  "tenga una única ocurrencia. Las coincidencias múltiples no se resolvieron por proximidad.", "",
                  "## Ventanas candidatas que contienen la ocurrencia única", "",
                  f"- {summary['matched_rows']:,} de {summary['candidate_rows_reviewed']:,} filas.",
                  f"- {summary['matched_distinct_windows']:,} ventanas por proteína y posición.",
                  f"- {summary['matched_distinct_sequences']:,} secuencias de ventana distintas.",
                  f"- {conflict_rows:,} filas tienen al menos un evento con coordenadas fuente contradictorias o inválidas.",
                  "", "| Familia de la ventana | Filas |", "|---|---:|"])
    lines.extend(f"| {family} | {affected_rows[family]:,} |" for family in families)
    lines.extend(["", "Las posiciones son 1-based e inclusivas e inferidas por una coincidencia única en FASTA. "
                  "El resultado se conserva por separado de los epítopos con coordenadas originales verificadas.",
                  "", "## Ejemplos", ""])
    lines.extend(f"- `{r['protein_url']}`, {r['family']}, ventana en {r['window_start_1based']}, "
                 f"epítopo `{r['epitope']}` inferido en {r['inferred_start_1based']}–{r['inferred_end_1based']}."
                 for r in examples)
    (output / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/global_epitope_labels")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--fasta", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.dataset, args.raw, args.fasta, args.previous, args.output)


if __name__ == "__main__":
    main()
