import json
import tempfile
import unittest
from pathlib import Path

from core.followup import build_patient_status
from services.delivery_worker import (
    SimulatedWorkerCrash,
    dispatch_notification,
    verify_delivery,
)
from services.fake_notification import FakeNotificationGateway
from storage.approvals import (
    approve_followup,
    get_current_approval,
    initialize_approval_schema,
    seed_demo_actor,
)
from storage.db import initialize_db
from storage.outbox import (
    get_notification,
    initialize_outbox_schema,
    queue_approved_notification,
    reserve_notification,
)
from storage.repository import (
    create_case,
    get_case,
    ingest_report,
)


DATA = json.loads(
    (Path(__file__).resolve().parents[1]
     / "fixtures/demo_case.json").read_text()
)


class TestDeliveryWorker(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)

        self.clinic_db = root / "clinic.db"
        self.gateway_db = root / "destination.db"

        initialize_db(self.clinic_db)
        initialize_approval_schema(self.clinic_db)
        initialize_outbox_schema(self.clinic_db)

        create_case(self.clinic_db, DATA)
        seed_demo_actor(self.clinic_db, "DOC-01", "clinician")
        seed_demo_actor(self.clinic_db, "STAFF-01", "coordinator")

        ingest_report(
            self.clinic_db,
            "CASE-001",
            {
                "report_id": "R-03",
                "order_id": "T-03",
                "patient_id": "PAT-001",
                "test_code": "LAB-C",
            },
            expected_version=1,
        )

        approve_followup(
            self.clinic_db,
            "CASE-001",
            clinician_id="DOC-01",
            expected_version=2,
            instructions="Please contact the clinic for follow-up.",
        )

        result = queue_approved_notification(
            self.clinic_db,
            "CASE-001",
            expected_version=2,
            requester_id="STAFF-01",
        )

        self.notification_id = result["notification_id"]
        self.gateway = FakeNotificationGateway(self.gateway_db)

    def tearDown(self):
        self.temp.cleanup()

    def test_dispatch_requires_target_verification(self):
        result = dispatch_notification(
            self.clinic_db,
            self.notification_id,
            self.gateway,
        )

        self.assertEqual(result["outcome"], "delivered")
        self.assertEqual(self.gateway.delivery_count(), 1)

        notification = get_notification(
            self.clinic_db, self.notification_id
        )
        self.assertEqual(notification["status"], "delivered")

    def test_patient_status_after_verified_delivery(self):
        dispatch_notification(
            self.clinic_db,
            self.notification_id,
            self.gateway,
        )

        notification = get_notification(
            self.clinic_db, self.notification_id
        )

        view = build_patient_status(
            get_case(self.clinic_db, "CASE-001"),
            approval=get_current_approval(
                self.clinic_db, "CASE-001"
            ),
            delivery={
                "case_version": notification["case_version"],
                "status": notification["status"],
            },
        )

        self.assertEqual(view["state"], "DELIVERED")
        self.assertNotIn("instructions", view)

    def test_crash_after_send_recovers_without_resend(self):
        with self.assertRaises(SimulatedWorkerCrash):
            dispatch_notification(
                self.clinic_db,
                self.notification_id,
                self.gateway,
                simulate_crash_after_send=True,
            )

        self.assertEqual(self.gateway.delivery_count(), 1)

        result = verify_delivery(
            self.clinic_db,
            self.notification_id,
            self.gateway,
        )

        self.assertEqual(result["outcome"], "delivered")
        self.assertEqual(self.gateway.delivery_count(), 1)

    def test_stale_queued_message_does_not_execute(self):
        ingest_report(
            self.clinic_db,
            "CASE-001",
            {
                "report_id": "R-04",
                "order_id": "T-03",
                "patient_id": "PAT-001",
                "test_code": "LAB-C",
            },
            expected_version=2,
        )

        result = dispatch_notification(
            self.clinic_db,
            self.notification_id,
            self.gateway,
        )

        self.assertEqual(result["outcome"], "superseded")
        self.assertEqual(self.gateway.delivery_count(), 0)

    def test_duplicate_dispatch_does_not_send_again(self):
        dispatch_notification(
            self.clinic_db,
            self.notification_id,
            self.gateway,
        )

        second = dispatch_notification(
            self.clinic_db,
            self.notification_id,
            self.gateway,
        )

        self.assertEqual(second["outcome"], "not_queued")
        self.assertEqual(self.gateway.delivery_count(), 1)

    def test_missing_receipt_stays_unknown(self):
        reserve_notification(
            self.clinic_db, self.notification_id
        )

        result = verify_delivery(
            self.clinic_db,
            self.notification_id,
            self.gateway,
        )

        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(
            get_notification(
                self.clinic_db, self.notification_id
            )["status"],
            "unknown",
        )

    def test_destination_idempotency_and_conflict(self):
        first = self.gateway.send(
            "example-key", "Fictional update"
        )
        repeated = self.gateway.send(
            "example-key", "Fictional update"
        )

        self.assertFalse(first["replayed"])
        self.assertTrue(repeated["replayed"])

        with self.assertRaises(ValueError):
            self.gateway.send(
                "example-key", "Different content"
            )

        self.assertEqual(self.gateway.delivery_count(), 1)


if __name__ == "__main__":
    unittest.main()
