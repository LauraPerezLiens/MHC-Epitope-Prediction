import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pyarrow.parquet as pq

from data_pipeline.scripts.rebuild_iedb import rebuild


FAMILY = "HLA-A"
PARENT = "example.org/PARENT.2"
SOURCE = "example.org/SOURCE.1"
SEQUENCE = "M" * 10 + "PEPTIDE" + "W" * 25 + "ACDEFGH" + "Y" * 20


def event(index, name, start, end, *, modification="", source=PARENT, parent=PARENT, family=FAMILY):
    row = dict.fromkeys(rebuild.FIELDS, "")
    row.update(
        epitope__name=name,
        epitope__modifications=modification,
        epitope__starting_position=str(start),
        epitope__ending_position=str(end),
        epitope__epitope_iri=f"https://www.iedb.org/epitope/{index}",
        assay__iri=f"https://www.iedb.org/assay/{index + 100}",
        family=family, organism="human", mhc_class="mhc-I",
        parent_url=parent, source_url=source, assay_type="mhc",
        source_file=f"{family}_example.csv", source_row_index=index,
    )
    return row


class LocalRegistry:
    def __init__(self):
        self.references = {
            PARENT: rebuild.Reference("PARENT.2", "2", SEQUENCE, "archived_parent_fasta", ""),
            SOURCE: rebuild.Reference("SOURCE.1", "1", "GGG" + SEQUENCE, "versioned_cache", ""),
        }
        self.records = {}
        self.prior_loci = {}

    def ref(self, organism, url):
        return self.references.get(url)

    def curated(self, row, peptide):
        return self.records.get(rebuild.identifiers(row)[0], [])

    def prepare(self, rows):
        for _ in rows:
            pass


class RebuildIEDBTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.output = Path(scratch.name)
        (self.output / "raw").mkdir()
        (self.output / "checkpoints").mkdir()
        self.registry = LocalRegistry()

    def read(self, table, family=FAMILY):
        return pq.read_table(self.output / table / f"{family}.parquet").to_pylist()

    def build(self, *events, family=FAMILY):
        with gzip.open(self.output / "raw" / f"{family}_test.jsonl.gz", "wt") as stream:
            for row in events:
                stream.write(json.dumps(row) + "\n")
        rebuild.build_family(self.output, family, self.registry)
        return rebuild.reconcile_family(self.output, family)

    def test_versioned_isoform_requires_exact_reference(self):
        domain = "www.uniprot.org/uniprot"
        isoform = f"{domain}/P12345-2.3"
        canonical = f"{domain}/P12345.3"
        unversioned = f"{domain}/P12345-2"
        events = [event(1, "PEPTIDE", 11, 17, source=isoform, parent=canonical),
                  event(2, "PEPTIDE", 11, 17, source=unversioned, parent=canonical)]
        with patch.object(rebuild, "load_archived", return_value={}):
            registry = rebuild.Registry(self.output, self.output, None)
        registry.iedb = {epitope: {"e_modification": []} for epitope in ("1", "2")}
        with patch.object(registry, "fetch_ncbi") as ncbi, patch.object(registry, "fetch_uniprot") as uniprot:
            registry.prepare(events)
        ncbi.assert_called_once_with(["P12345-2.3", "P12345.3"])
        self.assertEqual([call.args[0] for call in uniprot.call_args_list], [["P12345-2"], ["P12345"]])
        self.assertIsNone(registry.ref("human", isoform))

    def test_modified_only_parent_generates_no_examples(self):
        stats = self.build(event(1, "PEPTIDE", 11, 17, modification="Acetylation"))
        self.assertEqual(stats.get("windows", 0), 0)
        self.assertEqual(stats["pending_events"], 1)
        self.assertEqual(self.read("families"), [])
        self.assertEqual(self.read("proteins")[0]["status"], "no_verified_simple_evidence")
        self.assertEqual(self.read("evidence_pending")[0]["assay_id"], "101")
        self.assertEqual(rebuild.global_counts(self.output, [FAMILY]), {})

    def test_simple_positive_uses_one_window_per_start_and_full_containment(self):
        stats = self.build(event(1, "PEPTIDE", 11, 17), event(2, "PEPTIDE", 11, 17))
        self.assertEqual(stats["windows"], len(SEQUENCE) - 24)
        self.assertEqual(stats["positive_windows"], 11)
        windows = self.read("families")
        self.assertEqual(windows[10]["sequence"], SEQUENCE[10:35])
        self.assertEqual((windows[10]["window_start"], windows[10]["window_end"]), (11, 35))
        self.assertEqual(windows[10]["contains_epitope"], 1)
        self.assertEqual(windows[11]["contains_epitope"], 0)
        self.assertEqual(self.read("provenance")[10]["verified_event_ids"],
                         [f"{FAMILY}_example.csv:1", f"{FAMILY}_example.csv:2"])

    def test_mixed_parent_keeps_shared_windows_and_holds_out_modified_positives(self):
        self.registry.records["3"] = [{"structure_id": "3", "linear_sequence": "ACDEFGH",
                                       "e_modification": ["Phosphorylation"]}]
        self.build(event(1, "PEPTIDE", 11, 17),
                   event(2, "PEPTIDE", 11, 17, modification="Acetylation"),
                   event(3, "ACDEFGH", 43, 49))
        self.assertEqual([row["window_start"] for row in self.read("families") if row["contains_epitope"]],
                         list(range(1, 12)))
        held = self.read("holdouts")
        self.assertEqual([row["window_start"] for row in held], list(range(25, 44)))
        self.assertTrue(all(row["excluded_event_ids"] == [f"{FAMILY}_example.csv:3"] for row in held))
        self.assertTrue(all(row["window_start"] not in range(25, 44) for row in self.read("families")))
        self.assertEqual([row["chemistry"] for row in self.read("evidence_pending")], ["modified", "modified"])

    def test_historical_truncation_used_only_to_hold_out(self):
        self.build(event(1, "PEPTIDE", 11, 17),
                   event(2, "ACDEFGH + tag", 43, 49, modification="Conjugation"))
        self.assertEqual(len(self.read("holdouts")), 19)
        self.assertEqual(len(self.read("evidence_verified")), 1)

    def test_source_projection_and_invalid_source(self):
        self.build(event(1, "PEPTIDE", 14, 20, source=SOURCE),
                   event(2, "PEPTIDE", 11, 17, source=SOURCE))
        verified = self.read("evidence_verified")[0]
        self.assertEqual((verified["source_start"], verified["parent_start"], verified["parent_end"]), (14, 11, 17))
        self.assertEqual(verified["method"], "full_reference_alignment")
        self.assertEqual(self.read("evidence_pending")[0]["reason"], "source_interval_mismatch")

    def test_only_version_matched_explicit_parent_annotation_can_bypass_missing_source(self):
        row = event(1, "PEPTIDE", 14, 20, source="example.org/MISSING.1")
        item = dict(accession="PARENT.1", starting_position=11, ending_position=17)
        self.registry.records["1"] = [dict(structure_id="1", linear_sequence="PEPTIDE", e_modification=[],
                                           curated_source_antigens=[item])]
        self.assertEqual(rebuild.verify_event(row, self.registry)["reason"], "source_reference_unavailable")
        item["accession"] = "PARENT.2"
        row["epitope__starting_position"] = ""
        self.build(row)
        self.assertEqual(self.read("evidence_verified")[0]["method"], "iedb_explicit_parent_reference")

    def test_prior_mapping_requires_same_assay_and_parent_hash(self):
        row = event(1, "PEPTIDE", 14, 20, source="example.org/MISSING.1")
        key = FAMILY, row["source_url"], PARENT, "PEPTIDE", "14", "20"
        audit = dict(ids="1", assays="999", parent_sequence_sha256="unused",
                     corrected_start="11", corrected_end="17")
        self.registry.prior_loci[key] = [audit]
        self.assertEqual(rebuild.verify_event(row, self.registry)["status"], "pending")
        audit["assays"] = "101"
        self.assertEqual(rebuild.verify_event(row, self.registry)["status"], "pending")
        audit["parent_sequence_sha256"] = self.registry.references[PARENT].sha256
        self.build(row)
        self.assertEqual(self.read("evidence_verified")[0]["method"], "verified_prior_coordinate_audit")

    def test_global_positive_retained_across_families(self):
        self.build(event(1, "PEPTIDE", 11, 17))
        self.build(event(2, "ACDEFGH", 43, 49, family="HLA-B"), family="HLA-B")
        rebuild.global_counts(self.output, ["HLA-A", "HLA-B"])
        results = {r["sequence"]: r for r in pq.read_table(self.output / "global_index.parquet").to_pylist()}
        first = results[SEQUENCE[:25]]
        self.assertEqual((first["observations"], first["positive_observations"], first["global_contains_epitope"]),
                         (2, 1, 1))


if __name__ == "__main__":
    unittest.main()
