import copy
import json
import unittest
from pathlib import Path

from core.followup import build_patient_status


DATA = json.loads(
    (Path(__file__).resolve().parents[1]
     / "fixtures/demo_case.json").read_text()
)


class TestPatientFollowup(unittest.TestCase):

    def setUp(self):
        self.case = {**copy.deepcopy(DATA), "version": 1}
        self.approval = {
            "case_version": 1,
            "decision": "approved",
        }
        self.delivery = {
            "case_version": 1,
            "status": "delivered",
        }

    def complete_reports(self):
        self.case["reports"].append({
            "report_id": "R-03",
            "order_id": "T-03",
            "patient_id": "PAT-001",
            "test_code": "LAB-C",
        })

    def test_patient_sees_two_of_three_received(self):
        view = build_patient_status(self.case)
        self.assertEqual(view["state"], "AWAITING_REPORTS")
        self.assertEqual(view["received_count"], 2)
        self.assertEqual(view["pending_count"], 1)

    def test_complete_reports_still_require_doctor(self):
        self.complete_reports()
        view = build_patient_status(self.case)
        self.assertEqual(
            view["state"], "AWAITING_CLINICIAN_REVIEW"
        )

    def test_conflicting_report_needs_staff_review(self):
        self.case["reports"].append({
            "report_id": "R-03",
            "order_id": "T-03",
            "patient_id": "PAT-999",
            "test_code": "LAB-C",
        })
        view = build_patient_status(self.case)
        self.assertEqual(
            view["state"], "STAFF_REVIEW_REQUIRED"
        )

    def test_approval_cannot_override_missing_report(self):
        view = build_patient_status(
            self.case,
            approval=self.approval,
            delivery=self.delivery,
        )
        self.assertEqual(view["state"], "AWAITING_REPORTS")

    def test_approved_without_delivery(self):
        self.complete_reports()
        view = build_patient_status(
            self.case,
            approval=self.approval,
        )
        self.assertEqual(
            view["state"], "APPROVED_FOR_COMMUNICATION"
        )

    def test_sent_is_not_delivered(self):
        self.complete_reports()
        view = build_patient_status(
            self.case,
            approval=self.approval,
            delivery={
                "case_version": 1,
                "status": "sent",
            },
        )
        self.assertEqual(
            view["state"], "DELIVERY_UNCONFIRMED"
        )

    def test_confirmed_delivery_is_not_acknowledgement(self):
        self.complete_reports()
        view = build_patient_status(
            self.case,
            approval=self.approval,
            delivery=self.delivery,
        )
        self.assertEqual(view["state"], "DELIVERED")

    def test_acknowledgement_after_delivery(self):
        self.complete_reports()
        view = build_patient_status(
            self.case,
            approval=self.approval,
            delivery=self.delivery,
            acknowledged=True,
        )
        self.assertEqual(view["state"], "ACKNOWLEDGED")

    def test_early_acknowledgement_is_rejected(self):
        self.complete_reports()
        with self.assertRaises(ValueError):
            build_patient_status(
                self.case,
                approval=self.approval,
                delivery={
                    "case_version": 1,
                    "status": "queued",
                },
                acknowledged=True,
            )

    def test_old_approval_does_not_authorize_new_case(self):
        self.complete_reports()
        self.case["version"] = 2

        view = build_patient_status(
            self.case,
            approval=self.approval,
            delivery=self.delivery,
            acknowledged=True,
        )
        self.assertEqual(
            view["state"], "AWAITING_CLINICIAN_REVIEW"
        )
        self.assertTrue(view["approval_outdated"])

    def test_patient_view_excludes_source_evidence(self):
        view = build_patient_status(self.case)
        output = json.dumps(view)

        self.assertNotIn("source_text", output)
        self.assertNotIn("PAT-001", output)
        self.assertNotIn("LAB-A", output)


if __name__ == "__main__":
    unittest.main()
