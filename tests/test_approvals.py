import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.followup import build_patient_status
from storage.approvals import (
    ApprovalConflict,
    ApprovalForbidden,
    ApprovalNotReady,
    approve_followup,
    get_current_approval,
    initialize_approval_schema,
    seed_demo_actor,
)
from storage.db import connect_db, initialize_db
from storage.repository import (
    StaleCaseVersion,
    create_case,
    get_case,
    ingest_report,
)


class TestClinicianApprovals(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"

        initialize_db(self.path)
        initialize_approval_schema(self.path)

        self.case = {
            "fictional": True,
            "case_id": "CASE-001",
            "patient_id": "PAT-001",
            "orders": [
                {
                    "order_id": f"T-0{i}",
                    "patient_id": "PAT-001",
                    "test_code": f"LAB-{letter}",
                }
                for i, letter in enumerate("ABC", 1)
            ],
            "reports": [
                {
                    "report_id": f"R-0{i}",
                    "order_id": f"T-0{i}",
                    "patient_id": "PAT-001",
                    "test_code": f"LAB-{letter}",
                }
                for i, letter in enumerate("AB", 1)
            ],
        }

        create_case(self.path, self.case)
        seed_demo_actor(self.path, "DOC-01", "clinician")
        seed_demo_actor(self.path, "STAFF-01", "coordinator")

        self.third = {
            "report_id": "R-03",
            "order_id": "T-03",
            "patient_id": "PAT-001",
            "test_code": "LAB-C",
        }

    def tearDown(self):
        self.temp.cleanup()

    def complete_reports(self):
        ingest_report(
            self.path,
            "CASE-001",
            self.third,
            expected_version=1,
        )

    def approve(self, **overrides):
        arguments = {
            "clinician_id": "DOC-01",
            "expected_version": 2,
            "instructions":
                "Please contact the clinic to arrange follow-up.",
        }
        arguments.update(overrides)

        return approve_followup(
            self.path,
            "CASE-001",
            **arguments,
        )

    def test_missing_report_blocks_approval(self):
        with self.assertRaises(ApprovalNotReady):
            self.approve(expected_version=1)

        self.assertIsNone(
            get_current_approval(self.path, "CASE-001")
        )

    def test_coordinator_cannot_approve(self):
        self.complete_reports()

        with self.assertRaises(ApprovalForbidden):
            self.approve(clinician_id="STAFF-01")

    def test_unknown_actor_cannot_approve(self):
        self.complete_reports()

        with self.assertRaises(ApprovalForbidden):
            self.approve(clinician_id="UNKNOWN")

    def test_approval_persists_and_matches_version(self):
        self.complete_reports()
        result = self.approve()

        approval = get_current_approval(
            self.path,
            "CASE-001",
        )

        self.assertEqual(result["outcome"], "approved")
        self.assertEqual(approval["case_version"], 2)
        self.assertEqual(approval["decision"], "approved")

    def test_patient_view_uses_persisted_approval(self):
        self.complete_reports()
        self.approve()

        case = get_case(self.path, "CASE-001")
        approval = get_current_approval(
            self.path,
            "CASE-001",
        )

        view = build_patient_status(
            case,
            approval=approval,
        )

        self.assertEqual(
            view["state"],
            "APPROVED_FOR_COMMUNICATION",
        )
        self.assertNotIn("instructions", view)

    def test_duplicate_approval_is_idempotent(self):
        self.complete_reports()
        self.approve()
        repeated = self.approve()

        self.assertEqual(repeated["outcome"], "duplicate")

        with connect_db(self.path) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM clinician_approvals"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_conflicting_approval_is_rejected(self):
        self.complete_reports()
        self.approve()

        with self.assertRaises(ApprovalConflict):
            self.approve(
                instructions="Different clinician instructions"
            )

    def test_new_report_invalidates_approval(self):
        self.complete_reports()
        self.approve()

        ingest_report(
            self.path,
            "CASE-001",
            {
                "report_id": "R-04",
                "order_id": "T-03",
                "patient_id": "PAT-001",
                "test_code": "LAB-C",
            },
            expected_version=2,
        )

        self.assertIsNone(
            get_current_approval(self.path, "CASE-001")
        )

    def test_stale_approval_is_rejected(self):
        self.complete_reports()

        with self.assertRaises(StaleCaseVersion):
            self.approve(expected_version=1)

    def test_approval_ledger_is_append_only(self):
        self.complete_reports()
        self.approve()

        with self.assertRaises(sqlite3.IntegrityError):
            with connect_db(self.path) as db:
                db.execute(
                    "UPDATE clinician_approvals "
                    "SET instructions = 'modified'"
                )

        with self.assertRaises(sqlite3.IntegrityError):
            with connect_db(self.path) as db:
                db.execute(
                    "DELETE FROM clinician_approvals"
                )

    def test_empty_order_set_cannot_be_approved(self):
        create_case(
            self.path,
            {
                "fictional": True,
                "case_id": "CASE-EMPTY",
                "patient_id": "PAT-002",
                "orders": [],
                "reports": [],
            },
        )

        with self.assertRaises(ApprovalNotReady):
            approve_followup(
                self.path,
                "CASE-EMPTY",
                clinician_id="DOC-01",
                expected_version=1,
                instructions="Please contact the clinic.",
            )


if __name__ == "__main__":
    unittest.main()
