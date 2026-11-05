import json
import tempfile
import unittest
from pathlib import Path

from core.followup import build_patient_status
from storage.approvals import (
    approve_followup,
    get_current_approval,
    initialize_approval_schema,
    seed_demo_actor,
)
from storage.db import initialize_db
from storage.outbox import (
    NotificationForbidden,
    NotificationNotApproved,
    get_notification,
    initialize_outbox_schema,
    queue_approved_notification,
    reserve_notification,
)
from storage.repository import (
    StaleCaseVersion,
    create_case,
    get_case,
    ingest_report,
)


DATA = json.loads(
    (Path(__file__).resolve().parents[1]
     / "fixtures/demo_case.json").read_text()
)


class TestNotificationOutbox(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"

        initialize_db(self.path)
        initialize_approval_schema(self.path)
        initialize_outbox_schema(self.path)

        create_case(self.path, DATA)
        seed_demo_actor(self.path, "DOC-01", "clinician")
        seed_demo_actor(self.path, "STAFF-01", "coordinator")

        self.instructions = (
            "Please contact the clinic to arrange follow-up."
        )

    def tearDown(self):
        self.temp.cleanup()

    def approve_complete_case(self):
        ingest_report(
            self.path,
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
            self.path,
            "CASE-001",
            clinician_id="DOC-01",
            expected_version=2,
            instructions=self.instructions,
        )

    def queue(self, **overrides):
        args = {
            "expected_version": 2,
            "requester_id": "STAFF-01",
        }
        args.update(overrides)

        return queue_approved_notification(
            self.path, "CASE-001", **args
        )

    def test_no_approval_means_no_notification(self):
        with self.assertRaises(NotificationNotApproved):
            self.queue(expected_version=1)

    def test_approved_instructions_are_queued(self):
        self.approve_complete_case()
        result = self.queue()
        notification = get_notification(
            self.path, result["notification_id"]
        )

        self.assertEqual(result["outcome"], "queued")
        self.assertEqual(notification["status"], "queued")
        self.assertEqual(
            notification["instructions"], self.instructions
        )

    def test_duplicate_queue_is_idempotent(self):
        self.approve_complete_case()
        first = self.queue()
        second = self.queue()

        self.assertEqual(second["outcome"], "duplicate")
        self.assertEqual(
            first["notification_id"],
            second["notification_id"],
        )

    def test_unregistered_actor_cannot_queue(self):
        self.approve_complete_case()
        with self.assertRaises(NotificationForbidden):
            self.queue(requester_id="UNKNOWN")

    def test_stale_case_version_is_rejected(self):
        self.approve_complete_case()
        with self.assertRaises(StaleCaseVersion):
            self.queue(expected_version=1)

    def test_new_evidence_supersedes_queued_message(self):
        self.approve_complete_case()
        queued = self.queue()

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

        result = reserve_notification(
            self.path, queued["notification_id"]
        )

        self.assertEqual(result["outcome"], "superseded")
        self.assertEqual(
            get_notification(
                self.path, queued["notification_id"]
            )["status"],
            "superseded",
        )

    def test_worker_can_claim_only_once(self):
        self.approve_complete_case()
        queued = self.queue()
        notification_id = queued["notification_id"]

        first = reserve_notification(
            self.path, notification_id
        )
        second = reserve_notification(
            self.path, notification_id
        )

        self.assertEqual(first["outcome"], "claimed")
        self.assertEqual(second["outcome"], "not_queued")
        self.assertEqual(second["status"], "sending")
        self.assertEqual(
            first["instructions"], self.instructions
        )

    def test_queued_message_is_not_reported_delivered(self):
        self.approve_complete_case()
        queued = self.queue()
        notification = get_notification(
            self.path, queued["notification_id"]
        )

        patient_view = build_patient_status(
            get_case(self.path, "CASE-001"),
            approval=get_current_approval(
                self.path, "CASE-001"
            ),
            delivery={
                "case_version": notification["case_version"],
                "status": notification["status"],
            },
        )

        self.assertEqual(
            patient_view["state"], "DELIVERY_UNCONFIRMED"
        )
        self.assertNotIn("instructions", patient_view)


if __name__ == "__main__":
    unittest.main()
