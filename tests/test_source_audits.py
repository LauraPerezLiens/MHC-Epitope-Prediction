import csv
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.scripts.source_audits import exact_embeddings as embedding
from data_pipeline.scripts.source_audits import omitted_epitopes as epitope


class EpitopeAuditTests(unittest.TestCase):
    def test_parent_identity_preserves_isoforms_and_fasta_versions(self):
        archived = {
            ("human", "provider/P123-1"): {"ABCDE"},
            ("mouse", "provider/P123-1"): {"ABCDE"},
            ("human", "provider/P123-2"): {"ABCDE"},
            ("human", "provider/P123-3"): {"ABCDE"},
            ("mouse", "provider/P123-3"): {"BBCDE"},
            ("human", "provider/P123-4"): {"BBCDE", "ABCDE"},
        }
        key = epitope.resolve_parent(archived, "human", "provider/P123-1")[0]
        self.assertEqual(key, epitope.resolve_parent(archived, "mouse", "provider/P123-1")[0])
        self.assertNotEqual(key, epitope.resolve_parent(archived, "human", "provider/P123-2")[0])
        self.assertNotEqual(epitope.resolve_parent(archived, "mouse", "provider/P123-3")[0],
                            epitope.resolve_parent(archived, "human", "provider/P123-3")[0])
        self.assertEqual(epitope.resolve_parent(archived, "human", "provider/P123-4")[2],
                         "conflicting_fasta_versions")
        self.assertEqual(epitope.protein_url(" https://provider/P123-1 "), "provider/P123-1")

    def test_requires_full_containment_and_exact_coordinate_slice(self):
        protein = "LMABCDEFGHILMNOP"
        placed = {(3, 5, "ABC"): {"HLA-A"}, (7, 11, "EFGHI"): {"HLA-A"},
                  (4, 5, "XX"): {"HLA-A"}}
        evidence = sorted(placed), placed
        hits, exact = epitope.find_hits(protein[2:8], 3, protein, evidence, {"CD": {"HLA-B"}})
        self.assertTrue(exact)
        self.assertEqual([(hit[0], hit[1], hit[2]) for hit in hits],
                         [("coordinate_verified", "ABC", 3), ("sequence_only", "CD", "")])
        hits, exact = epitope.find_hits("XXXABC", 3, protein, evidence, {})
        self.assertFalse(exact)
        self.assertEqual(hits, [])

    def test_audit_never_transfers_evidence_to_a_different_parent(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            dataset, raw, fasta, output = (root / name for name in ("dataset", "raw", "fasta", "audit"))
            source = {"file": "human/mhc-I/HLA-A/classification.csv", "organism": "human",
                      "mhc_class": "mhc-I", "mhc_family": "HLA-A"}
            (dataset / "rows").mkdir(parents=True)
            (raw / "human/mhc-I/HLA-A").mkdir(parents=True)
            fasta.mkdir()
            (dataset / "config.json").write_text(json.dumps({"sequence_column": "25aa_seq", "sources": [source]}))
            (dataset / "summary.json").write_text(json.dumps({"status": "validated"}))
            sequence = "ACDEFGHIKLMNPQRSTVWYACDEF"
            with (fasta / "human_parent_protein_fasta.csv").open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerows([("protein_url", "fasta"), ("http://p/A-1", ">A\n" + sequence),
                                  ("http://p/A-2", ">B\n" + sequence)])
            (raw / "human/mhc-I/HLA-A/merged_unique_events.csv").write_text(
                "parent_id,epitope__name_canonical,epitope__starting_position,epitope__ending_position\n"
                "http://p/A-1,ACD,1.0,3.0\n"
            )
            pq.write_table(pa.table({
                "25aa_seq": [sequence, sequence], "protein_url": ["http://p/A-1", "http://p/A-2"],
                "protein_group_id": ["1", "2"], "group_id": ["1", "2"],
                "source_row_index": [0, 1], "window_start": ["1", "1"],
                "contains_epitope": [0, 0], "global_contains_epitope": [0, 0],
            }), dataset / "rows/human_mhc-I_HLA-A.parquet")
            epitope.run(dataset, raw, fasta, output, None)
            with (output / "hits.csv").open(newline="") as handle:
                hits = list(csv.DictReader(handle))
            self.assertEqual([(r["protein_url"], r["epitope_start_1based"], r["evidence"]) for r in hits],
                             [("p/A-1", "1", "coordinate_verified")])

    def test_sequence_only_reports_multiple_possible_positions(self):
        hits, _ = epitope.find_hits("AAAA", 0, None, None, {"AA": {"HLA-A"}})
        self.assertEqual([hit[4] for hit in hits], [0, 1, 2])
        self.assertTrue(all(hit[0] == "sequence_only" for hit in hits))


class ExactEmbeddingAuditTests(unittest.TestCase):
    def test_hash_collisions_do_not_merge_different_vectors(self):
        vectors = np.array([[1, 2], [1, 2.000001], [1, 2]], dtype=np.float32)
        subjects = [(b"forced collision", i) for i in range(3)]
        self.assertEqual(list(embedding.verified_representatives(subjects, vectors, slice(None))),
                         [(0, 0), (1, 1), (2, 0)])
        self.assertEqual(embedding.vector_digest(np.array([-0.])), embedding.vector_digest(np.array([0.])))
        with self.assertRaisesRegex(ValueError, "Nonfinite"):
            embedding.vector_digest(np.array([np.nan]))

    def test_proposed_mapping_ignores_group_id_and_preserves_different_global_labels(self):
        with TemporaryDirectory() as folder:
            output = Path(folder)
            db = sqlite3.connect(":memory:")
            self.addCleanup(db.close)
            db.execute("""CREATE TABLE obs (
                id INTEGER PRIMARY KEY, sid INTEGER,gid INTEGER,protein INTEGER,source_row INTEGER,
                seq TEXT,global_label INTEGER,chunk INTEGER,slot INTEGER,p INTEGER,s INTEGER)""")
            rows = [
                (0, 0, 1, 1, 0, "AAA", 1, 0, 0, 0, 0),
                (1, 1, 4, 9, 3, "AAA", 1, 0, 78, 0, 0),
                (2, 0, 2, 1, 1, "AAA", 1, 0, 26, 0, 2),
                (3, 1, 5, 2, 4, "BBB", 0, 0, 104, 0, 0),
            ]
            db.executemany("INSERT INTO obs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
            summary = embedding.summarize(db, output)
            self.assertEqual(summary["removable_rows"], 1)
            self.assertEqual(summary["remaining_rows"], 3)
            self.assertEqual(summary["embedding_pairs_with_different_global_labels"], 1)
            self.assertEqual(summary["primary_all_equal"], 1)
            self.assertEqual(summary["both_any_equal_pair"], 1)
            self.assertEqual(summary["both_all_equal"], 0)
            self.assertEqual(summary["multiple_representations"], 1)
            mapping = pq.read_table(output / "proposed_provenance.parquet").to_pylist()
            self.assertEqual(len(mapping), 4)
            self.assertEqual(next(row for row in mapping if row["source_group_id"] == 4)
                             ["representative_source_dataset_id"], 0)

    def test_shuffle_comparison_reports_modalities_and_checks_source_address(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = {"HLA-A": {"id": 0, "group_id_offset": 10}}
            db = sqlite3.connect(":memory:")
            self.addCleanup(db.close)
            db.execute("""CREATE TABLE obs (id INTEGER PRIMARY KEY,sid INTEGER,gid INTEGER,
                          chunk INTEGER,slot INTEGER,protein INTEGER,original_label INTEGER)""")
            db.executemany("INSERT INTO obs VALUES (?,?,?,?,?,?,?)",
                           [(0, 0, 1, 0, 0, 5, 0), (1, 0, 2, 0, 26, 6, 1)])
            observed = np.zeros((2, embedding.WIDTH), dtype=np.float32)
            shuffled = observed.copy()
            shuffled[0, 4] = 1
            shuffled[1, 1024] = 1
            np.save(root / "chunk_000000_X.npy", shuffled)
            frame = pd.DataFrame([
                (0, 0, 0, 0, 0, 1, 11, 5, 0), (0, 1, 0, 0, 26, 2, 12, 6, 1),
            ], columns=embedding.SHUFFLE_COLUMNS)
            summary = embedding.compare_shuffle(db, observed, [(0, frame)], root, source, True)
            self.assertEqual(summary["compared"], 2)
            self.assertEqual(summary["primary_different"], 1)
            self.assertEqual(summary["secondary_different"], 1)
            db.execute("DROP TABLE seen")
            db.execute("DROP INDEX source_address")
            frame.loc[0, "protein_group_id"] = 9
            with self.assertRaisesRegex(ValueError, "provenance"):
                embedding.compare_shuffle(db, observed, [(0, frame)], root, source, True)

    def test_original_index_filters_blosum_variants(self):
        with TemporaryDirectory() as folder:
            index = Path(folder) / "shuffled.csv"
            frame = pd.DataFrame([
                (0, 0, 0, 0, 1, 1, 1, 3, 0),
                (0, 1, 0, 0, 0, 1, 1, 3, 0),
                (0, 2, 0, 1, 2, 2, 2, 3, 1),
            ], columns=embedding.SHUFFLE_COLUMNS)
            frame.to_csv(index, index=False)
            chunks = list(embedding.shuffled_frames(index, 24, None))
            self.assertEqual(chunks[0][1].row_idx_in_chunk.tolist(), [1, 2])


if __name__ == "__main__":
    unittest.main()
