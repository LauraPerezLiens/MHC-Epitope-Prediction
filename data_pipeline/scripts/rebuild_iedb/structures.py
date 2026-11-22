"""Resolve archived whole-protein structural predictions by identity and sequence."""

from collections import defaultdict
import csv
import hashlib

import pyarrow as pa


STRUCTURE_FIELDS = [
    ("secondary_structure", pa.string()),
    ("structure_prediction_id", pa.string()),
    ("structure_status", pa.string()),
]


class StructureArchive:
    def __init__(self, paths):
        self.records = defaultdict(set)
        for organism, path in paths.items():
            with path.open(newline="") as stream:
                for row in csv.DictReader(stream):
                    url = row["protein_url"].strip().removeprefix("https://").removeprefix("http://").rstrip("/")
                    self.records[organism, url].add((row["sequence"].strip(), row["secondary_structure"].strip()))

    def resolve(self, organism, url, sequence, pinned):
        candidates = self.records.get((organism, url))
        if not candidates:
            return "missing_prediction", None, None
        if not pinned:
            return "unverified_archived_reference", None, None
        predictions = {structure for primary, structure in candidates if primary == sequence}
        if not predictions:
            return "protein_sequence_mismatch", None, None
        if len(predictions) != 1:
            return "ambiguous_prediction", None, None
        structure = predictions.pop()
        if len(structure) != len(sequence) or set(structure) - {"C", "H", "E"}:
            return "invalid_prediction", None, None
        identifier = hashlib.sha256(f"{sequence}\n{structure}".encode()).hexdigest()
        return "matched", structure, identifier


def packed_structure(sequence):
    return int(sequence.translate(str.maketrans("CHE", "012")), 4)
