"""Read the published metadata for NAP-CNB v2, without running the pipeline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

PIPELINE = "NAP-CNB v2"
ROOT = Path(__file__).resolve().parents[1]
SELECTION = Path("results/nap_cnb_v2_final_selection/selection.json")
VIEWS = Path("results/nap_cnb_v2_dataset_views")
D1 = VIEWS / "d1_manifest.json"
SPLITS = VIEWS / "splits/validation.json"
ASSIGNMENTS = VIEWS / "splits/assignments.parquet"
PRIMARY = Path("results/nap_cnb_v2_prott5/final")
SECONDARY = Path("results/nap_cnb_v2_secondarybert")
METADATA_LIMIT = 256 * 1024
SPLIT_NAMES = ("train", "validation", "test")


class UnknownMetadata(Exception):
    """The bounded read cannot establish the requested metadata."""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def count(value):
    require(type(value) is int and value >= 0, f"Invalid count: {value!r}")
    return value


def split_counts(data):
    require(set(data) == set(SPLIT_NAMES), "Invalid split names")
    result = {}
    for name in SPLIT_NAMES:
        row = data[name]
        values = {key: count(row[key]) for key in ("rows", "positive", "negative")}
        require(values["positive"] + values["negative"] == values["rows"], f"Invalid counts for {name}")
        result[name] = values
    return result


class Component:
    def __init__(self, root, source):
        self.root = root
        self.data = {
            "status": "UNKNOWN",
            "records": None,
            "source": str(source) if source else None,
            "evidence": [],
            "checked_now": [],
            "not_checked": ["full_data_integrity", "large_file_hashes"],
            "details": {},
            "errors": [],
        }

    def present(self, path, directory=False):
        info = (self.root / path).stat()
        test = stat.S_ISDIR if directory else stat.S_ISREG
        require(test(info.st_mode), f"Unexpected file type: {path}")
        check = "directories_present" if directory else "files_present"
        if check not in self.data["checked_now"]:
            self.data["checked_now"].append(check)
        return info

    def read(self, path, optional=False):
        try:
            self.present(path)
        except FileNotFoundError:
            if optional:
                return None
            raise
        with (self.root / path).open("rb") as stream:
            data = stream.read(METADATA_LIMIT + 1)
        if len(data) > METADATA_LIMIT:
            raise UnknownMetadata(f"Metadata exceeds {METADATA_LIMIT} bytes: {path}")
        if "metadata_read" not in self.data["checked_now"]:
            self.data["checked_now"].append("metadata_read")
        return data

    def load(self, path):
        data = json.loads(self.read(path))
        require(isinstance(data, dict), f"Expected JSON object: {path}")
        return data

    def evidence(self, path):
        self.data["evidence"].append(str(path))

    def selection_hash(self, expected):
        data = self.read(SELECTION)
        require(hashlib.sha256(data).hexdigest() == expected, "Selection SHA-256 does not match the recorded release")
        self.data["checked_now"].append("selection_manifest_sha256")

    def record_counts(self, records, positive=None, negative=None):
        self.data["records"] = count(records)
        if positive is not None:
            positive, negative = count(positive), count(negative)
            require(positive + negative == records, "Label counts do not sum to the total")
            self.data["details"].update(positive=positive, operational_negative=negative)


def selection(component):
    data = component.load(SELECTION)
    totals = data["totals"]
    require(count(data["schema_version"]) == 1 and data["join_key"] == "window_id", "Unsupported selection schema")
    retained = count(totals["windows"]) - count(totals["excluded"])
    component.record_counts(retained, totals["positive_final"], totals["negative_final"])
    require(retained == count(totals["matched"]) + count(totals["recovered"]), "Structural totals disagree")
    component.data["details"]["schema_version"] = data["schema_version"]
    component.data["details"]["excluded"] = totals["excluded"]
    families = data["base_families"]
    require(isinstance(families, dict) and families, "Empty or invalid family map")
    for path in (*families.values(), data["global_label_index"], data["structure_overlay"], data["exclusions"]):
        component.present(SELECTION.parent / path)
    for key in ("provenance_directory", "verified_evidence_directory"):
        component.present(SELECTION.parent / data[key], directory=True)
    signatures = data.get("input_signatures")
    for signature in signatures or ():
        path = SELECTION.parent / signature["path"]
        info = component.present(path)
        require((info.st_size, info.st_mtime_ns) == (signature["bytes"], signature["mtime_ns"]),
                f"Selection metadata signature differs: {path}")
    if signatures:
        component.data["checked_now"].append("selection_input_sizes_and_mtimes")
    report = SELECTION.parent / "final_selection_report.md"
    text = component.read(report, optional=True)
    if signatures and text and b"## Integridad y procedencia" in text:
        component.evidence(report)


def structures(component):
    data = component.load(SELECTION)
    totals = data["totals"]
    component.record_counts(count(totals["matched"]) + count(totals["recovered"]))
    require(component.data["records"] == count(totals["windows"]) - count(totals["excluded"]),
            "Structural coverage and selection counts disagree")
    overlay = SELECTION.parent / data["structure_overlay"]
    exclusions = SELECTION.parent / data["exclusions"]
    component.data["details"].update(overlay=str(overlay), exclusions=str(exclusions),
                                     recovered=totals["recovered"], excluded=totals["excluded"])
    for path in (overlay, exclusions):
        component.present(path)
        require(data["supplement_sha256"].get(str(path.relative_to(SELECTION.parent))) is not None,
                f"No recorded supplement signature for {path}")
    reports = (overlay.parent / "report.md", exclusions.parent / "completion_report.md",
               SELECTION.parent / "final_selection_report.md")
    texts = [component.read(path, optional=True) for path in reports]
    if all(texts) and b"Base validada" in texts[0] and b"## Integridad y procedencia" in texts[2]:
        for report in reports:
            component.evidence(report)


def report_count(text, pattern):
    if text is not None:
        match = re.search(pattern, text.decode("utf-8"))
        if match:
            return int(match.group(1).replace(".", "").replace(",", ""))
    return None


def prott5(component):
    manifest = component.load(PRIMARY / "manifest.json")
    require(manifest["sample_ordinals"] is None, "ProtT5 manifest describes a sample, not the full store")
    component.selection_hash(manifest["selection_sha256"])
    component.present(Path(manifest["inventory"]))
    component.present(PRIMARY / "progress.sqlite")
    details = component.data["details"]
    details.update(dimension=count(manifest["dimension"]), revision=manifest["revision"],
                   inventory=manifest["inventory"], inventory_sha256=manifest["inventory_sha256"])
    require(details["dimension"] > 0 and count(manifest["shard_rows"]) > 0, "Invalid ProtT5 dimensions or shard capacity")
    shards = sorted((component.root / PRIMARY).glob("shard-*.npy"))
    if not shards:
        raise FileNotFoundError(str(PRIMARY / "shard-*.npy"))
    for index, shard in enumerate(shards):
        expected = PRIMARY / f"shard-{index:04d}.npy"
        component.present(expected)
        require(shard.name == expected.name, f"Unexpected shard: {shard.name}")
    details["shards"] = len(shards)
    report = PRIMARY.parent / "final_report.md"
    text = component.read(report, optional=True)
    records = report_count(text, r"Se confirmaron \*\*([\d,.]+) embeddings")
    declared = report_count(text, r"\| Shards \| ([\d,.]+) \|")
    if records is not None:
        component.record_counts(records)
        capacity = manifest["shard_rows"]
        require((records + capacity - 1) // capacity == len(shards), "ProtT5 record count and shard count disagree")
    if declared is not None:
        require(declared == len(shards), "ProtT5 report and shard count disagree")
    if records is not None and declared is not None and b"**Estado validado.**" in text:
        component.evidence(report)
    component.data["not_checked"].append("sqlite_batch_contents")


def secondarybert(component):
    component.present(SECONDARY / "index.sqlite")
    pilot = component.load(SECONDARY / "pilot.json")
    rows, dimension = pilot["shape"]
    require(count(rows) == count(pilot["n"]) and count(dimension) > 0, "SecondaryBERT pilot shape disagrees")
    component.data["details"].update(dimension=dimension, dtype=pilot["dtype"],
                                     model_fingerprint=pilot["config"]["fingerprint"])
    report = SECONDARY / "secondarybert_report.md"
    text = component.read(report, optional=True)
    records = report_count(text, r"\*\*([\d,.]+) estructuras C/H/E exactas\*\*")
    if records is not None:
        component.record_counts(records)
        require(records >= rows, "SecondaryBERT final coverage is smaller than its pilot")
    if records is not None and "Fase 3C cerrada y validada".encode() in text and pilot["finite"] is True:
        component.evidence(report)
    component.data["not_checked"] += ["sqlite_contents", "historical_secondarybert_block_references"]


def datasets(component, kind, filename):
    source = VIEWS / "metrics.json"
    artifact = VIEWS / filename
    info = component.present(artifact)
    metrics = component.load(source)
    component.selection_hash(metrics["selection_sha256"])
    if kind == "base":
        families = metrics["families"]
        require(isinstance(families, dict) and families, "Invalid family metrics")
        records = sum(count(f["base"]) for f in families.values())
        positives = sum(count(f["base_positive"]) for f in families.values())
        for name in ("window_provenance.parquet", "legacy_group_links.parquet"):
            component.present(VIEWS / name)
    else:
        names = ("global_sequences", "global_positive") if kind == "labels" else (
            "global_representations", "global_positive_representations")
        records, positives = (count(metrics[name]) for name in names)
    component.record_counts(records, positives, records - positives)
    declared = metrics.get("files_bytes", {}).get(filename)
    if declared is not None:
        require(info.st_size == count(declared), f"File size differs from the certified metrics: {artifact}")
        component.data["checked_now"].append("file_size_matches_metrics")
        if "reopen_validation_seconds" in metrics:
            component.evidence(source)
    component.data["details"]["artifact"] = str(artifact)


def splits(component):
    data = component.load(SPLITS)
    size = component.present(ASSIGNMENTS).st_size
    component.selection_hash(data["selection_sha256"])
    groups = data["effective_groups_by_split"]
    require(set(groups) == set(SPLIT_NAMES), "Invalid group split names")
    component.record_counts(data["effective_groups"])
    require(sum(count(v) for v in groups.values()) == component.data["records"], "Split group counts disagree")
    require(size == count(data["assignment_bytes"]), "Split file size differs from the validation report")
    component.data["details"].update(seed=count(data["seed"]), version=data["version"],
                                     assignment_sha256=data["assignment_sha256"], groups_by_split=groups,
                                     global_by_split=split_counts(data["global"]), artifact=str(ASSIGNMENTS))
    component.data["checked_now"].append("assignment_size_and_metadata_counts")
    if data.get("assignment_sha256") and data.get("verified_cross_primary_historical_edges") == 0:
        component.evidence(SPLITS)


def d1(component):
    data = component.load(D1)
    require(count(data["schema_version"]) == 1 and data["id"] == "D1" and data["path_base"] == "repository_root",
            "Unsupported D1 manifest")
    dataset, split, embeds = data["dataset"], data["splits"], data["embeddings"]
    require(dataset["key"] == ["sequence", "secondary_structure"] and dataset["label"] == "label_global"
            and dataset["augmentation"] == "none", "Unexpected D1 dataset contract")
    require(split["join"] == {"sequence": "effective_group_id"} and split["field"] == "split_id",
            "Unexpected D1 split join")
    for name, key in (("ProtT5", "sequence"), ("SecondaryBERT", "secondary_structure")):
        require(embeds[name]["key"] == key and embeds[name]["dtype"] == "float32",
                f"Unexpected D1 embedding contract: {name}")
    primary, secondary = embeds["ProtT5"], embeds["SecondaryBERT"]
    inputs = data["inputs_sha256"]
    references = (dataset["path"], split["path"], split["validation"], primary["inventory"],
                  primary["manifest"], primary["progress"], secondary["index"], secondary["evidence"])
    require(all(path in inputs for path in references), "D1 reference is absent from inputs_sha256")
    for path in inputs:
        component.present(Path(path))
    split_report = component.load(Path(split["validation"]))
    primary_manifest = component.load(Path(primary["manifest"]))
    secondary_pilot = component.load(Path(secondary["index"]).with_name("pilot.json"))
    require(primary["dimension"] == primary_manifest["dimension"] and
            secondary["dimension"] == secondary_pilot["shape"][1], "D1 embedding dimensions disagree")
    for path in (str(SELECTION), split["validation"], primary["manifest"], secondary["evidence"]):
        require(hashlib.sha256(component.read(Path(path))).hexdigest() == inputs[path],
                f"D1 metadata signature differs: {path}")
    require(inputs[split["path"]] == split_report["assignment_sha256"] and split["seed"] == split_report["seed"]
            and split["version"] == split_report["version"] and split["codes"] == split_report["split_ids"]
            and inputs[dataset["path"]] == split_report["catalog_sha256"]["global_dataset"]
            and inputs[primary["inventory"]] == primary_manifest["inventory_sha256"],
            "D1 references disagree with the split or ProtT5 manifests")
    by_split = split_counts(data["by_split"])
    component.record_counts(data["observations"], sum(row["positive"] for row in by_split.values()),
                            sum(row["negative"] for row in by_split.values()))
    require(by_split == split_counts(split_report["global"]), "D1 and split report counts disagree")
    validation = data["validation"]
    require(count(validation["unique_representations"]) == component.data["records"]
            and count(validation["unique_primary_keys"]) == split_report["effective_groups"],
            "D1 validation counters disagree")
    pattern = Path(primary["shards"])
    require(pattern.name == "shard-*.npy", "Unexpected D1 shard pattern")
    shards = sorted((component.root / pattern.parent).glob(pattern.name))
    expected_shards = count(validation["confirmed_prott5_shards"])
    if len(shards) < expected_shards:
        raise FileNotFoundError(f"Missing D1 shards in {pattern.parent}")
    require(len(shards) == expected_shards, "D1 shard count disagrees")
    for index in range(expected_shards):
        component.present(pattern.parent / f"shard-{index:04d}.npy")
    component.data["details"].update(by_split=by_split, seed=split["seed"], schema_version=data["schema_version"],
                                     dataset=dataset["path"], assignments=split["path"])
    component.data["checked_now"].append("small_metadata_sha256_and_manifest_cross_checks")
    component.data["not_checked"].append("historical_secondarybert_block_references")
    if data.get("status") == "validated" and validation.get("reproduced_all_split_assignments") is True:
        component.evidence(D1)


def assess(root, source, inspect):
    component = Component(root, source)
    try:
        inspect(component)
    except FileNotFoundError as error:
        status, message = "MISSING", str(error)
    except (ValueError, TypeError, IndexError, AttributeError) as error:
        status, message = "INCONSISTENT", str(error)
    except (OSError, KeyError, UnknownMetadata) as error:
        status, message = "UNKNOWN", str(error)
    else:
        status = "CERTIFIED" if component.data["evidence"] else "PRESENT"
        message = None
    component.data["status"] = status
    if message:
        component.data["errors"].append({"code": status.lower(), "message": message})
    return component.data


def status(root):
    components = {
        "selection": assess(root, SELECTION, selection),
        "secondary_structures": assess(root, SELECTION, structures),
        "prott5": assess(root, PRIMARY / "manifest.json", prott5),
        "secondarybert": assess(root, SECONDARY / "index.sqlite", secondarybert),
        "base_dataset": assess(root, VIEWS / "metrics.json",
                               lambda c: datasets(c, "base", "base_dataset.parquet")),
        "global_labels": assess(root, VIEWS / "metrics.json",
                                lambda c: datasets(c, "labels", "global_labels.parquet")),
        "global_dataset": assess(root, VIEWS / "metrics.json",
                                 lambda c: datasets(c, "global", "global_dataset.parquet")),
        "splits": assess(root, SPLITS, splits),
        "d1": assess(root, D1, d1),
    }
    components["d2"] = {
        "status": "NOT AVAILABLE", "records": None, "source": None, "evidence": [],
        "checked_now": [], "not_checked": ["outside_current_release"],
        "details": {"reason": "D2 is outside the current D1 release"}, "errors": [],
    }
    return components


def render(report):
    print(f"{PIPELINE} — Pipeline Status")
    print(f"Repository: {report['root']}")
    print(f"Mode: {report['mode']}\n")
    print(f"{'Component':22} {'Status':15} {'Records':>12}  Details")
    print("-" * 78)
    names = ("Final selection", "Secondary structures", "ProtT5", "SecondaryBERT", "Base dataset",
             "Global labels", "Global dataset", "Splits", "D1 manifest", "D2")
    for name, item in zip(names, report["components"].values()):
        records = f"{item['records']:,}" if item["records"] is not None else "-"
        details = item["details"]
        parts = []
        if "positive" in details:
            parts.append(f"+ {details['positive']:,} / − {details['operational_negative']:,}")
        if "dimension" in details:
            parts.append(f"{details['dimension']} dimensions")
        if "shards" in details:
            parts.append(f"{details['shards']} shards")
        if "seed" in details:
            parts.append(f"seed {details['seed']}")
        counts = details.get("by_split", details.get("global_by_split"))
        if counts:
            parts.append(" / ".join(f"{key} {counts[key]['rows']:,}" for key in SPLIT_NAMES))
        print(f"{name:22} {item['status']:15} {records:>12}  {'; '.join(parts)}")
        for error in item["errors"]:
            print(f"  {error['message']}")
    print("\nAssessment: metadata and prior certification evidence only.")
    print("No exhaustive integrity checks performed.")
    for error in report["errors"]:
        print(error["message"], file=sys.stderr)


METRICS = VIEWS / "metrics.json"
FOOTER_LIMIT = 1024 * 1024
DATASET_SCHEMAS = {
    "base_dataset.parquet": (
        "family parent_url parent_accession parent_version parent_sha256 sequence secondary_structure "
        "organism mhc_class base_id", {"label_original": "int8", "observation_count": "int64"}),
    "global_labels.parquet": (
        "sequence", {"label_global": "int8", "min_original_label": "int8", "representations": "int64",
                     "base_observations": "int64", "original_observations": "int64"}),
    "global_dataset.parquet": (
        "sequence secondary_structure", {"label_global": "int8", "base_observations": "int64",
                                         "original_observations": "int64"}),
    "window_provenance.parquet": ("window_id base_id", {}),
    "legacy_group_links.parquet": (
        "window_id legacy_source_file group_id", {"legacy_row_index": "int64", "legacy_label": "int8"}),
}


def check_digest(value):
    require(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value), "Invalid recorded SHA-256")


def validation_check(root, name, source, inspect):
    result = {"name": name, "source": str(source)}
    try:
        details = inspect(Component(root, source))
    except FileNotFoundError as error:
        result.update(result="FAIL", error={"code": "missing_reference", "message": str(error)})
    except KeyError as error:
        result.update(result="INCOMPLETE", error={"code": "missing_metadata", "message": str(error)})
    except (OSError, UnknownMetadata) as error:
        result.update(result="INCOMPLETE", error={"code": "unavailable_metadata", "message": str(error)})
    except (ValueError, TypeError, AttributeError, IndexError, OverflowError) as error:
        result.update(result="FAIL", error={"code": "inconsistent_metadata", "message": str(error)})
    else:
        result.update(result="PASS", details=details)
    return result


def selection_contract(component):
    selection(component)
    data = component.load(SELECTION)
    families = data["counts_by_family"]
    require(families.keys() == data["base_families"].keys(), "Selection family maps disagree")
    totals = data["totals"]
    sparse_fields = {"recovered", "excluded", "excluded_positive"}
    # The selection writer serializes per-family Counters, omitting unused increments.
    normalized = {
        name: {**dict.fromkeys(sparse_fields, 0), **values} for name, values in families.items()
    }
    fields = ("windows", "positive_windows", "matched", "recovered", "excluded", "excluded_positive",
              "excluded_negative", "positive_final", "negative_final")
    for label, values in (*normalized.items(), ("total", totals)):
        for field in fields:
            count(values[field])
        require(values["excluded"] == values["excluded_positive"] + values["excluded_negative"]
                and values["positive_windows"] == values["positive_final"] + values["excluded_positive"]
                and values["windows"] == values["matched"] + values["recovered"] + values["excluded"]
                and values["windows"] == values["positive_final"] + values["negative_final"] + values["excluded"],
                f"Selection arithmetic disagrees: {label}")
    require(all(sum(row[k] for row in normalized.values()) == totals[k] for k in fields),
            "Family counts do not sum to the selection totals")
    require(bool(data["input_signatures"]), "Selection input signatures are empty")
    paths = {data["structure_overlay"], data["exclusions"]}
    signatures = data["supplement_sha256"]
    resolved = {(component.root / SELECTION.parent / path).resolve() for path in paths}
    require(len(resolved) == 2 and signatures.keys() == paths, "Overlay and exclusion references disagree")
    family_paths = {(component.root / SELECTION.parent / path).resolve() for path in data["base_families"].values()}
    require(len(family_paths) == len(families) and not resolved & family_paths, "Selection artifacts overlap")
    for value in signatures.values():
        check_digest(value)
    checked, deferred = [], []
    for path, expected in signatures.items():
        reference = SELECTION.parent / path
        if component.present(reference).st_size > METADATA_LIMIT:
            deferred.append(str(reference))
        else:
            require(hashlib.sha256(component.read(reference)).hexdigest() == expected,
                    f"Supplement hash differs: {path}")
            checked.append(str(reference))
    return {"schema_version": data["schema_version"], "declared_counts": component.data["details"],
            "declared_rows": component.data["records"], "signed_inputs_stat_checked": len(data["input_signatures"]),
            "supplement_hashes_checked": checked, "supplement_hashes_deferred": deferred}


def read_footer(component, path):
    import struct

    info = component.present(path)
    if info.st_size < 12:
        raise ValueError(f"Truncated Parquet file: {path}")
    with (component.root / path).open("rb") as stream:
        require(stream.read(4) == b"PAR1", f"Invalid Parquet header: {path}")
        stream.seek(-8, 2)
        trailer = stream.read(8)
        require(len(trailer) == 8 and trailer[4:] == b"PAR1", f"Invalid Parquet trailer: {path}")
        length = struct.unpack("<I", trailer[:4])[0]
        require(0 < length <= info.st_size - 12, f"Invalid Parquet footer size: {path}")
        if length > FOOTER_LIMIT:
            raise UnknownMetadata(f"Parquet footer exceeds {FOOTER_LIMIT} bytes: {path}")
        stream.seek(-8 - length, 2)
        footer = stream.read(length)
        require(len(footer) == length, f"Truncated Parquet footer: {path}")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise UnknownMetadata("PyArrow is unavailable for required Parquet footer checks") from error
    try:
        # Give PyArrow only the footer bytes, never a handle to the original data.
        metadata = pq.read_metadata(pa.BufferReader(b"PAR1" + footer + trailer))
        schema = metadata.schema.to_arrow_schema()
    except (pa.ArrowException, OSError) as error:
        raise ValueError(f"Invalid Parquet footer: {path}: {error}") from error
    columns = {field.name: str(field.type) for field in schema}
    require(len(columns) == len(schema), f"Duplicate Parquet column names: {path}")
    return info.st_size, metadata.num_rows, columns


def footer_contract(component, path, schema, declared_rows, declared_size):
    size, rows, columns = read_footer(component, path)
    require(rows == count(declared_rows), f"Footer rows ({rows}) differ from declared rows ({declared_rows}): {path}")
    require(size == count(declared_size), f"File size differs from published metadata: {path}")
    strings, types = schema
    expected = {**dict.fromkeys(strings.split(), "string"), **types}
    require(columns == expected, f"Incompatible Parquet schema: {path}")
    return {"declared_rows": declared_rows, "footer_rows": rows, "columns": columns}


def dataset_metadata(component, metrics, selection_data):
    component.selection_hash(metrics["selection_sha256"])
    families = metrics["families"]
    originals = selection_data["counts_by_family"]
    require(families.keys() == originals.keys() and bool(families), "Dataset families differ from selection")
    for name, family in families.items():
        original, base, removed, original_positive, base_positive = (
            count(family[key]) for key in ("original", "base", "removed", "original_positive", "base_positive"))
        positive = count(originals[name]["positive_final"])
        negative = count(originals[name]["negative_final"])
        require(original == positive + negative and original_positive == positive and base + removed == original
                and base_positive <= min(positive, base) and base - base_positive <= negative,
                f"Dataset counts disagree for {name}")
    labels, representations = count(metrics["global_sequences"]), count(metrics["global_representations"])
    positive_labels = count(metrics["global_positive"])
    positive_reps = count(metrics["global_positive_representations"])
    base = sum(f["base"] for f in families.values())
    require(positive_labels <= positive_reps <= representations <= base and positive_labels <= labels <= representations
            and labels - positive_labels <= representations - positive_reps,
            "Base, global label and representation counts disagree")
    return {
        "base_dataset.parquet": base,
        "global_labels.parquet": labels,
        "global_dataset.parquet": representations,
        "window_provenance.parquet": sum(f["original"] for f in families.values()),
        "legacy_group_links.parquet": sum(count(f["legacy_links"]) for f in families.values()),
    }


def dataset_contract(component, filename=None):
    metrics = component.load(METRICS)
    counts = dataset_metadata(component, metrics, component.load(SELECTION))
    if filename is None:
        return {"declared_rows_by_artifact": counts}
    return footer_contract(component, VIEWS / filename, DATASET_SCHEMAS[filename],
                           counts[filename], metrics["files_bytes"][filename])


def split_contract(component):
    splits(component)
    data = component.load(SPLITS)
    metrics = component.load(METRICS)
    component.selection_hash(metrics["selection_sha256"])
    require(data["seed"] == 42 and data["version"] == "primary-blake2b-mod10-v1",
            "Split seed or algorithm is incompatible with this release")
    require(data["split_ids"] == dict(zip(("0", "1", "2"), SPLIT_NAMES)), "Invalid split ID mapping")
    require(data["verified_cross_primary_historical_edges"] == 0, "Historical independence evidence disagrees")
    check_digest(data["assignment_sha256"])
    for key in ("base_dataset", "global_dataset", "global_labels"):
        check_digest(data["catalog_sha256"][key])
        name = f"{key}.parquet"
        require(component.present(VIEWS / name).st_size == count(metrics["files_bytes"][name]),
                f"Split companion catalog size differs: {name}")
    global_rows = split_counts(data["global"])
    base_rows = split_counts(data["base"])
    require(sum(row["rows"] for row in global_rows.values()) == count(metrics["global_representations"])
            and sum(row["positive"] for row in global_rows.values()) == count(metrics["global_positive_representations"])
            and sum(row["rows"] for row in base_rows.values()) == sum(count(f["base"]) for f in metrics["families"].values())
            and sum(row["positive"] for row in base_rows.values()) ==
            sum(count(f["base_positive"]) for f in metrics["families"].values())
            and data["effective_groups"] == metrics["global_sequences"],
            "Split totals disagree with the dataset metrics")
    footer = footer_contract(component, ASSIGNMENTS, ("effective_group_id", {"split_id": "uint8"}),
                             data["effective_groups"], data["assignment_bytes"])
    return {**footer, "seed": data["seed"], "version": data["version"], "global_by_split": global_rows,
            "groups_by_split": data["effective_groups_by_split"], "prior_independence_evidence": str(SPLITS)}


def d1_contract(component):
    d1(component)
    data = component.load(D1)
    primary, secondary = data["embeddings"]["ProtT5"], data["embeddings"]["SecondaryBERT"]
    references = {
        data["dataset"]["path"]: VIEWS / "global_dataset.parquet",
        data["splits"]["path"]: ASSIGNMENTS,
        data["splits"]["validation"]: SPLITS,
        primary["manifest"]: PRIMARY / "manifest.json",
        primary["progress"]: PRIMARY / "progress.sqlite",
        primary["shards"]: PRIMARY / "shard-*.npy",
        secondary["index"]: SECONDARY / "index.sqlite",
        secondary["evidence"]: SECONDARY / "secondarybert_report.md",
    }
    require(len(references) == 8 and all((component.root / path).resolve() == (component.root / expected).resolve()
                                        for path, expected in references.items()),
            "D1 artifact references differ from the current release")
    require(primary["dimension"] == 1024 and secondary["dimension"] == 768, "Unsupported D1 feature dimensions")
    require(data["status"] == "validated" and data["validation"]["reproduced_all_split_assignments"] is True,
            "D1 prior validation evidence is missing or inconsistent")
    for value in data["inputs_sha256"].values():
        check_digest(value)
    split_data = component.load(SPLITS)
    labels = VIEWS / "global_labels.parquet"
    component.present(labels)
    require(data["splits"]["seed"] == 42 and data["splits"]["version"] == "primary-blake2b-mod10-v1",
            "D1 split seed or algorithm is incompatible with this release")
    require(data["inputs_sha256"][str(labels)] == split_data["catalog_sha256"]["global_labels"],
            "D1 global label catalog signature disagrees")
    primary_manifest = component.load(PRIMARY / "manifest.json")
    require(primary_manifest["sample_ordinals"] is None and
            primary_manifest["selection_sha256"] == data["inputs_sha256"][str(SELECTION)],
            "D1 ProtT5 manifest is not the full store for this selection")
    require((component.root / primary["inventory"]).resolve() ==
            (component.root / primary_manifest["inventory"]).resolve(), "D1 ProtT5 inventory paths disagree")
    evidence = component.read(Path(secondary["evidence"]))
    secondary_count = report_count(evidence, r"\*\*([\d,.]+) estructuras C/H/E exactas\*\*")
    if secondary_count is None:
        raise UnknownMetadata("SecondaryBERT final key count is unavailable")
    require(secondary_count == count(data["validation"]["unique_secondary_keys"]),
            "D1 and SecondaryBERT key counts disagree")
    return {"declared_rows": data["observations"], "by_split": data["by_split"],
            "declared_secondary_keys": secondary_count,
            "dimensions": {"ProtT5": primary["dimension"], "SecondaryBERT": secondary["dimension"],
                           "combined": primary["dimension"] + secondary["dimension"]},
            "label": data["dataset"]["label"], "recorded_seed": data["splits"]["seed"]}


def read_npy_header(component, path):
    import ast

    size = component.present(path).st_size
    with (component.root / path).open("rb", buffering=0) as stream:
        prefix = stream.read(8)
        require(prefix[:6] == b"\x93NUMPY" and prefix[6:] in (b"\x01\x00", b"\x02\x00", b"\x03\x00"),
                f"Invalid NPY magic or version: {path}")
        width = 2 if prefix[6] == 1 else 4
        length_bytes = stream.read(width)
        length = int.from_bytes(length_bytes, "little")
        require(len(length_bytes) == width and 0 < length <= size - 8 - width, f"Invalid NPY header length: {path}")
        if length > 16 * 1024:
            raise UnknownMetadata(f"NPY header exceeds 16 KiB: {path}")
        header = stream.read(length)
        offset = stream.tell()
    try:
        spec = ast.literal_eval(header.decode("utf-8" if prefix[6] == 3 else "latin-1").strip())
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError(f"Invalid NPY header: {path}") from error
    require(isinstance(spec, dict) and spec.keys() == {"descr", "fortran_order", "shape"},
            f"Invalid NPY header fields: {path}")
    shape = spec["shape"]
    require(spec["descr"] == "<f4" and spec["fortran_order"] is False and
            isinstance(shape, tuple) and len(shape) == 2 and
            all(type(axis) is int and axis > 0 for axis in shape), f"Invalid NPY dtype, layout or shape: {path}")
    require(size == offset + shape[0] * shape[1] * 4, f"NPY file size disagrees with its header: {path}")
    return shape


def sqlite_metadata(component, path, inspect):
    import sqlite3
    from contextlib import closing

    absolute = (component.root / path).resolve()

    def snapshot():
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                Path(str(absolute) + suffix).lstat()
            except FileNotFoundError:
                continue
            raise UnknownMetadata(f"SQLite sidecar present: {absolute.name}{suffix}")
        info = component.present(absolute)
        return info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    before = snapshot()
    with absolute.open("rb", buffering=0) as stream:
        header = stream.read(20)
    require(len(header) == 20 and header[:16] == b"SQLite format 3\0", f"Invalid SQLite header: {path}")
    if header[18:20] != b"\x01\x01":
        raise UnknownMetadata(f"SQLite catalog is not in finalized rollback-journal format: {path}")
    # Callers first establish prior closure evidence. Immutable mode cannot create
    # sidecars or locks. Reject a changing snapshot instead of assuming closure.
    try:
        with closing(sqlite3.connect(absolute.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0)) as db:
            db.set_progress_handler(lambda: 1, 2_000_000)
            require(db.execute("PRAGMA user_version").fetchone() == (0,), "Unsupported SQLite schema version")
            result = inspect(db)
    except sqlite3.DatabaseError as error:
        if getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT or str(error) == "interrupted":
            raise UnknownMetadata(f"SQLite metadata query exceeded its step budget: {path}") from error
        raise ValueError(f"Invalid SQLite catalog: {path}: {error}") from error
    if snapshot() != before:
        raise UnknownMetadata(f"SQLite catalog changed during the query: {path}")
    return result


def sqlite_schema(db, table, columns, primary_key):
    fields = db.execute(f"PRAGMA table_info({table})").fetchall()
    require({row[1]: row[2] for row in fields} == columns and
            [row[1] for row in sorted(fields, key=lambda row: row[5]) if row[5]] == primary_key,
            f"Incompatible SQLite table: {table}")


def prott5_contract(component):
    report = PRIMARY.parent / "final_report.md"
    manifest = component.load(PRIMARY / "manifest.json")
    prott5(component)
    if not component.data["evidence"]:
        raise UnknownMetadata("ProtT5 final certificate is unavailable or incomplete")
    check_digest(manifest["inventory_sha256"])
    require(manifest["stable_id"] == "exact original sequence" and manifest["revision"] and
            "little-endian float32 NPY shards" in manifest["storage"], "Incompatible ProtT5 storage manifest")
    certified = component.load(PRIMARY.parent / "inventory_validation.json")
    inventory = Path(manifest["inventory"])
    _, rows, schema = read_footer(component, inventory)
    require(schema == {"sequence": "string", "windows": "int32", "historical_rows": "int32",
                       "historical_original": "bool", "status": "string"}, "Incompatible ProtT5 inventory schema")
    require(rows == count(certified["unique"]) == component.data["records"], "ProtT5 inventory counts disagree")
    capacity, dimension, batch = (count(manifest[key]) for key in ("shard_rows", "dimension", "batch_size"))
    require(batch > 0, "Invalid ProtT5 batch size")
    shard_count = component.data["details"]["shards"]
    expected_rows = []
    for index in range(shard_count):
        observed = read_npy_header(component, PRIMARY / f"shard-{index:04d}.npy")
        expected = min(capacity, rows - index * capacity)
        require(observed == (expected, dimension), f"ProtT5 shard rows or dimension disagree: {index}")
        expected_rows.append(expected)

    def receipts(db):
        sqlite_schema(db, "batches", {"shard": "INTEGER", "start": "INTEGER", "rows": "INTEGER",
                                      "digest": "TEXT", "token_s": "REAL", "forward_s": "REAL",
                                      "write_s": "REAL"}, ["shard", "start"])
        offsets = [0] * len(expected_rows)
        batches = 0
        for index, start, length, digest in db.execute("SELECT shard,start,rows,digest FROM batches ORDER BY shard,start"):
            require(type(index) is int and 0 <= index < shard_count, "Invalid ProtT5 receipt shard")
            require(start == offsets[index] < expected_rows[index] and length == min(batch, expected_rows[index] - start),
                    f"ProtT5 receipt range disagrees: shard {index}, start {start}")
            check_digest(digest)
            offsets[index] += length
            batches += 1
        require(offsets == expected_rows, "ProtT5 receipt coverage is incomplete")
        return batches

    recorded_batches = report_count(component.read(report), r"\| Lotes SQLite confirmados \| ([\d,.]+) \|")
    batches = sqlite_metadata(component, PRIMARY / "progress.sqlite", receipts)
    require(recorded_batches is not None, "ProtT5 certificate omits its receipt count")
    require(batches == recorded_batches, "ProtT5 receipt count disagrees with the certificate")
    return {"inventory_footer_rows": rows, "shard_header_rows": sum(expected_rows), "shards": shard_count,
            "dimension": dimension, "dtype": "float32 (<f4)", "sqlite_receipts": batches,
            "prior_evidence": str(report)}


def secondarybert_contract(component):
    secondarybert(component)
    report = SECONDARY / "secondarybert_report.md"
    if not component.data["evidence"]:
        raise UnknownMetadata("SecondaryBERT final certificate is unavailable or incomplete")
    pilot = component.load(SECONDARY / "pilot.json")
    text = component.read(report)
    counts = {
        category: report_count(text, rf"\| {label} \| ([\d,.]+) \|")
        for category, label in (("historical", "Históricas verificadas y accesibles por referencia"),
                                ("pilot", "Generadas y verificadas en el piloto"),
                                ("generated", "Generadas en la ejecución completa"),
                                ("pending", "Pendientes de generación"))
    }
    if any(value is None for value in counts.values()):
        raise UnknownMetadata("SecondaryBERT certificate omits storage category counts")
    new_count = counts["pilot"] + counts["generated"]
    require(counts["pending"] == 0 and counts["pilot"] == pilot["n"] and
            counts["historical"] + new_count == component.data["records"], "SecondaryBERT storage counts disagree")
    require(pilot["dtype"] == "float32", "Incompatible SecondaryBERT dtype")
    dimension = component.data["details"]["dimension"]
    fingerprint = pilot["config"]["fingerprint"]
    check_digest(fingerprint)
    require(fingerprint.encode() in text and re.search(rb"\b" + str(dimension).encode() + rb" valores float32", text),
            "SecondaryBERT model or dimension differs from closure evidence")
    archive = Path("results/nap_cnb_v2_embedding_audit")
    for filename, expected in (("verified_secondarybert_frequencies.parquet", counts["historical"]),
                               ("missing_secondarybert_structures.parquet", new_count)):
        _, rows, schema = read_footer(component, archive / filename)
        require(schema.get("secondary_structure") == "string" and rows == expected,
                f"SecondaryBERT inventory disagrees: {filename}")
    index = SECONDARY / "index.sqlite"
    recorded_size = report_count(text, r"\| SQLite final \| ([\d,.]+) bytes")
    if recorded_size is None:
        raise UnknownMetadata("SecondaryBERT certificate omits its index size")
    declared_archives = report_count(text, r"integridad en ([\d,.]+) bloques canónicos")
    if declared_archives is None:
        raise UnknownMetadata("SecondaryBERT certificate omits its archive count")
    require(0 < declared_archives <= 4096, "Unexpected SecondaryBERT archive count")

    def catalog(db):
        sqlite_schema(db, "shard", {"id": "INTEGER", "path": "TEXT"}, ["id"])
        sqlite_schema(db, "inventory", {"structure": "TEXT", "sha256": "BLOB", "length": "INTEGER",
                                        "windows": "INTEGER", "shard": "INTEGER", "row_offset": "INTEGER"},
                      ["structure"])
        sqlite_schema(db, "embedding", {"structure": "TEXT", "vector": "BLOB", "checksum": "BLOB"}, ["structure"])
        paths = db.execute("SELECT id,path FROM shard LIMIT ?", (declared_archives + 1,)).fetchall()
        require(len(paths) == declared_archives and len({path for _, path in paths}) == len(paths),
                "SecondaryBERT archive table disagrees with the certificate")
        for _, path in paths:
            require(Path(path).suffix == ".npy" and Path(path).parent.name == "chunks",
                    f"Unexpected SecondaryBERT canonical path: {path}")
            component.present(Path(path + ".zst"))
            component.present(Path(path + ".archive.json"))
        if new_count:
            key = db.execute("SELECT structure FROM embedding LIMIT 1").fetchone()
            require(key is not None, "SecondaryBERT has no new embedding references")
            link = db.execute("SELECT length,shard,row_offset FROM inventory WHERE structure=?", key).fetchone()
            require(link == (25, None, None) and re.fullmatch("[CHE]{25}", key[0]),
                    "Invalid sampled SecondaryBERT new embedding reference")
        return len(paths)

    found = sqlite_metadata(component, index, catalog)
    require(component.present(index).st_size == recorded_size, "SecondaryBERT index size differs from its certificate")
    return {"certified_keys": component.data["records"], "declared_historical_keys": counts["historical"],
            "declared_new_keys": new_count, "dimension": dimension, "dtype": pilot["dtype"],
            "canonical_archive_paths_checked": found, "prior_evidence": str(report),
            "new_reference_sample_checked": bool(new_count)}


def structures_contract(component):
    selection_contract(component)
    evidence_before = len(component.data["evidence"])
    structures(component)
    if len(component.data["evidence"]) == evidence_before:
        raise UnknownMetadata("Structural recovery, closure or selection evidence is incomplete")
    spec = component.load(SELECTION)
    totals = spec["totals"]
    overlay, excluded = (SELECTION.parent / spec[key] for key in ("structure_overlay", "exclusions"))
    metrics_path = overlay.parent / "metrics.json"
    metrics = component.load(metrics_path)
    require(metrics["matched_after"] == totals["matched"] + totals["recovered"]
            and metrics["matched_before"] == totals["matched"] and metrics["binary_windows"] == totals["windows"]
            and metrics["remaining_windows"] == totals["excluded"]
            and metrics["window_counts"]["recovered"] == totals["recovered"],
            "Structural recovery counts disagree with the selection")
    recovered = footer_contract(
        component, overlay,
        ("window_id parent_url parent_sha256 secondary_structure structure_prediction_id verification_method validation_status", {}),
        totals["recovered"], metrics["artifact_bytes"][overlay.name])
    excluded_size, excluded_rows, schema = read_footer(component, excluded)
    require(schema == {"window_id": "string", "parent_sha256": "string", "window_start": "int64",
                       "invalid_residues": "string"} and excluded_rows == totals["excluded"],
            "Structural exclusions schema or row count disagrees")
    for name in ("prediction_sources.tsv", "proteins.tsv"):
        require(component.present(overlay.parent / name).st_size == metrics["artifact_bytes"][name],
                f"Structural provenance metadata size differs: {name}")
    component.present(excluded.parent / "pending_proteins.tsv")
    sources = metrics["sources"]
    require(isinstance(sources, list) and bool(sources), "Structural prediction provenance is empty")
    for source in sources:
        component.present(Path(source["path"]))
        check_digest(source["sha256"])
    return {"retained_windows": totals["matched"] + totals["recovered"], "recovered_windows": totals["recovered"],
            "excluded_windows": totals["excluded"], "overlay": recovered,
            "exclusions": {"footer_rows": excluded_rows, "declared_rows": totals["excluded"], "bytes": excluded_size},
            "prediction_sources": [source["path"] for source in sources], "prior_evidence": component.data["evidence"]}


VALIDATIONS = {
    "validate-prott5": (
        (("prott5_manifest_inventory_headers_and_receipts", PRIMARY / "manifest.json", prott5_contract),),
        ("embedding_values", "numerical_integrity", "full_hashes")),
    "validate-secondarybert": (
        (("secondarybert_certificate_catalog_and_references", SECONDARY / "index.sqlite", secondarybert_contract),),
        ("live_inventory_and_blob_recounts", "blob_checksums", "historical_zstd_decompression", "numerical_integrity")),
    "validate-structures": (
        (("structure_selection_overlay_exclusions_and_provenance", SELECTION, structures_contract),),
        ("coordinate_reverification", "protein_window_correspondence", "structure_prediction", "large_source_hashes")),
    "validate-selection": (
        (("selection_contract", SELECTION, selection_contract),),
        ("large_supplement_hashes", "row_level_window_validation", "selection_rebuild")),
    "validate-datasets": (
        (("dataset_metadata_and_declared_counts", METRICS, dataset_contract),
         *((f"footer_{Path(name).stem}", VIEWS / name,
            lambda c, name=name: dataset_contract(c, filename=name)) for name in DATASET_SCHEMAS)),
        ("row_level_uniqueness", "global_label_recomputation", "provenance_joins", "embedding_integrity")),
    "validate-splits": (
        (("split_metadata_counts_and_footer", SPLITS, split_contract),),
        ("assignment_recomputation", "independence_reverification", "full_parquet_hashes")),
    "validate-d1": (
        (("d1_manifest_references_counts_and_dimensions", D1, d1_contract),),
        ("embedding_payload_integrity", "dataset_row_joins", "label_recomputation", "assignment_recomputation",
         "full_parquet_and_sqlite_hashes")),
}


def validate(root, command):
    checks, skipped = VALIDATIONS[command]
    results = [validation_check(root, *check) for check in checks]
    results.extend({"name": name, "result": "SKIPPED", "reason": "Outside metadata-only scope"} for name in skipped)
    states = {item["result"] for item in results}
    overall = next((state for state in ("FAIL", "INCOMPLETE") if state in states), "PASS")
    return overall, results


def render_validation(report):
    print(f"{PIPELINE} — {report['command']}")
    print(f"Repository: {report['root']}")
    print(f"Mode: {report['mode']}\n")
    width = max((len(item["name"]) for item in report["checks"]), default=46)
    for item in report["checks"]:
        print(f"{item['name']:{max(width, 46)}} {item['result']}")
        if "error" in item:
            print(f"  {item['error']['message']}")
    print(f"\nOverall: {report['overall'] or 'NOT RUN'}")
    if report["command"] in {"validate-prott5", "validate-secondarybert", "validate-structures"}:
        print("Scope: metadata, file headers and bounded catalog queries where applicable.")
        for item in report["checks"]:
            if item["result"] == "PASS":
                details = item["details"]
                summary = {key: value for key, value in details.items() if isinstance(value, (int, str))}
                print("  " + "; ".join(f"{key}: {value}" for key, value in summary.items()))
    else:
        print("Scope: metadata and, where applicable, Parquet footers only.")
    print("No exhaustive integrity checks performed.")
    for error in report["errors"]:
        print(error["message"], file=sys.stderr)


TRAIN_PROFILES = ROOT / "data_pipeline/nap_cnb_v2_training_profiles.json"
HISTORICAL_FEATURES = Path("data/data_input_nn_shuffled_concatenate")
HISTORICAL_SCALER = Path("neural_network/MLP/standardizer_all_train_chunks.npz")


def training_profile(component, args):
    import math

    profiles = component.load(TRAIN_PROFILES)
    require(count(profiles["schema_version"]) == 1, "Unsupported training profile schema")
    config = component.load(args.config) if args.config else {}
    require(set(config) <= {"schema_version", "profile", "parameters"}, "Unknown training configuration field")
    version = config.get("schema_version")
    require(not args.config or (type(version) is int and version == 1),
            "Training configuration requires schema_version 1")
    name = config.get("profile", "lr_balanced" if args.model == "lr" else "mlp_historical")
    require(isinstance(name, str) and name in profiles["profiles"],
            "Unknown or unsupported training profile; v2 requires exact 50/50 TRAIN balance")
    profile = profiles["profiles"][name]
    require(profile["model"] == args.model, "Training profile is incompatible with the chosen model")
    require(profile["sampling"] == "exact_50_50", "v2 requires the historical exact 50/50 TRAIN sampler")
    overrides = config.get("parameters", {})
    parameters = {**profile["parameters"]}
    require(isinstance(overrides, dict) and overrides.keys() <= parameters.keys(), "Unknown training parameter")
    parameters.update(overrides)
    for key, value in parameters.items():
        if key in {"epochs", "batch_size", "seed", "scheduler_t0", "scheduler_tmult"}:
            count(value)
            require(value > 0 or key == "seed", f"{key} must be positive")
        else:
            require(type(value) in (int, float) and math.isfinite(value) and value >= 0, f"Invalid {key}")
    require(parameters["learning_rate"] > 0, "learning_rate must be positive")
    require(profile["sampling"] != "exact_50_50" or parameters["batch_size"] % 2 == 0,
            "Balanced training requires an even batch size")
    if args.model == "mlp":
        require(parameters["dropout"] < 1 and parameters["scheduler_min_lr"] <= parameters["learning_rate"],
                "Invalid dropout or scheduler_min_lr")
    return {"name": name, **profile, "parameters": parameters}


def original_training_data(component, label):
    certified = d1_contract(component)
    manifest = component.load(D1)
    features = manifest["embeddings"]
    details = {
        "contract": "D1" if label == "global" else "v2 family-context base",
        "path": manifest["dataset"]["path"],
        "label": "label_global" if label == "global" else "label_original",
        "rows": certified["declared_rows"], "by_split": certified["by_split"],
        "dimensions": certified["dimensions"], "embeddings": features,
        "splits": manifest["splits"], "layout": "separate_embedding_catalogs",
        "scaler": {"status": "REQUIRES_TRAIN_FIT", "method": "feature-wise standardization",
                   "scope": "selected v2 TRAIN only", "path": None},
    }
    if label == "original":
        metrics = component.load(METRICS)
        counts = dataset_metadata(component, metrics, component.load(SELECTION))
        base_rows = counts["base_dataset.parquet"]
        negatives = sum(count(row["base"]) - count(row["base_positive"]) for row in metrics["families"].values())
        split_report = component.load(SPLITS)
        base_splits = split_counts(split_report["base"])
        require(sum(row["rows"] for row in base_splits.values()) == base_rows and
                sum(row["negative"] for row in base_splits.values()) == negatives, "Base split counts disagree")
        path = VIEWS / "base_dataset.parquet"
        require(component.present(path).st_size == count(metrics["files_bytes"][path.name]),
                "Base file size disagrees with published metrics")
        details.update(path=str(path), rows=base_rows, by_split=base_splits)
    return details


def historical_training_data(component):
    layout = component.load(HISTORICAL_FEATURES / "feature_layout.json")
    split = component.load(HISTORICAL_FEATURES / "reorder_manifest.json")
    require(layout["format"] == "primary_secondary_float32_v1" and layout["normalized"] is False,
            "Incompatible historical feature layout")
    require(layout["complete"] is True, "Historical feature layout is incomplete")
    require(all(count(layout[key]) == count(split[key]) for key in ("rows", "chunks")),
            "Historical layout and reorder manifest counts disagree")
    primary, secondary = count(layout["primary_dim"]), count(layout["secondary_dim"])
    require((primary, secondary) == (1024, 768), "Historical feature dimensions disagree")
    chunk = HISTORICAL_FEATURES / "mixed/classification_mixed_ProtT5_chunks"
    component.present(chunk / "chunk_000000_X.npy")
    for field in ("y", "group_id", "split_id"):
        component.present(chunk / "chunk_metadata" / f"chunk_000000_{field}.npy")
    component.present(HISTORICAL_SCALER)
    return {
        "contract": "historical augmented chunks", "path": str(HISTORICAL_FEATURES), "label": "historical y",
        "rows": count(layout["rows"]), "chunks": count(layout["chunks"]),
        "dimensions": {"ProtT5": primary, "SecondaryBERT": secondary, "combined": primary + secondary},
        "embeddings": {"layout": "concatenated_float32", "metadata": str(HISTORICAL_FEATURES / "feature_layout.json")},
        "splits": {"contract": "historical per-row split_id", "source": str(HISTORICAL_FEATURES / "reorder_manifest.json"),
                   "v2_independence_verified": False, "manifest_fields_available": sorted(split)},
        "scaler": {"status": "HISTORICAL_ONLY", "method": "feature-wise standardization",
                   "scope": "historical augmented TRAIN only", "path": str(HISTORICAL_SCALER)},
        "validation_scope": "layout, manifest, one chunk and its three metadata paths; no payloads read",
    }


V2_SCALERS = Path("results/nap_cnb_v2_training/scalers")
V2_EVALUATION = {
    "optimization": "TRAIN",
    "scaler_fit": "TRAIN",
    "checkpoint_selection": "VALIDATION",
    "selection_metric": "validation_loss",
    "final_evaluation": "TEST",
    "test_during_training": False,
    "early_stopping": False,
    "implementation": "explicit v2 hook in the shared historical engine",
}


def scaler_contract(root, label, dataset):
    component = Component(root, D1)
    manifest = component.load(D1)
    split_report = component.load(SPLITS)
    artifact = "global_dataset" if label == "global" else "base_dataset"
    return {
        "schema_version": 1,
        "release": "NAP-CNB v2",
        "label": dataset["label"],
        "view": dataset["path"],
        "split": "TRAIN",
        "train_rows": dataset["by_split"]["train"]["rows"],
        "dimensions": dataset["dimensions"],
        "method": "historical modality standardization, population variance",
        "accumulator_dtype": "float64",
        "output_dtype": "float32",
        "constant_scale_threshold": 1e-12,
        "d1_manifest_sha256": hashlib.sha256(component.read(D1)).hexdigest(),
        "split_validation_sha256": hashlib.sha256(component.read(SPLITS)).hexdigest(),
        "declared_input_sha256": {
            "view": split_report["catalog_sha256"][artifact],
            "assignments": split_report["assignment_sha256"],
            "prott5_manifest": manifest["inputs_sha256"][manifest["embeddings"]["ProtT5"]["manifest"]],
            "secondarybert_index": manifest["inputs_sha256"][manifest["embeddings"]["SecondaryBERT"]["index"]],
        },
    }


def scaler_metadata(path):
    import zipfile

    require(path.stat().st_size <= 2 * METADATA_LIMIT, "Scaler archive exceeds metadata budget")
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        required = {"primary_mean.npy", "primary_scale.npy", "secondary_mean.npy", "secondary_scale.npy",
                    "sampled_dataset_names.npy", "sampled_chunk_ids.npy", "provenance.json"}
        require(len(members) == len(required) and set(members) == required, "Unexpected scaler archive members")
        require(all(item.file_size <= METADATA_LIMIT for item in archive.infolist()), "Scaler archive member too large")
        with archive.open("provenance.json") as stream:
            metadata = json.load(stream)
    require(isinstance(metadata, dict), "Invalid scaler provenance")
    return metadata


def check_scaler_contract(path, expected):
    metadata = scaler_metadata(path)
    require(all(metadata.get(key) == value for key, value in expected.items()), "Scaler provenance differs from TRAIN")
    require(metadata.get("output") == str(path.resolve()), "Scaler output path differs from the provenance")
    require(type(metadata.get("batch_size")) is int and metadata["batch_size"] > 0,
            "Invalid scaler fit batch size")
    return metadata


def scaler_plan(root, label, dataset):
    import zipfile

    relative = V2_SCALERS / ("d1.npz" if label == "global" else "base.npz")
    path = root / relative
    plan = dataset["scaler"]
    plan.update(planned_path=str(relative), fit_command=[
        "python", "-B", "-m", "data_pipeline.nap_cnb_v2_batches", "fit-scaler",
        "--root", str(root), "--label", label, "--batch-size", "8192",
        "--confirm-full-train", "--output", str(relative),
    ])
    if not path.exists():
        return
    try:
        metadata = check_scaler_contract(path, scaler_contract(root, label, dataset))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, zipfile.BadZipFile) as error:
        plan.update(status="INCOMPATIBLE", detail=str(error))
    else:
        plan.update(status="METADATA_MATCH", path=str(relative), train_rows=metadata["train_rows"],
                    detail="Provenance matches; numeric statistics must be checked by the reader before use.")



def training_plan(root, args, report):
    component = Component(root, args.config)
    profile = training_profile(component, args)
    component.present(Path(profile["script"]))
    output = (root / (args.output or Path("results/nap_cnb_v2_training") /
                      f"{args.model}-{args.data}-{args.label}")).resolve()
    report.update(model=args.model, data=args.data, label=args.label, profile=profile, output=str(output),
                  execution="DISABLED — DRY RUN ONLY", command_preview=None, blockers=[])
    if args.data == "original":
        report["dataset"] = original_training_data(component, args.label)
        adapter = Path("data_pipeline/nap_cnb_v2_batches.py")
        # The adapter belongs to the code checkout, independently of --root data.
        component.present(ROOT / adapter)
        report["adapter"] = {"path": str(adapter), "workers": 1, "integration": "legacy row hooks"}
        scaler_plan(root, args.label, report["dataset"])
        scaler = report["dataset"]["scaler"]
        report["overall"] = "INCOMPATIBLE" if scaler["status"] == "INCOMPATIBLE" else "INCOMPLETE"
        report["checkpoint_policy"] = dict(V2_EVALUATION)
        if scaler["status"] == "REQUIRES_TRAIN_FIT":
            report["blockers"].append("The scaler for the selected TRAIN view has not been fitted.")
        elif scaler["status"] == "INCOMPATIBLE":
            report["blockers"].append(f"Scaler contract rejected: {scaler['detail']}")
    elif args.label == "global":
        report["overall"] = "INCOMPATIBLE"
        report["blockers"].append("D2 is not available. Historical y is not the v2 global label.")
    else:
        report["dataset"] = historical_training_data(component)
        report["overall"] = "INCOMPATIBLE"
        report["blockers"].append(
            "Historical data are available for replay, but their y and row splits are incompatible with the v2 release.")
    if output.exists():
        report["blockers"].append("The requested output already exists; a future run needs an unused destination.")
    return 1


def render_training(report):
    print(f"{PIPELINE} — Training preflight")
    print(f"Repository: {report['root']}")
    print(f"Status: {report['overall']}")
    print("Execution: DISABLED — DRY RUN ONLY")
    if "profile" in report:
        profile = report["profile"]
        print(f"Model: {report['model']} ({profile['name']})")
        print(f"Implementation: {profile['script']}")
        print(f"Configuration: {json.dumps(profile['parameters'], sort_keys=True)}")
        print(f"Sampling: {profile['sampling']}")
        print(f"Output (planned): {report['output']}")
        if "adapter" in report:
            print(f"Adapter: {report['adapter']['path']} ({report['adapter']['integration']})")
        if "dataset" in report:
            data = report["dataset"]
            print(f"Dataset: {data['contract']} — {data['path']}")
            print(f"Label: {data['label']}; records: {data['rows']:,}")
            print(f"Features: {json.dumps(data['dimensions'])}")
            if data.get("by_split"):
                print("Splits: " + " / ".join(f"{name} {row['rows']:,}" for name, row in data["by_split"].items()))
            print(f"Scaler: {data['scaler']['status']} ({data['scaler']['scope']})")
            if "planned_path" in data["scaler"]:
                print(f"Scaler path: {data['scaler']['planned_path']}")
        if "checkpoint_policy" in report:
            print("Checkpoint policy for v2: VALIDATION loss; TEST once after selection. Both keep natural prevalence.")
    print("Launch command: unavailable for this contract")
    for issue in report.get("blockers", ()):
        print(f"- {issue}")
    for error in report["errors"]:
        print(f"- {error['message']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root (default: this module's repository)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", *VALIDATIONS):
        help_text = ("show artifact status using published metadata" if name == "status"
                     else f"check the {name.removeprefix('validate-')} contract using published metadata")
        query = commands.add_parser(name, help=help_text)
        query.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="repository root")
        query.add_argument("--json", action="store_true", help="output structured JSON")
    train = commands.add_parser("train", help="plan a training run without launching it")
    train.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="repository root")
    train.add_argument("--json", action="store_true", help="output structured JSON")
    train.add_argument("--model", choices=("lr", "mlp"), required=True)
    train.add_argument("--data", choices=("original", "blosum62"), required=True)
    train.add_argument("--label", choices=("original", "global"), required=True)
    train.add_argument("--config", type=Path, help="optional JSON profile overrides, relative to the repository")
    train.add_argument("--output", type=Path, help="planned output path, relative to the repository")
    train.add_argument("--dry-run", action="store_true", help="explicitly request planning; this is always the mode")
    args = parser.parse_args(argv)
    root = args.root or ROOT
    report = {"pipeline": PIPELINE, "root": str(root), "mode": "metadata-only", "errors": []}
    if args.command == "status":
        report["components"] = {}
    elif args.command == "train":
        report.update(command="train", mode="preflight", overall="INCOMPLETE", execution="DISABLED — DRY RUN ONLY")
    else:
        report.update(command=args.command, overall=None, checks=[])
    try:
        root = root.resolve()
        report["root"] = str(root)
        if not root.is_dir():
            raise OSError(f"Repository root is not a directory: {root}")
        if args.command == "status":
            report["components"] = status(root)
            code = int(any(c["status"] in {"MISSING", "INCONSISTENT", "UNKNOWN"}
                           for c in report["components"].values()))
        elif args.command == "train":
            try:
                code = training_plan(root, args, report)
            except (FileNotFoundError, KeyError, UnknownMetadata) as error:
                report["errors"].append({"code": "missing_prerequisite", "message": str(error)})
                code = 1
            except (ValueError, TypeError, OverflowError, IndexError, AttributeError) as error:
                report["overall"] = "INCOMPATIBLE"
                report["errors"].append({"code": "incompatible_contract", "message": str(error)})
                code = 1
        else:
            report["overall"], report["checks"] = validate(root, args.command)
            code = int(report["overall"] != "PASS")
    except (OSError, RuntimeError) as error:
        report["errors"].append({"code": "query_failed", "message": str(error)})
        code = 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "status":
        render(report)
    elif args.command == "train":
        render_training(report)
    else:
        render_validation(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
