
import json
import tempfile
import unittest
from pathlib import Path

from agent.tools import LabInvestigationTools
from storage.db import initialize_db
from storage.repository import create_case, get_case


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads(
    (ROOT / "fixtures/demo_case.json").read_text()
)
LAB_SOURCE = ROOT / "fixtures/lab_inbox.json"


class TestInvestigationTools(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "clinic.db"

        initialize_db(self.db_path)
        create_case(self.db_path, DATA)

        self.tools = LabInvestigationTools(
            self.db_path,
            "CASE-001",
            LAB_SOURCE,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_finds_pending_third_order(self):
        result = self.tools.get_pending_orders()

        self.assertEqual(
            [x["order_id"] for x in result["pending_orders"]],
            ["T-03"],
        )

    def test_candidate_exposes_linked_message(self):
        result = self.tools.search_lab_records("T-03")

        candidates = {
            item["source_id"]: item
            for item in result["candidates"]
        }

        self.assertEqual(
            candidates["LABREC-101"]["message_ids"],
            ["MSG-101"],
        )

        self.assertNotIn("LABREC-102", candidates)

    def test_ambiguous_candidates_never_autolink(self):
        result = self.tools.search_lab_records("T-03")

        self.assertEqual(len(result["candidates"]), 1)
        self.assertFalse(result["automatically_attached"])

        self.assertTrue(all(
            item["requires_staff_verification"]
            for item in result["candidates"]
        ))

    def test_received_order_cannot_be_reinvestigated(self):
        with self.assertRaises(ValueError):
            self.tools.search_lab_records("T-02")

    def test_message_has_source_reference(self):
        message = self.tools.inspect_lab_message("MSG-101")

        self.assertEqual(message["source_id"], "MSG-101")
        self.assertTrue(message["untrusted_external_text"])

    def test_other_case_message_is_inaccessible(self):
        with self.assertRaises(KeyError):
            self.tools.inspect_lab_message("MSG-102")

    def test_clarification_does_not_modify_case(self):
        before = get_case(self.db_path, "CASE-001")

        draft = self.tools.draft_staff_clarification(
            "T-03", "LABREC-101"
        )

        after = get_case(self.db_path, "CASE-001")

        self.assertEqual(before, after)
        self.assertEqual(
            draft["status"], "NEEDS_STAFF_REVIEW"
        )
        self.assertFalse(draft["executed"])

    def test_other_patient_candidate_is_withheld(self):
        result = self.tools.search_lab_records("T-03")

        candidate_ids = [
            item["source_id"]
            for item in result["candidates"]
        ]

        self.assertEqual(candidate_ids, ["LABREC-101"])
        self.assertEqual(
            result["withheld_patient_mismatch_count"], 1
        )

        with self.assertRaises(ValueError):
            self.tools.draft_staff_clarification(
                "T-03", "LABREC-102"
            )


    def test_other_patient_message_is_blocked(self):
        self.tools.source["messages"].append({
            "message_id": "MSG-WRONG-PATIENT",
            "case_id": "CASE-001",
            "record_id": "LABREC-102",
            "body": "This must not be disclosed.",
        })

        with self.assertRaises(KeyError):
            self.tools.inspect_lab_message(
                "MSG-WRONG-PATIENT"
            )

    def test_no_candidate_creates_staff_escalation(self):
        self.tools.source["records"] = [
            record
            for record in self.tools.source["records"]
            if record["record_id"] == "LABREC-102"
        ]

        before = get_case(self.db_path, "CASE-001")

        draft = self.tools.draft_missing_report_escalation(
           "T-03"
        )

        self.assertEqual(
            draft["action"],
            "REQUEST_MISSING_REPORT_STATUS",
        )
        self.assertEqual(draft["evidence_source_ids"], [])
        self.assertFalse(draft["executed"])
        self.assertEqual(
            before, get_case(self.db_path, "CASE-001")
        )


    def test_missing_report_escalation_rejects_visible_candidate(self):
        with self.assertRaises(ValueError):
            self.tools.draft_missing_report_escalation(
                "T-03"
            )


if __name__ == "__main__":
    unittest.main()
