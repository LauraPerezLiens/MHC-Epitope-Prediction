import unittest

from data_pipeline.scripts.iedb_pending_audit.audit import event_key, verify_group
from data_pipeline.scripts.rebuild_iedb.rebuild import Reference


class PendingEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.peptide = "ACDEFGHIK"
        self.target = "LMNPQRST" + self.peptide + "VWYLMNPQRST"
        self.row = {
            "family":"HLA-A", "old_event_id":"legacy", "original_sequence":self.peptide,
            "start":"1", "end":"9", "source_iri":"http://db/SRC001.1", "parent_iri":"http://db/PARENT",
            "epitope_iri":"http://www.iedb.org/epitope/17", "assay_iri":"http://www.iedb.org/assay/83",
            "original_name":self.peptide+" + ACET(A1)", "corrected_sequence":"", "modification":"Acetylation",
        }
        self.parent = Reference("PARENT","2",self.target,"archived_parent_fasta","")
        self.archive={("human","db/PARENT"):self.parent}
        self.reference={"SRC001.1": self.peptide+"LMNPQRSTVWY"}
        self.records={"17":{"structure_id":17,"linear_sequence":self.peptide,
                            "curated_source_antigens":[{"iri":"UNIPROT:PARENT.2","accession":"PARENT.2",
                                                        "starting_position":9,"ending_position":17}]}}

    def verify(self, row=None):
        row = row or self.row
        return verify_group(row,[row],self.records,{},self.archive,self.reference,None)

    def test_modified_evidence_retains_validated_parent_and_does_not_become_plain(self):
        result=self.verify()
        self.assertEqual(result["state"],"modified_backbone_and_parent_verified")
        self.assertTrue(result["corrected"])
        self.assertTrue(result["evidence"][0]["source_exact"])
        self.assertFalse(result["evidence"][0]["plain"])
        self.assertEqual(result["evidence"][0]["parent_start"],9)

    def test_exact_backbone_alone_does_not_transfer_from_unavailable_source(self):
        self.records["17"]["curated_source_antigens"]=[]
        self.reference={}
        result=self.verify()
        self.assertEqual(result["state"],"requires_reference_or_backbone")
        self.assertEqual(result["evidence"],[])
        self.assertEqual(result["structure_observations"][0]["linear_sequence"],self.peptide)

    def test_absent_parent_is_incompatible(self):
        self.archive={("human","db/PARENT"):Reference("PARENT","2","L"*28,"archived_parent_fasta","")}
        result=self.verify()
        self.assertEqual(result["state"],"incompatible_parent_reference")
        self.assertFalse(result["corrected"])

    def test_event_keys_scope_family_and_preserve_versions(self):
        original=event_key(self.row)
        self.assertEqual(event_key(dict(self.row,source_iri="https://db/SRC001.1")),original)
        self.assertNotEqual(event_key(dict(self.row,source_iri="https://db/SRC001.2")),original)
        self.assertNotEqual(event_key(dict(self.row,family="HLA-B")),original)


if __name__=="__main__":
    unittest.main()
