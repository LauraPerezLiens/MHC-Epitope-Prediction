import sqlite3
import unittest

from data_pipeline.scripts.iedb_modified_audit.audit import classify, key
from data_pipeline.scripts.iedb_modified_audit.impact import duplicates


class ModifiedAuditTests(unittest.TestCase):
    def test_plus_is_not_a_chemical_annotation(self):
        self.assertEqual(classify({"modification":"","corrected_sequence":""}),"uncertain")
        self.assertEqual(classify({"modification":"Oxidation","corrected_sequence":"ACDEF"}),"modified")
        self.assertEqual(classify({"modification":"","corrected_sequence":"ACDEF"}),"simple")

    def test_key_preserves_reference_version_and_position(self):
        a=key("HLA-A","ACDEF","https://x/P.1","http://x/Q-2",1,5)
        self.assertEqual(a,key("HLA-A","ACDEF","http://x/P.1","https://x/Q-2",1,5))
        self.assertNotEqual(a,key("HLA-A","ACDEF","http://x/P.2","https://x/Q-2",1,5))
        self.assertNotEqual(a,key("HLA-A","ACDEF","http://x/P.1","https://x/Q-2",2,6))

    def test_mixed_distinct_entities_are_separate_from_repeated_assays(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE records(family,old_id,eid,assay,chemistry,src,par,a,b)")
            db.execute("CREATE INDEX rec_event ON records(family,old_id)")
            db.execute("CREATE INDEX rec_eid ON records(eid)")
            db.executemany("INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)",[
                ("F","legacy","1","a","simple","A","B",1,5),
                ("F","legacy","1","b","simple","A","B",1,5),
                ("F","legacy","2","c","modified","A","B",1,5),
                ("F","second","2","d","modified","A","B",2,6),
            ])
            numbers=duplicates(db)
        self.assertEqual(numbers["multiple_assays_same_entity"]["records"],2)
        self.assertEqual(numbers["mixed_simple_and_modified_different_entities"]["records"],3)
        self.assertEqual(numbers["mixed_simple_and_modified_different_entities"]["family_events"],1)
        self.assertEqual(numbers["same_entity_different_reference_or_coordinate"]["family_events"],2)


if __name__=="__main__":
    unittest.main()
