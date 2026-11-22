"""Audit known epitope containment within the exact archived parent protein."""

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3

import pyarrow.parquet as pq

from data_pipeline.scripts.global_epitope_labels.build import ROOT, row_path, write_json


def protein_url(value):
    return value.strip().removeprefix("https://").removeprefix("http://")


def archived_proteins(fasta_root, organisms):
    csv.field_size_limit(8 * 1024 * 1024)
    sequences = defaultdict(set)
    for organism in organisms:
        path = fasta_root / f"{organism}_parent_protein_fasta.csv"
        with path.open(newline="", encoding="utf-8-sig") as source:
            for row in csv.DictReader(source):
                url = protein_url(row["protein_url"])
                sequence = "".join(line.strip() for line in row["fasta"].splitlines()
                                   if not line.startswith(">")).upper()
                if url and sequence:
                    sequences[organism, url].add(sequence)
    return sequences


def resolve_parent(archived, organism, url):
    versions = archived.get((organism, url), ())
    if len(versions) == 1:
        sequence, = versions
        return (url, sequence), sequence, "archived_fasta"
    if versions:
        return (url, organism), None, "conflicting_fasta_versions"
    return (url, organism), None, "missing_fasta"


def positive_evidence(config, archived, raw_root):
    placed = defaultdict(lambda: defaultdict(set))
    unplaced = defaultdict(lambda: defaultdict(set))
    problems = Counter()
    unique = set()
    examples = []
    for source in config["sources"]:
        origin = Path(source["file"]).parent
        family = source["mhc_family"]
        path = raw_root / origin / "merged_unique_events.csv"
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                url = protein_url(row["parent_id"])
                peptide = row["epitope__name_canonical"].strip().upper()
                reason = None
                if not url or not peptide:
                    problems["missing_protein_or_epitope"] += 1
                    continue
                key, protein, parent_status = resolve_parent(archived, source["organism"], url)
                unique.add((key, peptide))
                try:
                    coordinates = [Decimal(row[f"epitope__{part}_position"]) for part in ("starting", "ending")]
                    if any(not value.is_finite() or value != value.to_integral_value() for value in coordinates):
                        raise ValueError("Nonintegral coordinates.")
                    start, end = map(int, coordinates)
                except (ValueError, InvalidOperation):
                    start, end = 0, 0
                if parent_status == "conflicting_fasta_versions":
                    reason = parent_status
                elif (protein is not None and 1 <= start <= end <= len(protein)
                      and protein[start - 1:end] == peptide):
                    if len(peptide) <= 25:
                        placed[key][start, end, peptide].add(family)
                    else:
                        problems["positive_longer_than_window"] += 1
                elif len(peptide) <= 25:
                    reason = (parent_status if protein is None else "missing_or_conflicting_epitope_coordinates")
                    if protein is None or peptide in protein:
                        unplaced[key][peptide].add(family)
                    else:
                        reason = "epitope_absent_from_archived_fasta"
                if reason:
                    problems[reason] += 1
                    if len(examples) < 20:
                        examples.append((family, url, peptide, start or "", end or "", reason))
    ordered = {key: (sorted(group), group) for key, group in placed.items()}
    return ordered, unplaced, unique, problems, examples


def find_hits(sequence, window_start, protein, coordinated, unplaced):
    window_end = window_start + len(sequence) - 1
    exact_window = (protein is not None and window_start > 0
                    and protein[window_start - 1:window_end] == sequence)
    hits = []
    if exact_window and coordinated:
        keys, families = coordinated
        i = bisect_left(keys, (window_start,))
        while i < len(keys) and keys[i][0] <= window_end:
            start, end, peptide = keys[i]
            if end <= window_end and sequence[start - window_start:end - window_start + 1] == peptide:
                hits.append(("coordinate_verified", peptide, start, end, start - window_start, families[keys[i]]))
            i += 1
    for peptide, families in sorted(unplaced.items()):
        offset = sequence.find(peptide)
        while offset >= 0:
            hits.append(("sequence_only", peptide, "", "", offset, families))
            offset = sequence.find(peptide, offset + 1)
    return hits, exact_window


def run(dataset, raw_root, fasta_root, output, limit):
    config = json.loads((dataset / "config.json").read_text())
    if json.loads((dataset / "summary.json").read_text())["status"] != "validated":
        raise ValueError("Expected a validated global dataset.")
    if any(output.resolve().is_relative_to(root.resolve()) for root in (dataset, raw_root, fasta_root)):
        raise ValueError("Audit output must be separate from the source dataset.")
    output.mkdir(parents=True, exist_ok=False)
    archived = archived_proteins(fasta_root, sorted({entry["organism"] for entry in config["sources"]}))
    placed, unplaced, known, issues, ambiguous_examples = positive_evidence(config, archived, raw_root)
    totals = Counter()
    proteins = set()
    family_totals = {}
    examples = []
    example_keys = set()
    seq_column = config["sequence_column"]
    columns = [seq_column, "protein_url", "protein_group_id", "group_id", "window_start", "source_row_index",
               "contains_epitope", "global_contains_epitope"]
    header = ["family", "protein_url", "protein_group_id", "group_id", "source_file", "source_row_index",
              "window_start_1based", "window", "original_label", "global_label", "evidence",
              "epitope", "epitope_start_1based", "epitope_end_1based", "offset_0based", "evidence_families"]
    index = sqlite3.connect(output / "audit_counts.sqlite")
    index.executescript("""
        CREATE TABLE sequences (status TEXT, seq TEXT, PRIMARY KEY(status, seq)) WITHOUT ROWID;
        CREATE TABLE windows (
            status TEXT, parent TEXT, version INTEGER, start INTEGER, seq TEXT,
            PRIMARY KEY(status,parent,version,start,seq)
        ) WITHOUT ROWID;
    """)
    version_ids = {}
    with (output / "hits.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for source in config["sources"]:
            local = Counter({key: 0 for key in ("rows", "unlabeled_rows", "coordinate_verified_rows",
                                               "sequence_only_rows", "sequence_only_without_verified_rows")})
            organism, family = source["organism"], source["mhc_family"]
            for batch in pq.ParquetFile(row_path(dataset, source)).iter_batches(batch_size=50_000, columns=columns):
                if limit is not None:
                    batch = batch.slice(0, max(0, limit - local["rows"]))
                for sequence, url, pgid, gid, window_start, row_index, original, label in zip(
                    *(column.to_pylist() for column in batch.columns)
                ):
                    url = protein_url(url)
                    key, protein, parent_status = resolve_parent(archived, organism, url)
                    proteins.add(key)
                    local["rows"] += 1
                    if label:
                        continue
                    local["unlabeled_rows"] += 1
                    try:
                        start = int(window_start)
                    except (ValueError, TypeError):
                        start = 0
                    candidates = unplaced.get(key, {})
                    if parent_status == "conflicting_fasta_versions":
                        local["ambiguous_parent_rows"] += 1
                    hits, exact = find_hits(sequence, start, protein, placed.get(key), candidates)
                    if not exact:
                        local["unverified_window_coordinates"] += 1
                        if key in placed and parent_status != "conflicting_fasta_versions":
                            coordinate_only = defaultdict(set)
                            for (_, _, peptide), families in placed[key][1].items():
                                coordinate_only[peptide].update(families)
                            fallback = {k: v for k, v in coordinate_only.items() if k not in candidates}
                            more_hits, _ = find_hits(sequence, start, None, None, fallback)
                            hits.extend(more_hits)
                    statuses = {hit[0] for hit in hits}
                    if statuses == {"sequence_only"}:
                        local["sequence_only_without_verified_rows"] += 1
                    for status in statuses:
                        local[f"{status}_rows"] += 1
                        version = version_ids.setdefault(key, len(version_ids))
                        index.execute("INSERT OR IGNORE INTO sequences VALUES (?,?)", (status, sequence))
                        index.execute("INSERT OR IGNORE INTO windows VALUES (?,?,?,?,?)",
                                      (status, url, version, start, sequence))
                    for status, peptide, ep_start, ep_end, offset, families in hits:
                        record = dict(zip(header, (family, url, pgid, gid, source["file"], row_index,
                                                  start, sequence, original, label, status, peptide,
                                                  ep_start, ep_end, offset, "|".join(sorted(families)))))
                        writer.writerow(record)
                        example_key = status, url, peptide
                        if example_key not in example_keys and sum(
                            example["evidence"] == status for example in examples
                        ) < 4:
                            example_keys.add(example_key)
                            examples.append(record)
                index.commit()
                if limit is not None and local["rows"] >= limit:
                    break
            family_totals[family] = dict(local)
            totals.update(local)
            print(f"{family}: reviewed {local['rows']:,}, coordinate verified "
                  f"{local['coordinate_verified_rows']:,}, sequence-only {local['sequence_only_rows']:,}", flush=True)
    distinct = {table: dict(index.execute(f"SELECT status, COUNT(*) FROM {table} GROUP BY status"))
                for table in ("sequences", "windows")}
    for table, keys in (("sequences", "seq"), ("windows", "parent,version,start,seq")):
        distinct[table]["any_candidate"] = index.execute(
            f"SELECT COUNT(*) FROM (SELECT 1 FROM {table} GROUP BY {keys})"
        ).fetchone()[0]
    index.close()
    totals["candidate_rows"] = totals["coordinate_verified_rows"] + totals["sequence_only_without_verified_rows"]
    with (output / "ambiguous_evidence_examples.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("family", "protein_url", "epitope", "start", "end", "reason"))
        writer.writerows(ambiguous_examples)
    summary = {
        "scope": "full" if limit is None else "prefix_per_family", "limit": limit,
        "analysed_proteins": len(proteins), "known_epitope_sequences": len({p for _, p in known}),
        "known_protein_epitope_pairs": len(known), "placed_protein_epitope_occurrences": sum(len(v[0]) for v in placed.values()),
        "totals": dict(totals), "distinct": distinct, "families": family_totals,
        "evidence_issues": dict(issues), "examples": examples,
    }
    write_json(output / "summary.json", summary)
    scope = "Corpus completo." if limit is None else f"Primeras {limit:,} filas de cada familia."
    lines = ["# Auditoría de epítopos positivos potencialmente omitidos", "",
             f"{scope} La evidencia se leyó completa de las once familias.", "",
             f"- Proteínas revisadas: {summary['analysed_proteins']:,}",
             f"- Epítopos positivos distintos: {summary['known_epitope_sequences']:,}",
             f"- Pares proteína–epítopo: {summary['known_protein_epitope_pairs']:,}",
             f"- Ocurrencias positivas con coordenadas verificadas y longitud ≤25: {summary['placed_protein_epitope_occurrences']:,}",
             f"- Filas revisadas: {totals['rows']:,} ({totals['unlabeled_rows']:,} sin anotación global positiva)", "",
             "| Evidencia | Filas | Ventanas distintas | Secuencias distintas |",
             "|---|---:|---:|---:|"]
    for status in ("coordinate_verified", "sequence_only"):
        lines.append(f"| {status} | {totals[f'{status}_rows']:,} | {distinct['windows'].get(status, 0):,} "
                     f"| {distinct['sequences'].get(status, 0):,} |")
    lines.append(f"| Cualquier candidato | {totals['candidate_rows']:,} | {distinct['windows']['any_candidate']:,} "
                 f"| {distinct['sequences']['any_candidate']:,} |")
    lines.extend(["", f"Filas con coincidencias exclusivamente de secuencia: {totals['sequence_only_without_verified_rows']:,}. "
                  "Una fila puede aparecer en las dos categorías.", "",
                  "| Familia | Filas revisadas | Coordenadas verificadas | Coincidencia de secuencia |",
                  "|---|---:|---:|---:|"])
    for family, counts in family_totals.items():
        lines.append(f"| {family} | {counts['rows']:,} | {counts['coordinate_verified_rows']:,} "
                     f"| {counts['sequence_only_rows']:,} |")
    lines.extend(["", "## Ambigüedades y revisión", "",
                  f"- Ventanas sin coordenadas verificadas contra FASTA: {totals['unverified_window_coordinates']:,}.",
                  f"- Ventanas con versiones FASTA incompatibles: {totals['ambiguous_parent_rows']:,}."])
    lines.extend(f"- Eventos de evidencia con `{key}`: {count:,}." for key, count in issues.items())
    lines.extend(["", "Los identificadores de proteína se compararon por URL completa y secuencia FASTA cuando "
                  "estaba disponible. Las versiones conflictivas dentro de un mismo origen se excluyeron de los "
                  "hallazgos. Los aciertos por secuencia no confirman el locus. La muestra por prefijo no permite extrapolar tasas.",
                  "Revisar los aciertos por coordenadas y resolver identidad y locus de los ambiguos antes de decidir cambios de etiqueta.",
                  "", "## Ejemplos", ""])
    for entry in examples:
        lines.append(f"- {entry['evidence']} en `{entry['protein_url']}`, {entry['family']}, "
                     f"ventana `{entry['window']}` en {entry['window_start_1based']}, "
                     f"epítopo `{entry['epitope']}` ({entry['epitope_start_1based'] or '?'}–"
                     f"{entry['epitope_end_1based'] or '?'}), etiqueta global {entry['global_label']}.")
    if not examples:
        lines.append("La muestra no produjo candidatos.")
    (output / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/global_epitope_labels")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--fasta", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--rows-per-family", type=int)
    scope.add_argument("--full", action="store_true")
    args = parser.parse_args()
    if args.rows_per_family is not None and args.rows_per_family < 1:
        parser.error("Sample size must be positive.")
    run(args.dataset, args.raw, args.fasta, args.output, args.rows_per_family)


if __name__ == "__main__":
    main()
