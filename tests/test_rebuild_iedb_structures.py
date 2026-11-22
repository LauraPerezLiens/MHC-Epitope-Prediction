import csv
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pyarrow.parquet as pq

from data_pipeline.scripts.rebuild_iedb import rebuild
from tests.test_rebuild_iedb import FAMILY, PARENT, SEQUENCE, LocalRegistry, event


class StructureTest(unittest.TestCase):
    def test_archived_structure_is_sliced_and_reconciled(self):
        ss = ("CHE" * len(SEQUENCE))[:len(SEQUENCE)]
        with TemporaryDirectory() as scratch:
            output = Path(scratch)
            (output / "raw").mkdir()
            (output / "checkpoints").mkdir()
            with gzip.open(output / "raw" / f"{FAMILY}_test.jsonl.gz", "wt") as handle:
                handle.write(json.dumps(event(1, "PEPTIDE", 11, 17)) + "\n")
            predictions = output / "archive.csv"
            with predictions.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("protein_url", "sequence", "secondary_structure"))
                writer.writerow((PARENT, SEQUENCE, ss))
                writer.writerow((PARENT, "T" + SEQUENCE, "C" + ss))
                writer.writerow(("example.org/other", SEQUENCE, "C" * len(SEQUENCE)))
                writer.writerow(("example.org/other", SEQUENCE, "H" * len(SEQUENCE)))
            structures = rebuild.StructureArchive({"human": predictions})
            self.assertEqual(structures.resolve("human", "example.org/other", SEQUENCE, True)[0], "ambiguous_prediction")
            self.assertEqual(structures.resolve("human", PARENT, "A" * len(SEQUENCE), True)[0], "protein_sequence_mismatch")
            self.assertEqual(structures.resolve("human", PARENT, SEQUENCE, False)[0], "unverified_archived_reference")
            self.assertEqual(structures.resolve("mouse", PARENT, SEQUENCE, True)[0], "missing_prediction")
            rebuild.build_family(output, FAMILY, LocalRegistry(), structures)
            counts = rebuild.reconcile_family(output, FAMILY, structures)
            self.assertEqual(counts["structural_windows_matched"], len(SEQUENCE) - 24)
            window = pq.read_table(output / "families" / f"{FAMILY}.parquet").to_pylist()[10]
            self.assertEqual(window["secondary_structure"], ss[10:35])
            self.assertEqual(window["contains_epitope"], 1)
            total = rebuild.global_counts(output, [FAMILY], structural=True)
            self.assertEqual(total["unique_primary_secondary_pairs"], len({
                (SEQUENCE[i:i+25], ss[i:i+25]) for i in range(len(SEQUENCE) - 24)
            }))


if __name__ == "__main__":
    unittest.main()
