"""Trace the sample's distinct representations to original embeddings and structural metadata."""

import argparse
from collections import defaultdict
import csv
from itertools import combinations
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from data_pipeline.scripts.check_sampled_modalities import load_source
from data_pipeline.scripts.global_epitope_labels.build import ROOT, row_path, write_json
from data_pipeline.scripts.source_audits.exact_embeddings import OriginalVectors, csv_stream


def distances(a, b):
    a, b = a.astype(np.float64), b.astype(np.float64)
    delta = a - b
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return {
        "exact": bool(np.array_equal(a, b)), "max_abs": float(np.max(np.abs(delta))),
        "euclidean": float(np.linalg.norm(delta)),
        "cosine": float(np.clip(np.dot(a, b) / denominator, -1, 1)) if denominator else None,
    }


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(dataset, sample, output):
    sources = json.loads((sample / "sources.json").read_text())
    config = json.loads((dataset / "config.json").read_text())
    family_sources = {s["mhc_family"]: s for s in config["sources"]}
    if any(output.resolve().is_relative_to(root.resolve()) for root in (dataset, sample)):
        raise ValueError("Use a separate output directory.")
    groups = defaultdict(list)
    for row in pq.read_table(sample / "proposed_provenance.parquet").to_pylist():
        groups[row["original_seq"]].append(row)
    cases = {seq: rows for seq, rows in groups.items() if len({
        (row["representative_source_dataset_id"], row["representative_source_row_index"]) for row in rows
    }) > 1}
    by_source = defaultdict(list)
    for rows in cases.values():
        for row in rows:
            by_source[row["source_dataset_id"]].append(row)
    output.mkdir(parents=True, exist_ok=False)
    models, observations, vectors = {}, [], {}
    for sid, rows in sorted(by_source.items()):
        source = sources[str(sid)]
        family = source["family"]
        store = Path(source["secondary"])
        model = json.loads(load_source(store / "embedding_config.json"))
        models[family] = {key: model[key] for key in (
            "model_fingerprint", "pooling", "dtype", "token_mapping", "batch_size", "world_size",
        )}
        wanted = {r["source_group_id"] for r in rows}
        structures = {}
        with csv_stream(store / "metadata.csv", prefix=True) as stream:
            for record in csv.DictReader(iter(lambda: stream.readline().decode("utf-8"), "")):
                group = int(record["group_id"])
                if group in wanted:
                    structures[group] = record
                    if structures.keys() == wanted:
                        break
        if structures.keys() != wanted:
            raise ValueError(f"Missing archived structural metadata: {family}.")
        original = {}
        for batch in pq.ParquetFile(row_path(dataset, family_sources[family])).iter_batches(
            batch_size=20_000, columns=[config["sequence_column"], "group_id", "protein_group_id", "protein_url",
                                         "window_start", "contains_epitope", "global_contains_epitope", "source_row_index"],
        ):
            for r in batch.to_pylist():
                group = int(r["group_id"])
                if group in wanted:
                    original[group] = r
            if original.keys() == wanted:
                break
        if original.keys() != wanted:
            raise ValueError(f"Missing global source observations: {family}.")
        reader = OriginalVectors(source)
        for row in sorted(rows, key=lambda r: (r["primary_chunk"], r["primary_row"])):
            group = row["source_group_id"]
            seq = row["original_seq"]
            context, structure = original[group], structures[group]
            expected = (seq, row["source_protein_group_id"], context["protein_url"],
                        int(context["window_start"]), context["contains_epitope"])
            archived = (structure["25aa_seq"], int(structure["protein_group_id"]), structure["protein_url"],
                        int(structure["window_start"]), int(structure["contains_epitope"]))
            clean = structure["clean_ss"]
            if (archived != expected or context[config["sequence_column"]] != seq
                    or row["source_row_index"] != context["source_row_index"]
                    or row["global_contains_epitope"] != context["global_contains_epitope"]
                    or len(clean) != 25 or set(clean) - {"C", "H", "E"} or structure["ss_status"] != "ok"):
                raise ValueError(f"Structural and original metadata disagree: {family}/{group}.")
            p, s = reader.vector_pair(row["primary_chunk"], row["primary_row"], group,
                                      row["source_protein_group_id"], context["contains_epitope"])
            key = sid, row["source_row_index"]
            vectors[key] = p.copy(), s.copy()
            observations.append(dict(row, family=family, protein_url=context["protein_url"],
                                     window_start=int(context["window_start"]), clean_ss=clean,
                                     secondary_model_fingerprint=model["model_fingerprint"]))
        del reader
    by_seq = defaultdict(list)
    for observation in observations:
        by_seq[observation["original_seq"]].append(observation)
    comparisons, summaries = [], []
    for seq, rows in sorted(by_seq.items()):
        all_pairs = []
        for a, b in combinations(rows, 2):
            ka = a["source_dataset_id"], a["source_row_index"]
            kb = b["source_dataset_id"], b["source_row_index"]
            primary, secondary = (distances(x, y) for x, y in zip(vectors[ka], vectors[kb]))
            same_rep = (a["representative_source_dataset_id"], a["representative_source_row_index"]) == (
                b["representative_source_dataset_id"], b["representative_source_row_index"]
            )
            if same_rep != (primary["exact"] and secondary["exact"]
                            and a["global_contains_epitope"] == b["global_contains_epitope"]):
                raise ValueError(f"Representation classes do not reproduce the sample: {seq}.")
            comparison = {
                "original_seq": seq, "family_a": a["family"], "group_a": a["source_group_id"],
                "family_b": b["family"], "group_b": b["source_group_id"],
                "clean_ss_a": a["clean_ss"], "clean_ss_b": b["clean_ss"],
                "structural_positions_different": sum(x != y for x, y in zip(a["clean_ss"], b["clean_ss"])),
                "same_model_fingerprint": a["secondary_model_fingerprint"] == b["secondary_model_fingerprint"],
            }
            comparison.update({f"{mode}_{key}": value for mode, measures in (
                ("primary", primary), ("secondary", secondary),
            ) for key, value in measures.items()})
            all_pairs.append(comparison)
        comparisons.extend(all_pairs)
        differing = [p for p in all_pairs if not p["secondary_exact"] or not p["primary_exact"]]
        summaries.append({
            "sequence": seq, "appearances": len(rows), "observations": rows,
            "primary_identical": all(p["primary_exact"] for p in all_pairs),
            "secondary_identical": all(p["secondary_exact"] for p in all_pairs),
            "different_pairs": len(differing),
            "differences_with_distinct_structure": sum(p["structural_positions_different"] > 0 for p in differing),
            "differences_with_same_structure": sum(p["structural_positions_different"] == 0 for p in differing),
            "all_models_match": all(p["same_model_fingerprint"] for p in all_pairs),
            "secondary_max_abs": max(p["secondary_max_abs"] for p in all_pairs),
            "secondary_euclidean_min": min(p["secondary_euclidean"] for p in differing),
            "secondary_euclidean_max": max(p["secondary_euclidean"] for p in differing),
            "secondary_cosine_min": min(p["secondary_cosine"] for p in differing),
            "secondary_cosine_max": max(p["secondary_cosine"] for p in differing),
        })
    write_csv(output / "observations.csv", observations)
    write_csv(output / "pairwise.csv", comparisons)
    write_json(output / "summary.json", {"cases": summaries, "secondary_processing": models})
    report = ["# Seis secuencias con representaciones diferentes", "",
              f"Se verificaron {len(observations)} apariciones y {len(comparisons)} pares en los bloques originales. "
              "Las métricas descriptivas se calcularon en float64 sobre los valores almacenados. "
              "La igualdad se comprobó sin tolerancia.", ""]
    for case in summaries:
        report.extend([f"## `{case['sequence']}`", "",
                       f"{case['appearances']} apariciones. ProtT5 idéntico: {case['primary_identical']}. "
                       f"SecondaryBERT idéntico: {case['secondary_identical']}.", "",
                       "| Familia | Grupo | Proteína | Inicio | Entrada C/H/E |", "|---|---:|---|---:|---|"])
        report.extend(f"| {r['family']} | {r['source_group_id']} | {r['protein_url']} | {r['window_start']} | "
                      f"`{r['clean_ss']}` |" for r in case["observations"])
        report.extend(["", f"SecondaryBERT, pares distintos: {case['different_pairs']}. "
                       f"Diferencia máxima absoluta {case['secondary_max_abs']:.8g}. "
                       f"Distancia euclídea {case['secondary_euclidean_min']:.8g}–{case['secondary_euclidean_max']:.8g}. "
                       f"Coseno {case['secondary_cosine_min']:.8g}–{case['secondary_cosine_max']:.8g}.",
                       f"Pares distintos con entrada estructural diferente: {case['differences_with_distinct_structure']}. "
                       f"Pares distintos con entrada estructural igual: {case['differences_with_same_structure']}. "
                       f"Fingerprint de modelo coincidente entre apariciones: {case['all_models_match']}.", ""])
    report.extend(["## Interpretación", "",
                   "Las cadenas C/H/E proceden del campo clean_ss archivado por SecondaryBERT, "
                   "cotejado con proteína, secuencia, posición y grupo originales. "
                   "Una diferencia de estas cadenas demuestra que cambió la entrada del modelo. "
                   "Los parámetros registrados se incluyen en el resumen. No se realizó una inferencia controlada "
                   "para aislar el efecto numérico del contexto frente a posibles diferencias de ejecución.",
                   "Las distancias son descriptivas. No intervienen en la definición de duplicado.", ""])
    (output / "report.md").write_text("\n".join(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/global_epitope_labels")
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.dataset, args.sample, args.output)


if __name__ == "__main__":
    main()
