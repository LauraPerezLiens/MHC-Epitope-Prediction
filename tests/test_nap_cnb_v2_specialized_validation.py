"""Small on-disk fixtures for the bounded embedding and structure readers."""
from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from data_pipeline import nap_cnb_v2 as cli
from tests import test_nap_cnb_v2_validation as fixtures


@unittest.skipIf(fixtures.pq is None, "PyArrow is unavailable")
class SpecializedValidationTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ValidationTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.write = self.fixture.root, self.fixture.write
        self.footer = self.fixture.footer
        self.audit = Path("results/nap_cnb_v2_embedding_audit")

    def outcome(self, command, expected):
        result, checks = cli.validate(self.root, f"validate-{command}")
        self.assertEqual(result, expected, checks)
        return checks[0].get("details")

    def sqlite(self, path, script):
        with closing(sqlite3.connect(self.root / path)) as db:
            db.executescript(script)

    def npy(self, rows=3, dimension=2):
        header = repr({"descr": "<f4", "fortran_order": False, "shape": (rows, dimension)}).encode()
        header += b" " * (-(10 + len(header) + 1) % 64) + b"\n"
        (self.root / cli.PRIMARY / "shard-0000.npy").write_bytes(
            b"\x93NUMPY\x01\x00" + len(header).to_bytes(2, "little") + header + b"\0" * rows * dimension * 4)

    def primary(self):
        inventory = self.audit / "inventory with #.parquet"
        self.footer(inventory, ("sequence status", {"windows": "int32", "historical_rows": "int32",
                                                   "historical_original": "bool"}), 3)
        self.write(cli.PRIMARY / "manifest.json", {
            "sample_ordinals": None, "selection_sha256": self.fixture.sha(cli.SELECTION),
            "inventory": str(inventory), "inventory_sha256": self.fixture.sha(inventory),
            "dimension": 2, "shard_rows": 3, "batch_size": 2, "revision": "fixture",
            "stable_id": "exact original sequence", "storage": "little-endian float32 NPY shards",
        })
        self.write(cli.PRIMARY.parent / "inventory_validation.json", {"unique": 3})
        self.write(cli.PRIMARY.parent / "final_report.md", "**Estado validado.** Se confirmaron **3 embeddings**\n"
                   "| Shards | 1 |\n| Lotes SQLite confirmados | 2 |")
        self.npy()
        self.sqlite(cli.PRIMARY / "progress.sqlite", """
          CREATE TABLE batches(shard INTEGER,start INTEGER,rows INTEGER,digest TEXT,
                               token_s REAL,forward_s REAL,write_s REAL, PRIMARY KEY (shard,start));
          INSERT INTO batches VALUES (0,0,2,printf('%064d',0),0,0,0),(0,2,1,printf('%064d',0),0,0,0);
        """)
        return inventory

    def secondary(self, create_embedding=True):
        path = "historical/chunks/block.npy"
        for suffix in (".zst", ".archive.json"):
            self.write(path + suffix, "not accessed")
        fingerprint = "a" * 64
        self.write(cli.SECONDARY / "pilot.json", {
            "shape": [1, 2], "n": 1, "dtype": "float32", "finite": True, "config": {"fingerprint": fingerprint}
        })
        index = cli.SECONDARY / "index.sqlite"
        self.sqlite(index, """
          CREATE TABLE shard(id INTEGER PRIMARY KEY,path TEXT);
          INSERT INTO shard VALUES (1,'historical/chunks/block.npy');
          CREATE TABLE inventory(structure TEXT PRIMARY KEY, sha256 BLOB, length INTEGER,
                                 windows INTEGER, shard INTEGER, row_offset INTEGER) WITHOUT ROWID;
          CREATE TABLE embedding(structure TEXT PRIMARY KEY, vector BLOB, checksum BLOB) WITHOUT ROWID;
        """)
        if create_embedding:
            self.sqlite(index, """
              INSERT INTO inventory VALUES ('CCCCCCCCCCCCCCCCCCCCCCCCC',x'00',25,1,NULL,NULL);
              INSERT INTO embedding VALUES ('CCCCCCCCCCCCCCCCCCCCCCCCC',x'0000',x'00');
            """)
        report = cli.SECONDARY / "secondarybert_report.md"
        self.write(report, f"Fase 3C cerrada y validada. **2 estructuras C/H/E exactas**.\n"
                   f"{fingerprint} · 2 valores float32. integridad en 1 bloques canónicos\n"
                   "| Históricas verificadas y accesibles por referencia | 1 | 1 |\n"
                   "| Generadas y verificadas en el piloto | 1 | 1 |\n"
                   "| Generadas en la ejecución completa | 0 | 0 |\n"
                   "| Pendientes de generación | 0 | 0 |\n"
                   f"| SQLite final | {(self.root / index).stat().st_size} bytes |")
        for name in ("verified_secondarybert_frequencies.parquet", "missing_secondarybert_structures.parquet"):
            self.footer(self.audit / name, ("secondary_structure", {}), 1)
        return Path(path + ".zst"), index, report

    def structures(self):
        path = cli.SELECTION.parent
        overlay, excluded = path / "overlay.parquet", path / "exclusions.parquet"
        self.footer(overlay, ("window_id parent_url parent_sha256 secondary_structure structure_prediction_id "
                              "verification_method validation_status", {}), 4)
        self.footer(excluded, ("window_id parent_sha256 invalid_residues", {"window_start": "int64"}), 2)
        for name in ("prediction_sources.tsv", "proteins.tsv", "pending_proteins.tsv", "predictions.csv"):
            self.write(path / name, "fixture")
        metrics = {
            "matched_before": 8, "matched_after": 12, "binary_windows": 14, "remaining_windows": 2,
            "window_counts": {"recovered": 4},
            "artifact_bytes": {name: (self.root / path / name).stat().st_size
                               for name in ("overlay.parquet", "prediction_sources.tsv", "proteins.tsv")},
            "sources": [{"path": str(path / "predictions.csv"), "sha256": self.fixture.sha(path / "predictions.csv")}],
        }
        self.write(path / "metrics.json", metrics)
        spec = self.fixture.selection
        spec["supplement_sha256"] = {name.name: self.fixture.sha(name) for name in (overlay, excluded)}
        self.write(cli.SELECTION, spec)
        return overlay, excluded, metrics

    def test_prott5_read_only_and_sqlite_sidecar(self):
        self.primary()
        before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in self.root.rglob("*")}
        actual = sqlite3.connect

        def checked(database, **kwargs):
            self.assertIn("?mode=ro&immutable=1", database)
            self.assertTrue(kwargs["uri"])
            db = actual(database, **kwargs)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("CREATE TABLE write_attempt(x)")
            return db

        with patch.object(sqlite3, "connect", side_effect=checked):
            self.assertEqual(self.outcome("prott5", "PASS")["sqlite_receipts"], 2)
        self.assertEqual(before, {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in self.root.rglob("*")})
        self.write(cli.PRIMARY / "progress.sqlite-wal", "in flight")
        with patch.object(sqlite3, "connect", side_effect=AssertionError("Opened live catalog")):
            self.outcome("prott5", "INCOMPLETE")

    def test_prott5_missing_and_invalid_shards_and_manifest(self):
        self.primary()
        shard = self.root / cli.PRIMARY / "shard-0000.npy"
        shard.unlink()
        self.outcome("prott5", "FAIL")
        shard.write_bytes(b"Invalid")
        self.outcome("prott5", "FAIL")
        for rows, dimension in ((3, 4), (2, 2)):
            self.npy(rows, dimension)
            self.outcome("prott5", "FAIL")
        (self.root / cli.PRIMARY / "manifest.json").unlink()
        self.outcome("prott5", "FAIL")

    def test_prott5_receipt_coverage_does_not_rehash_vectors(self):
        self.primary()
        shard = self.root / cli.PRIMARY / "shard-0000.npy"
        original = shard.read_bytes()
        shard.write_bytes(original[:-8] + b"\0\0\x80\x3f" * 2)
        self.assertEqual(self.outcome("prott5", "PASS")["sqlite_receipts"], 2)
        self.sqlite(cli.PRIMARY / "progress.sqlite", "DELETE FROM batches WHERE start=2;")
        self.outcome("prott5", "FAIL")

    def test_prott5_invalid_inventory_schema(self):
        inventory = self.primary()
        self.footer(inventory, ("not_sequence", {}), 3)
        self.outcome("prott5", "FAIL")

    def test_secondarybert_canonical_references_and_index_version(self):
        archive, index, _ = self.secondary()
        result = self.outcome("secondarybert", "PASS")
        self.assertEqual((result["declared_historical_keys"], result["declared_new_keys"]), (1, 1))
        (self.root / archive).unlink()
        self.outcome("secondarybert", "FAIL")
        self.write(archive, "restored")
        self.sqlite(index, "PRAGMA user_version=1;")
        self.outcome("secondarybert", "FAIL")
        (self.root / index).unlink()
        self.outcome("secondarybert", "FAIL")

    def test_secondarybert_dimension_counts_and_new_reference(self):
        _, index, _ = self.secondary(create_embedding=False)
        self.outcome("secondarybert", "FAIL")
        (self.root / index).unlink()
        _, _, report = self.secondary()
        self.outcome("secondarybert", "PASS")
        template = (self.root / report).read_text()
        for old, new in (("2 valores", "3 valores"), ("**2 estructuras", "**3 estructuras")):
            self.write(report, template.replace(old, new))
            self.outcome("secondarybert", "FAIL")

    def test_structures_references_and_counts(self):
        overlay, excluded, metrics = self.structures()
        self.assertEqual(self.outcome("structures", "PASS")["overlay"]["footer_rows"], 4)
        self.write(overlay.parent / "metrics.json", {**metrics, "remaining_windows": 3})
        self.outcome("structures", "FAIL")
        self.write(overlay.parent / "metrics.json", metrics)
        self.write(overlay.parent / "metrics.json", {**metrics, "sources": [
            {**metrics["sources"][0], "path": "missing.csv"}]})
        self.outcome("structures", "FAIL")
        self.write(overlay.parent / "metrics.json", metrics)
        (self.root / overlay.parent / "report.md").unlink()
        self.outcome("structures", "INCOMPLETE")
        self.write(overlay.parent / "report.md", "Base validada")
        for path in (excluded, overlay):
            with self.subTest(path=path):
                original = (self.root / path).read_bytes()
                (self.root / path).unlink()
                self.outcome("structures", "FAIL")
                (self.root / path).write_bytes(original)
