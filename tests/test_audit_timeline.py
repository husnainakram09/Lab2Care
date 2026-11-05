
"""Tests for evidence-backed fictional audit history."""

import json
import tempfile
import unittest
from pathlib import Path

from api.audit_timeline import build_case_timeline
from api.clinician_actions import simulate_clinician_approval
from api.communication_actions import (
    queue_demo_update,
    deliver_demo_update,
)
from api.demo_state import prepare_demo_db
from api.staff_actions import receive_confirmed_demo_report
from storage.acknowledgements import record_demo_acknowledgement


class TestAuditTimeline(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "clinic.db"
        prepare_demo_db(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_fresh_case_has_no_action_events(self):
        history = build_case_timeline(self.db)

        self.assertEqual(history["case_version"], 1)
        self.assertEqual(history["events"], [])
        self.assertIsNone(
            history["notification_snapshot"]
        )
        self.assertTrue(history["read_only"])

    def test_report_receipt_has_source_provenance(self):
        receive_confirmed_demo_report(
            self.db,
            confirmation_id="LABCONF-001",
            expected_version=1,
            staff_attested=True,
        )

        history = build_case_timeline(self.db)

        self.assertEqual(history["case_version"], 2)
        self.assertEqual(len(history["events"]), 1)

        event = history["events"][0]

        self.assertEqual(event["kind"], "case_event")
        self.assertTrue(
            event["source"].startswith("case_events:")
        )
        self.assertEqual(event["case_version"], 2)

        # The timeline must not expose raw report text.
        self.assertNotIn(
            "Fictional completed laboratory report",
            json.dumps(history),
        )

    def test_completed_case_uses_persisted_records(self):
        receive_confirmed_demo_report(
            self.db,
            confirmation_id="LABCONF-001",
            expected_version=1,
            staff_attested=True,
        )

        simulate_clinician_approval(
            self.db,
            expected_version=2,
            clinician_attested=True,
        )

        queued = queue_demo_update(
            self.db,
            expected_version=2,
        )

        self.assertEqual(queued["outcome"], "queued")

        delivered = deliver_demo_update(
            self.db,
            expected_version=2,
        )

        self.assertEqual(
            delivered["notification_status"],
            "delivered",
        )

        record_demo_acknowledgement(
            self.db,
            expected_version=2,
            patient_attested=True,
        )

        history = build_case_timeline(self.db)

        self.assertEqual(
            [event["kind"] for event in history["events"]],
            [
                "case_event",
                "clinician_approval",
                "notification_queued",
                "patient_acknowledgement",
            ],
        )

        self.assertEqual(
            history["notification_snapshot"]["status"],
            "delivered",
        )

        # We never invent a timed delivery ledger event.
        self.assertNotIn(
            "delivery_verified",
            [event["kind"] for event in history["events"]],
        )


if __name__ == "__main__":
    unittest.main()
