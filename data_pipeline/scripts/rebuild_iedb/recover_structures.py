"""Recover archived whole-protein predictions for validated phase-one gaps."""

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from .rebuild import FAMILY_META, accession, load_archived, normalize_url, signature

WINDOW_FIELDS = [
    "window_id", "family", "parent_url", "parent_sha256", "parent_accession", "parent_version",
    "window_start", "window_end", "sequence", "secondary_structure", "structure_status",
]
INDEX_FIELDS = [
    "window_id", "parent_url", "parent_sha256", "secondary_structure",
    "structure_prediction_id", "verification_method", "validation_status",
]


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def accession_base(url):
    return accession(url).split(".")[0].split("-")[0].upper()


def selected_rows(path, column, values, fields):
    ordered = sorted(values)
    if not ordered:
        return
    source = ds.dataset(path, format="parquet")
    for fragment in source.get_fragments():
        metadata = fragment.metadata
        column_index = metadata.schema.names.index(column)
        matching = []
        for index in range(metadata.num_row_groups):
            stats = metadata.row_group(index).column(column_index).statistics
            if stats is None or not stats.has_min_max:
                matching.append(index)
                continue
            left = bisect_left(ordered, stats.min)
            if left < len(ordered) and ordered[left] <= stats.max:
                matching.append(index)
        if matching:
            scanner = ds.Scanner.from_fragment(
                fragment.subset(row_group_ids=matching), columns=fields,
                filter=ds.field(column).isin(ordered), batch_size=50_000,
            )
            yield from scanner.to_batches()


def load_gaps(root, summary):
    cases = defaultdict(list)
    by_family = defaultdict(dict)
    with (root / "structure_gaps.tsv").open(newline="") as stream:
        for gap in csv.DictReader(stream, delimiter="\t"):
            family, url = gap["family"], gap["parent_url"]
            if url in by_family[family]:
                raise ValueError(f"Duplicate gap for {family}/{url}")
            gap["binary_windows"] = int(gap["binary_windows"])
            by_family[family][url] = gap
    for family, gaps in by_family.items():
        found = set()
        fields = ["url", "accession", "version", "sequence", "sha256", "provider"]
        for batch in selected_rows(root / "references" / f"{family}.parquet", "url", gaps, fields):
            for ref in batch.to_pylist():
                url = ref["url"]
                gap = gaps[url]
                if url in found or gap["parent_sha256"] != ref["sha256"] or digest(ref["sequence"]) != ref["sha256"]:
                    raise ValueError(f"Reference checksum or uniqueness failure for {family}/{url}")
                found.add(url)
                key = (ref["accession"], ref["version"], ref["sha256"])
                gap.update(ref)
                cases[key].append(gap)
        if found != gaps.keys():
            raise ValueError(f"Missing protein references for {family}")
    expected = Counter()
    for stats in summary["validation"].values():
        for key, count in stats.items():
            if key.startswith("structural_windows_") and key != "structural_windows_matched":
                expected[key.removeprefix("structural_windows_")] += count
    observed = Counter()
    for gaps in cases.values():
        for gap in gaps:
            observed[gap["structure_status"]] += gap["binary_windows"]
    if observed != expected:
        raise ValueError("Gap inventory disagrees with the validated window counts")
    return cases


def scan_archives(inputs, references, cases):
    wanted_hashes = {key[2] for key in cases}
    wanted_bases = {accession_base(gap["url"]) for gaps in cases.values() for gap in gaps}
    exact = defaultdict(list)
    related = defaultdict(list)
    manifest = []
    for organism, path in inputs.items():
        checksum = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                checksum.update(block)
        manifest.append(dict(organism=organism, path=str(path), sha256=checksum.hexdigest()))
        with path.open(newline="") as stream:
            for record, row in enumerate(csv.DictReader(stream), 1):
                url = normalize_url(row["protein_url"])
                sequence = row["sequence"].strip()
                structure = row["secondary_structure"].strip()
                sha = digest(sequence)
                base = accession_base(url)
                if sha not in wanted_hashes and base not in wanted_bases:
                    continue
                ref = references.get((organism, url))
                version = ref.version if ref and ref.sequence == sequence else ""
                prediction = dict(organism=organism, source_file=str(path), source_record=record,
                                  source_url=url, source_accession=accession(url), source_version=version,
                                  full_sequence_sha256=sha, sequence=sequence, structure=structure,
                                  prediction_id=digest(f"{sequence}\n{structure}"))
                if sha in wanted_hashes:
                    exact[sha].append(prediction)
                if base in wanted_bases:
                    related[base].append(prediction)
    return exact, related, manifest


def decide(gaps, exact, related):
    sequence = gaps[0]["sequence"]
    if any(gap["sequence"] != sequence for gap in gaps):
        raise ValueError("Inconsistent sequence for the same protein identity")
    urls = {gap["url"] for gap in gaps}
    exact = [record for record in exact if record["sequence"] == sequence]
    valid = [record for record in exact if len(record["structure"]) == len(sequence)
             and not set(record["structure"]) - set("CHE")]
    structures = {record["structure"] for record in valid}
    if len(structures) > 1:
        return "ambiguous_prediction", valid
    if valid:
        return "recovered", valid
    if exact:
        reason = ("incompatible_length" if all(len(record["structure"]) != len(sequence) for record in exact)
                  else "invalid_structure_alphabet")
        return reason, exact
    if any(record["source_url"] in urls for record in related):
        return "incompatible_full_sequence", related
    if related:
        return "different_version_or_isoform", related
    return "prediction_not_found_in_archives", []


def recover_window(row, gap, structure, method):
    start, end = row["window_start"], row["window_end"]
    identity = ("parent_url", "parent_sha256", "parent_accession", "parent_version", "structure_status")
    expected = (gap["url"], gap["sha256"], gap["accession"], gap["version"], gap["structure_status"])
    if tuple(row[key] for key in identity) != expected or row["secondary_structure"] is not None:
        raise ValueError(f"Window is incompatible with the gap inventory: {row['window_id']}")
    if (not 1 <= start <= end <= len(gap["sequence"]) or end != start + 24
            or row["sequence"] != gap["sequence"][start - 1:end]
            or row["window_id"] != f"{row['family']}|{gap['url']}|{start}"):
        raise ValueError(f"Invalid original coordinates: {row['window_id']}")
    cropped = structure["structure"][start - 1:end]
    if len(cropped) != 25 or set(cropped) - set("CHE"):
        raise ValueError(f"Invalid C/H/E crop: {row['window_id']}")
    return dict(window_id=row["window_id"], parent_url=gap["url"], parent_sha256=gap["sha256"],
                secondary_structure=cropped, structure_prediction_id=structure["prediction_id"],
                verification_method=method, validation_status="verified")


def write_overlay(root, output, recovered):
    counts = Counter()
    rows_by_family = {}
    schema = pa.schema([(field, pa.string()) for field in INDEX_FIELDS])
    with pq.ParquetWriter(output / "window_structures.parquet", schema, compression="zstd") as writer:
        for family, gaps in recovered.items():
            observed = defaultdict(set)
            for batch in selected_rows(root / "families" / f"{family}.parquet", "parent_url", gaps, WINDOW_FIELDS):
                rows = []
                for row in batch.to_pylist():
                    url, start = row["parent_url"], row["window_start"]
                    gap, prediction, method = gaps[url]
                    if row["family"] != family or start in observed[url]:
                        raise ValueError(f"Unexpected family or duplicate locus: {row['window_id']}")
                    observed[url].add(start)
                    rows.append(recover_window(row, gap, prediction, method))
                    counts[method] += 1
                writer.write_table(pa.Table.from_pylist(rows, schema=schema))
            for url, (gap, _, _) in gaps.items():
                if len(observed[url]) != gap["binary_windows"]:
                    raise ValueError(f"Incomplete recovery for {family}/{url}")
            rows_by_family[family] = sum(map(len, observed.values()))
    if pq.ParquetFile(output / "window_structures.parquet").metadata.num_rows != counts.total():
        raise ValueError("Overlay footer disagrees with validated rows")
    return counts, rows_by_family


def write_tsv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def run(root, output):
    root, output = root.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("Choose a new output directory outside phase one")
    summary = json.loads((root / "summary.json").read_text())
    config = json.loads((root / "config.json").read_text())
    if summary["status"] != "validated" or summary["scope"] != "full":
        raise ValueError("A validated full phase-one dataset is required")
    inputs = {name: Path(record[0]) for name, record in config["structure_inputs"].items()}
    for record in [*config["structure_inputs"].values(), *config["fasta"]]:
        if signature(Path(record[0])) != record:
            raise ValueError(f"Archived phase-one input changed: {record[0]}")
    watched = [root / name for name in ("summary.json", "config.json", "global_index.parquet", "structure_gaps.tsv")]
    watched += [root / folder / f"{family}.parquet" for family in config["scope"]
                for folder in ("families", "references")]
    watched += list(inputs.values()) + [Path(record[0]) for record in config["fasta"]]
    before = [signature(path) for path in watched]
    cases = load_gaps(root, summary)
    old_references = load_archived(Path(config["fasta"][0][0]).parent)
    exact, related, sources = scan_archives(inputs, old_references, cases)

    recovered = defaultdict(dict)
    proteins, protein_sources = [], []
    protein_counts, window_counts = Counter(), Counter()
    pending_hashes = defaultdict(set)
    usable_prediction_hashes = set()
    outcomes_by_original_status = defaultdict(Counter)
    predictions = set()
    for (acc, version, sha), gaps in sorted(cases.items()):
        aliases = sorted({gap["url"] for gap in gaps})
        # A family can contain two URLs for the same accession and sequence.
        family_gaps = Counter()
        for gap in gaps:
            family_gaps[gap["family"]] += gap["binary_windows"]
        candidates = [record for base in sorted({accession_base(url) for url in aliases})
                      for record in related.get(base, ())]
        status, records = decide(gaps, exact.get(sha, ()), candidates)
        if status in {"recovered", "ambiguous_prediction"}:
            usable_prediction_hashes.add(sha)
        for gap in gaps:
            outcomes_by_original_status[gap["structure_status"]][status] += gap["binary_windows"]
        protein_counts[status] += 1
        window_counts[status] += sum(family_gaps.values())
        proteins.append(dict(parent_accession=acc, parent_version=version, parent_sha256=sha,
                             length=len(gaps[0]["sequence"]), parent_urls="|".join(aliases),
                             parent_providers="|".join(sorted({gap["provider"] for gap in gaps})),
                             original_statuses="|".join(sorted({gap["structure_status"] for gap in gaps})),
                             windows_by_family=json.dumps(family_gaps, sort_keys=True),
                             binary_windows=sum(family_gaps.values()), recovery_status=status))
        for record in records:
            provenance = {key: value for key, value in record.items() if key not in {"sequence", "structure"}}
            protein_sources.append(dict(parent_accession=acc, parent_version=version, parent_sha256=sha,
                                        recovery_status=status, **provenance))
        if status != "recovered":
            pending_hashes[status].add(sha)
            continue
        prediction = records[0]  # Every valid record has the same full sequence and structure.
        predictions.add(prediction["prediction_id"])
        for gap in gaps:
            method = ("exact_full_sequence_same_url" if any(
                record["source_url"] == gap["url"] and record["organism"] == FAMILY_META[gap["family"]][0]
                for record in records
            ) else "exact_full_sequence_other_identifier")
            recovered[gap["family"]][gap["url"]] = gap, prediction, method

    with TemporaryDirectory(prefix=".structure_recovery_", dir=output.parent) as scratch:
        staged = Path(scratch) / output.name
        staged.mkdir()
        counts, by_family = write_overlay(root, staged, recovered)
        if counts.total() != window_counts["recovered"]:
            raise ValueError("Recovery totals disagree with the gap inventory")
        if before != [signature(path) for path in watched]:
            raise ValueError("An original input changed during recovery")
        protein_fields = [
            "parent_accession", "parent_version", "parent_sha256", "length", "parent_urls",
            "parent_providers", "original_statuses", "windows_by_family", "binary_windows", "recovery_status",
        ]
        write_tsv(staged / "proteins.tsv", proteins, protein_fields)
        source_fields = [
            "parent_accession", "parent_version", "parent_sha256", "recovery_status", "organism",
            "source_file", "source_record", "source_url", "source_accession", "source_version",
            "full_sequence_sha256", "prediction_id",
        ]
        write_tsv(staged / "prediction_sources.tsv", protein_sources, source_fields)
        data = dict(sources=sources, protein_counts=protein_counts, window_counts=window_counts,
                    distinct_sequences=len({key[2] for key in cases}), windows_by_method=counts,
                    phase1_input_signatures=before[:4 + 2 * len(config["scope"])],
                    recovered_source_rows_with_verified_version=sum(
                        bool(row["source_version"]) for row in protein_sources if row["recovery_status"] == "recovered"
                    ),
                    recovered_windows_by_family=by_family, validated_predictions=len(predictions),
                    pending_distinct_sequences={key: len(hashes) for key, hashes in pending_hashes.items()},
                    windows_by_original_status=outcomes_by_original_status,
                    proteins_without_valid_prediction=sum(
                        row["parent_sha256"] not in usable_prediction_hashes for row in proteins
                    ),
                    sequences_without_valid_prediction=len(
                        set().union(*pending_hashes.values()) - usable_prediction_hashes
                    ))
        write_report(staged, root, data, summary)
        staged.rename(output)


def write_report(output, root, data, summary):
    binary = summary["global_index"]["observations"]
    before = sum(stats.get("structural_windows_matched", 0) for stats in summary["validation"].values())
    recovered = data["window_counts"]["recovered"]
    remaining = binary - before - recovered
    assert remaining == sum(data["window_counts"].values()) - recovered
    data.update(binary_windows=binary, matched_before=before, matched_after=before + recovered,
                remaining_windows=remaining, coverage_after_percent=100 * (before + recovered) / binary,
                artifact_bytes={path.name: path.stat().st_size for path in output.iterdir()})
    (output / "metrics.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# NAP-CNB v2 · recuperación de estructura secundaria",
        "",
        f"Base validada en `{root}`.",
        "",
        "| Métrica | Antes | Después |",
        "|---|---:|---:|",
        f"| Ventanas binarias | {binary:,} | {binary:,} |",
        f"| Ventanas con C/H/E verificada | {before:,} | {before + recovered:,} |",
        f"| Ventanas sin C/H/E | {binary - before:,} | {remaining:,} |",
        f"| Cobertura estructural | {100 * before / binary:.3f} % | {data['coverage_after_percent']:.3f} % |",
        "",
        f"Se investigaron **{sum(data['protein_counts'].values()):,}** proteínas, agrupadas por accession, "
        f"versión y hash completo, con **{data['distinct_sequences']:,}** secuencias completas distintas. "
        f"Se recuperaron **{data['protein_counts']['recovered']:,}** proteínas y **{recovered:,}** ventanas.",
        "",
        "| Resultado | Proteínas únicas | Ventanas binarias |",
        "|---|---:|---:|",
    ]
    labels = {
        "recovered": "Recuperada", "ambiguous_prediction": "Predicciones completas discrepantes",
        "incompatible_length": "Longitud incompatible", "invalid_structure_alphabet": "Alfabeto incompatible",
        "incompatible_full_sequence": "Secuencia incompatible bajo la misma URL",
        "different_version_or_isoform": "Versión o isoforma relacionada con secuencia distinta",
        "prediction_not_found_in_archives": "Predicción completa sin localizar en los archivos consultados",
    }
    for status, count in sorted(data["protein_counts"].items()):
        lines.append(f"| {labels[status]} | {count:,} | {data['window_counts'][status]:,} |")
    lines += [
        "",
        f"Con los archivos localizados, **{data['proteins_without_valid_prediction']:,}** proteínas "
        f"requieren predicción, con **{data['sequences_without_valid_prediction']:,}** secuencias completas distintas. "
        "",
        "",
        "## Fuentes y verificación",
        "",
    ]
    for original, outcomes in sorted(data["windows_by_original_status"].items()):
        lines.append(f"- Entre las {sum(outcomes.values()):,} ventanas con estado previo `{original}`, "
                     f"se recuperaron {outcomes.get('recovered', 0):,}.")
    lines.append("")
    if data["windows_by_original_status"].get("unverified_archived_reference", {}).get("recovered"):
        lines += [
            "Fase 1 exigía una referencia del FASTA archivado con versión o cadena fijada. "
            "La recuperación acredita la secuencia completa directamente en la fila de ProteinUnet. "
            f"El FASTA de la misma URL acreditó una versión para "
            f"{data['recovered_source_rows_with_verified_version']:,} registros de procedencia recuperados. "
            "Las demás versiones se conservan vacías.",
            "",
        ]
    for source in data["sources"]:
        lines.append(f"- `{source['path']}` con SHA-256 `{source['sha256']}`.")
    lines += [
        "- Los CSV ya estaban extraídos del archivo intermedio y se cruzaron con los FASTA archivados y "
        "las referencias completas de los casos de fase 1. La versión de la predicción se registra "
        "cuando el FASTA de la misma URL acredita una coincidencia completa.",
        f"- FASTA archivados y referencias de fase 1 en `{root / 'references'}`.",
        "- Cada recuperación exigió igualdad literal de la secuencia completa, longitud global compatible, "
        "alfabeto C/H/E y unanimidad de las predicciones válidas encontradas para la secuencia. "
        "El recorte primario y el estructural comparten coordenadas inclusivas de base 1.",
        "- Se comprobaron pertenencia al inventario de ausencias, unicidad por ventana, recuentos por proteína, "
        "el pie del Parquet y las firmas de los archivos de entrada antes y después de la lectura. "
        "Se usaron los límites por URL del Parquet para descartar grupos de filas ajenos a los casos pendientes.",
        "",
        "## Archivos incrementales",
        "",
        "- `window_structures.parquet` se une a fase 1 por `window_id`. "
        "`structure_prediction_id` referencia `prediction_id` en `prediction_sources.tsv`.",
        "- `proteins.tsv` detalla las causas y el volumen por familia para cada proteína. "
        "`prediction_sources.tsv` conserva las filas originales, identificadores y versiones disponibles "
        "de los candidatos encontrados.",
        "- `metrics.json` conserva recuentos, métodos, firmas y tamaños. La procedencia admite "
        "varias filas de origen equivalentes por predicción.",
        "",
    ]
    sizes = data["artifact_bytes"]
    for name, size in sorted(sizes.items()):
        lines.append(f"- `{name}` ocupa {size:,} bytes.")
    sizes["metrics.json"] = (output / "metrics.json").stat().st_size
    lines.append(f"- `metrics.json` ocupa {sizes['metrics.json']:,} bytes.")
    body = "\n".join(lines) + "\n"
    size = 0
    while True:
        footer = f"- `report.md` ocupa {size:,} bytes. La salida completa ocupa {sum(sizes.values()) + size:,} bytes.\n"
        measured = len((body + footer).encode("utf-8"))
        if measured == size:
            break
        size = measured
    (output / "report.md").write_text(body + footer, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase1", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.phase1, args.output)
