
"""Staff evidence-review tests using fictional records."""

import json
import tempfile
import unittest
from pathlib import Path

from api.demo_state import prepare_demo_db
from api.staff_review import build_staff_review_packet
from storage.repository import get_case, ingest_report


class TestStaffReview(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "clinic.db"
        prepare_demo_db(self.db_path)

    def tearDown(self):
        self.temp.cleanup()

    def test_review_finds_unresolved_reference(self):
        packet = build_staff_review_packet(self.db_path)

        self.assertEqual(packet["case_version"], 1)
        self.assertEqual(len(packet["pending_orders"]), 1)

        order = packet["pending_orders"][0]

        self.assertEqual(order["order_id"], "T-03")
        self.assertEqual(
            [x["source_id"] for x in order["candidates"]],
            ["LABREC-101"],
        )
        self.assertEqual(
            order["candidates"][0]["messages"][0]["source_id"],
            "MSG-101",
        )

    def test_review_is_read_only_and_withholds_other_patient(self):
        before = get_case(self.db_path, "CASE-001")

        packet = build_staff_review_packet(self.db_path)

        after = get_case(self.db_path, "CASE-001")
        encoded = json.dumps(packet)

        self.assertEqual(before, after)
        self.assertTrue(packet["read_only"])
        self.assertNotIn("LABREC-102", encoded)
        self.assertNotIn("PAT-999", encoded)

    def test_review_updates_after_report_ingestion(self):
        ingest_report(
            self.db_path,
            "CASE-001",
            {
                "report_id": "R-03",
                "order_id": "T-03",
                "patient_id": "PAT-001",
                "test_code": "LAB-C",
                "source_text": "Fictional report C",
            },
            expected_version=1,
        )

        packet = build_staff_review_packet(self.db_path)

        self.assertEqual(packet["case_version"], 2)
        self.assertEqual(packet["pending_orders"], [])
        self.assertEqual(
            packet["status"], "NO_PENDING_ORDERS",
        )


if __name__ == "__main__":
    unittest.main()
