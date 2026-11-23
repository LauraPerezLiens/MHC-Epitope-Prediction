import io
from pathlib import Path
import shutil
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data_pipeline.scripts.iedb_download_audit import audit as replay

from data_pipeline.scripts.iedb_download_audit.audit import compare_record, conditions, windows
from data_pipeline.scripts.iedb_download_audit.live import check_pages


class IedbDownloadAuditTests(unittest.TestCase):
    def event(self, **values):
        return {
            "epitope__name": "ACDEFGHIK",
            "epitope__starting_position": "2",
            "epitope__ending_position": "10",
            "epitope__source_molecule_iri": "https://db/P1.2",
            "epitope__molecule_parent_iri": "http://db/P1",
            "assay_id__iedb_iri": "http://www.iedb.org/assay/1",
            "epitope__epitope_iri": "http://www.iedb.org/epitope/2",
            **values,
        }

    def test_plain_sequence_preserves_a_versioned_source_and_parent(self):
        old, new, change, reasons, seq, _, _, assay = compare_record(self.event())
        self.assertEqual(change, "unchanged")
        self.assertEqual(new[:5], old)
        self.assertEqual(new[3:5], ("https://db/P1.2", "http://db/P1"))
        self.assertEqual(seq, "ACDEFGHIK")
        self.assertFalse(reasons)
        self.assertTrue(assay.endswith("/1"))

    def test_missing_coordinates_are_retained_and_ambiguous_names_are_not_truncated(self):
        old, new, change, reasons, *_ = compare_record(self.event(epitope__ending_position=""))
        self.assertIsNone(old)
        self.assertEqual(change, "added")
        self.assertIn("missing_coordinates", reasons)
        self.assertEqual(new[-1], "http://www.iedb.org/epitope/2")
        old, _, change, reasons, seq, legacy, *_ = compare_record(
            self.event(epitope__name="N-acetyl ACDEFGHIK")
        )
        self.assertEqual(old[0], legacy)
        self.assertEqual(legacy, "N")
        self.assertEqual(change, "modified")
        self.assertEqual(seq, "")
        self.assertIn("sequence_requires_review", reasons)

    def test_alternative_differs_in_a_single_filter(self):
        row = {"host__name": "Homo sapiens (human)", "epitope__source_organism": "Homo sapiens",
               "epitope__object_type": "Linear peptide", "mhc_restriction__class": "II",
               "mhc_restriction__name": "HLA-DQA1*01:01/DQB1*05:01",
               "assay__qualitative_measurement": "Not positive"}
        old, new = conditions(row, "human", "mhc-II", "HLA-DQ")
        self.assertTrue(all(old.values()))
        self.assertEqual([k for k in new if old[k] != new[k]], ["positive"])

    def test_window_bounds_and_truncated_page(self):
        self.assertEqual(list(windows(2, 9, 26)), [1, 2])
        pages = {0: ([{"id": 1}], "0-0/*"), 1: ([{"id": 2}], "1-1/*")}
        rows, manifest = check_pages(lambda offset, size: pages[offset], 2, 10)
        self.assertEqual(rows, [{"id": 1}, {"id": 2}])
        self.assertEqual(manifest, [
            {"offset": 0, "records": 1, "content_range": "0-0/*"},
            {"offset": 1, "records": 1, "content_range": "1-1/*"},
        ])
        with self.assertRaisesRegex(ValueError, "Repeated payload"):
            check_pages(lambda offset, size: ([{"id": 1}], f"{offset}-{offset}/*"), 2, 10)
        with self.assertRaisesRegex(ValueError, "Unexpected pagination"):
            check_pages(lambda offset, size: ([], "*/*"), 1, 10)

    def test_pages_reject_malformed_record_payloads(self):
        for payload in ({"error": "missing records"}, ["not a record"], [None]):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, "JSON records"):
                check_pages(lambda offset, size: (payload, "0-0/1"), 1, 10)


    @unittest.skipUnless(shutil.which("zstd"), "zstd is required")
    def test_archive_validation_and_report_failure_keep_destination_unpublished(self):
        family = ("human", "mhc-I", "fixture")
        member = "data_raw/human/mhc-I/fixture/mhc_export_full.csv"
        merged = "data_raw/human/mhc-I/fixture/merged_unique_events.csv"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "fixture.tar.zst"
            source = root / "fixture.tar"
            for org in ("human", "mouse"):
                (root / f"{org}_parent_protein_fasta.csv").write_text("id_full,resolved_id,protein_url,fasta\n")
            for case in ("missing", "write failure", "success", "existing"):
                with self.subTest(case=case):
                    output = root / ("success" if case == "existing" else case)
                    with tarfile.open(source, "w") as tar:
                        contents = {merged: b"epitope__name_canonical,epitope__starting_position,epitope__ending_position,source_id,parent_id\n"}
                        if case != "missing":
                            contents[member] = b"epitope__name\n"
                        for name, data in contents.items():
                            info = tarfile.TarInfo(name)
                            info.size = len(data)
                            tar.addfile(info, io.BytesIO(data))
                    subprocess.run(["zstd", "-qf", str(source), "-o", str(archive)], check=True)
                    with patch.object(replay, "MEMBERS", {member: (*family, "mhc")}), patch.object(replay, "FAMILIES", [family]):
                        if case == "missing":
                            with self.assertRaisesRegex(ValueError, "Missing archive members"):
                                replay.audit(archive, output, root)
                        elif case == "write failure":
                            with patch.object(replay, "write_json", side_effect=OSError("fixture write failure")):
                                with self.assertRaisesRegex(OSError, "fixture write failure"):
                                    replay.audit(archive, output, root)
                        elif case == "success":
                            replay.audit(archive, output, root)
                            previous = (output / "summary.json").read_bytes()
                        else:
                            with self.assertRaises(FileExistsError):
                                replay.audit(archive, output, root)
                            self.assertEqual((output / "summary.json").read_bytes(), previous)
                    if case in ("missing", "write failure"):
                        self.assertFalse(output.exists())
                        self.assertFalse(list(root.glob(".iedb-audit-*")))


if __name__ == "__main__":
    unittest.main()
