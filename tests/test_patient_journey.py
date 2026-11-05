import tempfile
import unittest
from pathlib import Path

from core.followup import build_patient_status
from services.fake_notification import FakeNotificationGateway
from scripts.demo_patient_journey import run_demo
from storage.approvals import get_current_approval
from storage.repository import get_case, ingest_report


class TestPatientJourney(unittest.TestCase):

    def test_complete_patient_followup(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_demo(directory)

            states = [
                item["state"]
                for item in result["timeline"]
            ]

            self.assertEqual(states, [
                "AWAITING_REPORTS",
                "AWAITING_CLINICIAN_REVIEW",
                "APPROVED_FOR_COMMUNICATION",
                "DELIVERY_UNCONFIRMED",
                "DELIVERED",
            ])

            self.assertEqual(result["case_version"], 2)
            self.assertEqual(
                result["destination_receipts"], 1
            )
            self.assertEqual(
                result["final_delivery_outcome"], "delivered"
            )

    def test_new_evidence_requires_fresh_review(self):
        with tempfile.TemporaryDirectory() as directory:
            run_demo(directory)

            root = Path(directory)
            clinic_db = root / "clinic.db"
            destination_db = root / "destination.db"

            # A new, conflicting report arrives after the
            # simulated notification was delivered.
            ingest_report(
                clinic_db,
                "CASE-001",
                {
                    "report_id": "R-04",
                    "order_id": "T-03",
                    "patient_id": "PAT-001",
                    "test_code": "LAB-C",
                    "source_text":
                        "Additional fictional conflicting report",
                },
                expected_version=2,
            )

            case = get_case(clinic_db, "CASE-001")

            self.assertEqual(case["version"], 3)
            self.assertIsNone(
                get_current_approval(
                    clinic_db, "CASE-001"
                )
            )

            patient_view = build_patient_status(
                case,
                approval=None,
            )

            self.assertEqual(
                patient_view["state"],
                "STAFF_REVIEW_REQUIRED",
            )

            # Historical delivery remains recorded.
            gateway = FakeNotificationGateway(
                destination_db
            )
            self.assertEqual(
                gateway.delivery_count(), 1
            )


if __name__ == "__main__":
    unittest.main()
