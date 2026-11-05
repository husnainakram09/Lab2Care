import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.reconcile import reconcile_case, approval_is_current
from storage.db import connect_db, initialize_db
from storage.repository import (
    create_case,
    get_case,
    ingest_report,
    ReportConflict,
    StaleCaseVersion,
)


DATA = json.loads(
    (Path(__file__).resolve().parents[1]
     / "fixtures/demo_case.json").read_text()
)


class TestReportIngestion(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "cases.db"
        initialize_db(self.path)
        create_case(self.path, DATA)

        self.third = {
            "report_id": "R-03",
            "order_id": "T-03",
            "patient_id": "PAT-001",
            "test_code": "LAB-C",
            "source_text": "Fictional report C",
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_ingestion_increments_version(self):
        result = ingest_report(
            self.path, "CASE-001", self.third,
            expected_version=1,
        )

        case = get_case(self.path, "CASE-001")

        self.assertEqual(result["outcome"], "ingested")
        self.assertEqual(case["version"], 2)
        self.assertEqual(len(case["reports"]), 3)
        self.assertFalse(approval_is_current(1, 2))

        reconciliation = reconcile_case(
            case["patient_id"],
            case["orders"],
            case["reports"],
        )
        self.assertEqual(reconciliation["missing_order_ids"], [])

    def test_duplicate_delivery_is_idempotent(self):
        ingest_report(
            self.path, "CASE-001", self.third,
            expected_version=1,
        )

        retry = ingest_report(
            self.path, "CASE-001", self.third,
            expected_version=1,
        )

        self.assertEqual(retry["outcome"], "duplicate")
        self.assertEqual(retry["case_version"], 2)

        with connect_db(self.path) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM case_events"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_conflicting_duplicate_is_rejected(self):
        ingest_report(
            self.path, "CASE-001", self.third,
            expected_version=1,
        )

        changed = copy.deepcopy(self.third)
        changed["source_text"] = "Different evidence"

        with self.assertRaises(ReportConflict):
            ingest_report(
                self.path, "CASE-001", changed,
                expected_version=2,
            )

        self.assertEqual(
            get_case(self.path, "CASE-001")["version"], 2
        )

    def test_stale_new_write_is_rejected(self):
        with self.assertRaises(StaleCaseVersion):
            ingest_report(
                self.path, "CASE-001", self.third,
                expected_version=2,
            )

        case = get_case(self.path, "CASE-001")
        self.assertEqual(case["version"], 1)
        self.assertEqual(len(case["reports"]), 2)

    def test_mismatched_evidence_is_preserved(self):
        wrong = copy.deepcopy(self.third)
        wrong["patient_id"] = "PAT-999"

        ingest_report(
            self.path, "CASE-001", wrong,
            expected_version=1,
        )

        case = get_case(self.path, "CASE-001")

        result = reconcile_case(
            case["patient_id"],
            case["orders"],
            case["reports"],
        )

        self.assertEqual(
            result["quarantined"][0]["reason"],
            "patient_mismatch",
        )
        self.assertIn("T-03", result["missing_order_ids"])

    def test_audit_failure_rolls_back_everything(self):
        with connect_db(self.path) as db:
            db.execute("""
                CREATE TRIGGER fail_audit_insert
                BEFORE INSERT ON case_events
                BEGIN
                    SELECT RAISE(
                        ABORT, 'simulated audit failure'
                    );
                END;
            """)

        with self.assertRaises(sqlite3.IntegrityError):
            ingest_report(
                self.path, "CASE-001", self.third,
                expected_version=1,
            )

        case = get_case(self.path, "CASE-001")

        self.assertEqual(case["version"], 1)
        self.assertEqual(len(case["reports"]), 2)


if __name__ == "__main__":
    unittest.main()
