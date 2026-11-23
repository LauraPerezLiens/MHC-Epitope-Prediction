"""Validate and describe the final logical NAP-CNB v2 selection."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import os

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .rebuild import signature

LABELS = pa.array([0, 1], type=pa.int8())
BASE_FIELDS = [
    "window_id", "parent_url", "parent_sha256", "window_start", "structure_status",
    "contains_epitope", "secondary_structure",
]


def read_index(path, fields):
    rows = {}
    for batch in pq.ParquetFile(path).iter_batches(columns=["window_id", *fields]):
        for row in batch.to_pylist():
            key = row.pop("window_id")
            if not key or key in rows:
                raise ValueError(f"Missing or duplicate window ID in {path}: {key!r}")
            rows[key] = row
    return rows


def checked_counts(phase, exclusions, overlay, summary):
    families = {}
    for family, expected in summary["validation"].items():
        positions = pq.ParquetFile(phase / "families" / f"{family}.parquet")
        counts = Counter()
        for batch in positions.iter_batches(columns=BASE_FIELDS):
            labels = batch["contains_epitope"]
            structure = batch["secondary_structure"]
            status = batch["structure_status"]
            if labels.null_count or status.null_count or not pc.all(pc.is_in(labels, value_set=LABELS)).as_py():
                raise ValueError(f"Invalid base label or structure status in {family}")
            missing = pc.is_null(structure)
            if pc.any(pc.not_equal(missing, pc.not_equal(status, "matched"))).as_py():
                raise ValueError(f"Base C/H/E presence contradicts its status in {family}")
            invalid_structure = pc.fill_null(pc.invert(pc.match_substring_regex(structure, "^[CHE]{25}$")), False)
            if pc.any(invalid_structure).as_py():
                raise ValueError(f"Invalid base C/H/E in {family}")
            counts["windows"] += batch.num_rows
            counts["positive_windows"] += pc.sum(labels).as_py()
            counts["matched"] += batch.num_rows - structure.null_count
            if not structure.null_count:
                continue
            for row in batch.filter(missing).to_pylist():
                key, start = row["window_id"], row["window_start"]
                if key != f"{family}|{row['parent_url']}|{start}":
                    raise ValueError(f"Invalid base window identity: {key}")
                excluded = exclusions.pop(key, None)
                recovered = overlay.pop(key, None)
                if (excluded is None) == (recovered is None):
                    raise ValueError(f"Unresolved or contradictory C/H/E source: {key}")
                if excluded is not None:
                    if (excluded["parent_sha256"], excluded["window_start"], row["structure_status"]) != (
                        row["parent_sha256"], start, "missing_prediction"
                    ):
                        raise ValueError(f"Exclusion disagrees with its base row: {key}")
                    counts["excluded"] += 1
                    counts["excluded_positive"] += row["contains_epitope"]
                else:
                    if (recovered["parent_sha256"], recovered["parent_url"], row["structure_status"]) != (
                        row["parent_sha256"], row["parent_url"], "unverified_archived_reference"
                    ):
                        raise ValueError(f"Recovered C/H/E disagrees with its base row: {key}")
                    counts["recovered"] += 1
        for field in ("windows", "positive_windows", "matched"):
            key = "structural_windows_matched" if field == "matched" else field
            if counts[field] != expected.get(key, 0):
                raise ValueError(f"Base counts changed in {family}/{key}")
        counts["excluded_negative"] = counts["excluded"] - counts["excluded_positive"]
        counts["positive_final"] = counts["positive_windows"] - counts["excluded_positive"]
        counts["negative_final"] = counts["windows"] - counts["excluded"] - counts["positive_final"]
        if counts["positive_final"] + counts["negative_final"] != counts["matched"] + counts["recovered"]:
            raise ValueError(f"Final coverage disagrees with final label counts in {family}")
        families[family] = dict(counts)
    if exclusions or overlay:
        raise ValueError("Supplementary IDs absent from the missing-structure rows of the base")
    return families


def run(results):
    phase = results / "nap_cnb_v2_phase1"
    recovery = results / "nap_cnb_v2_structure_recovery"
    completion = results / "nap_cnb_v2_structure_completion"
    output = results / "nap_cnb_v2_final_selection"
    if output.exists():
        raise FileExistsError(output)
    summary = json.loads((phase / "summary.json").read_text())
    metrics = json.loads((recovery / "metrics.json").read_text())
    if summary["status"] != "validated" or summary["scope"] != "full":
        raise ValueError("Validated full phase one required")
    signed = metrics["phase1_input_signatures"]
    if any(signature(Path(entry[0])) != entry for entry in signed):
        raise ValueError("A validated phase-one input changed")
    exclusion_path = completion / "pending_windows.parquet"
    overlay_path = recovery / "window_structures.parquet"
    watched = [Path(entry[0]) for entry in signed] + [exclusion_path, overlay_path]
    watched += [phase / folder / f"{family}.parquet" for family in summary["validation"]
                for folder in ("holdouts", "provenance", "evidence_verified")]
    before = [signature(path) for path in watched]
    exclusions = read_index(exclusion_path, ["parent_sha256", "window_start"])
    overlay = read_index(overlay_path, ["parent_sha256", "parent_url", "secondary_structure",
                                        "structure_prediction_id", "validation_status"])
    if len(exclusions) != metrics["remaining_windows"] or len(overlay) != metrics["window_counts"]["recovered"]:
        raise ValueError("Unexpected number of supplemental windows")
    if exclusions.keys() & overlay.keys():
        raise ValueError("Exclusion and recovery IDs overlap")
    for key, row in overlay.items():
        sequence = row["secondary_structure"]
        if (row["validation_status"] != "verified" or not row["structure_prediction_id"]
                or not sequence or len(sequence) != 25 or set(sequence) - set("CHE")):
            raise ValueError(f"Invalid recovered structure: {key}")
    families = checked_counts(phase, exclusions, overlay, summary)
    if before != [signature(path) for path in watched]:
        raise ValueError("An input changed during validation")
    totals = Counter()
    for counts in families.values():
        totals.update(counts)
    if (totals["windows"], totals["positive_windows"], totals["excluded"], totals["matched"] + totals["recovered"]) != (
        49_205_104, 5_594_529, 81_601, 49_123_503
    ):
        raise ValueError("Final totals disagree with validated release")
    def relative(path):
        return os.path.relpath(path, output)

    manifest = {
        "schema_version": 1,
        "base_families": {family: relative(phase / "families" / f"{family}.parquet") for family in families},
        "exclusions": relative(exclusion_path),
        "structure_overlay": relative(overlay_path),
        "provenance_directory": relative(phase / "provenance"),
        "verified_evidence_directory": relative(phase / "evidence_verified"),
        "global_label_index": relative(phase / "global_index.parquet"),
        "join_key": "window_id",
        "input_signatures": [{"path": relative(path), "bytes": entry[1], "mtime_ns": entry[2]}
                             for path, entry in zip(watched, before, strict=True)],
        "supplement_sha256": {relative(path): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in (exclusion_path, overlay_path)},
        "counts_by_family": families,
        "totals": dict(totals),
    }
    with TemporaryDirectory(dir=results, prefix=".final_selection_") as work:
        staged = Path(work) / output.name
        staged.mkdir()
        (staged / "selection.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        write_report(staged, summary, families, totals)
        staged.rename(output)


def number(value):
    return f"{value:,}".replace(",", ".")


def percent(numerator, denominator):
    return f"{100 * numerator / denominator:.3f}".replace(".", ",") + " %" if denominator else "—"


def write_report(output, summary, families, totals):
    n = number
    retained = totals["positive_final"] + totals["negative_final"]
    lines = [
        "# NAP-CNB v2 · selección definitiva",
        "",
        "La selección conserva únicamente las ventanas binarias con estructura secundaria verificada.",
        "",
        "| Métrica | Dataset binario original | Selección definitiva |",
        "|---|---:|---:|",
        f"| Ventanas | {n(totals['windows'])} | {n(retained)} |",
        f"| Positivas | {n(totals['positive_windows'])} | {n(totals['positive_final'])} |",
        f"| Negativas operativas | {n(totals['windows'] - totals['positive_windows'])} | {n(totals['negative_final'])} |",
        f"| Sin estructura verificada | {n(totals['excluded'])} | 0 |",
        f"| Cobertura estructural | {percent(retained, totals['windows'])} | 100 % |",
        f"| Prevalencia de positivos | {percent(totals['positive_windows'], totals['windows'])} | {percent(totals['positive_final'], retained)} |",
        "",
        "El 100 % corresponde al subconjunto seleccionado. El conjunto binario original conserva las ventanas pendientes.",
        "",
        f"Se excluyeron **{n(totals['excluded_positive'])} positivas** y **{n(totals['excluded_negative'])} negativas operativas**.",
        "",
        "| Familia | Ventanas originales | Pos. antes | Neg. antes | Excluidas | Pos. excl. | Neg. excl. | % ventanas excl. | % positivos excl. | Pos. después | Neg. después | Prevalencia antes → después |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for family, c in families.items():
        w, p, exc, p_exc = (c.get(key, 0) for key in ("windows", "positive_windows", "excluded", "excluded_positive"))
        line = [family, n(w), n(p), n(w-p), n(exc), n(p_exc), n(exc-p_exc), percent(exc,w), percent(p_exc,p),
                n(c["positive_final"]), n(c["negative_final"]),
                f"{percent(p,w)} → {percent(c['positive_final'],w-exc)}"]
        lines.append("| " + " | ".join(line) + " |")
    eligible = (family for family, counts in families.items() if counts["positive_windows"] > 0)
    ranked = sorted(eligible, key=lambda f: families[f].get("excluded_positive", 0) / families[f]["positive_windows"],
                    reverse=True)
    lines += ["", "Las mayores pérdidas relativas de positivos fueron las de estas tres familias.", ""]
    for family in ranked[:3]:
        c = families[family]
        lines.append(f"- **{family}** perdió {n(c.get('excluded_positive', 0))} de {n(c['positive_windows'])} "
                     f"positivos ({percent(c.get('excluded_positive', 0), c['positive_windows'])}).")
    holdouts = sum(c.get("held_out_windows", 0) for c in summary["validation"].values())
    lines += [
        "",
        "## Integridad y procedencia",
        "",
        f"- Se verificaron etiquetas binarias y longitud y alfabeto de todo el C/H/E base. "
        f"El recuento conservado comprende {n(totals['matched'])} estructuras de fase 1 y "
        f"{n(totals['recovered'])} recuperaciones previas.",
        "- Cada ventana sin C/H/E base se encontró una sola vez entre las recuperaciones o las exclusiones. "
        "Se cotejaron los hashes de proteína y las coordenadas o la URL, según el índice.",
        f"- Se conservaron las firmas de los archivos base previamente reconciliados. La selección solo filtra "
        f"ventanas binarias existentes y mantiene fuera los {n(holdouts)} holdouts. Las etiquetas, secuencias, "
        "coordenadas y familias se leen de la base. El criterio de exclusión es la falta de C/H/E verificada.",
        "- Las comprobaciones previas de secuencia completa, coordenadas y evidencias siguen ligadas a la base y "
        "a la recuperación por `window_id`. El manifiesto incluye las firmas y los hashes de los dos suplementos.",
        "",
        "## Cómo consultar la selección",
        "",
        "Desde este directorio, DuckDB puede consultar la selección con esta vista. Las rutas, familias y "
        "fuentes se detallan en [selection.json](selection.json).",
        "",
        "```sql",
        "CREATE VIEW nap_cnb_v2_final AS",
        "SELECT b.* EXCLUDE (secondary_structure, structure_prediction_id, structure_status),",
        "       coalesce(b.secondary_structure, r.secondary_structure) AS secondary_structure,",
        "       coalesce(b.structure_prediction_id, r.structure_prediction_id) AS structure_prediction_id,",
        "       CASE WHEN r.window_id IS NULL THEN 'phase1' ELSE 'archived_recovery' END AS structure_source",
        "FROM read_parquet([",
        ",\n".join(f"  '../nap_cnb_v2_phase1/families/{family}.parquet'" for family in families),
        "]) AS b",
        "LEFT JOIN read_parquet('../nap_cnb_v2_structure_recovery/window_structures.parquet') AS r",
        "  ON b.window_id = r.window_id",
        "WHERE NOT EXISTS (",
        "  SELECT 1 FROM read_parquet('../nap_cnb_v2_structure_completion/pending_windows.parquet') AS e",
        "  WHERE e.window_id = b.window_id",
        ");",
        "```",
        "",
        "La etiqueta familiar es `contains_epitope`. El índice global conserva "
        "la etiqueta v2 del conjunto binario original por secuencia exacta. Las referencias a ensayos y epítopos se consultan por "
        "`window_id` en `provenance/` y por ID de evento en `evidence_verified/` de la familia correspondiente.",
        "",
        "## Espacio adicional",
        "",
        f"- `selection.json` ocupa {n((output / 'selection.json').stat().st_size)} bytes.",
        "- `final_selection_report.md` documenta la selección y su consulta.",
    ]
    (output / "final_selection_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("results"))
    run(parser.parse_args().results.resolve())
