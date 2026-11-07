
"""Tests for the persistent fictional patient case."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from openai import APITimeoutError

from api.demo_state import prepare_demo_db
from services.delivery_worker import (
    SimulatedWorkerCrash,
    dispatch_notification,
)
from services.fake_notification import FakeNotificationGateway
from storage.repository import ingest_report


class TestSharedCaseAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with patch.dict(
            os.environ,
            {"FOLLOWUP_ENABLE_LOCAL_AGENT": "1"},
        ):
            from api.dev_main import app

        cls.app = app

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "clinic.db"

        prepare_demo_db(self.db_path)

        self.database_patch = patch(
            "api.demo_state.ACTIVE_DB",
            self.db_path,
        )
        self.database_patch.start()

        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.database_patch.stop()
        self.temp.cleanup()

    def test_reads_persistent_case(self):
        response = self.client.get(
            "/demo/active-case/status"
        )

        self.assertEqual(response.status_code, 200)

        result = response.json()

        self.assertEqual(result["state"], "AWAITING_REPORTS")
        self.assertEqual(result["received_count"], 2)
        self.assertEqual(result["pending_count"], 1)
        self.assertEqual(result["case_version"], 1)

    def test_new_report_updates_patient_view(self):
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

        response = self.client.get(
            "/demo/active-case/status"
        )

        self.assertEqual(response.status_code, 200)

        result = response.json()

        self.assertEqual(
            result["state"],
            "AWAITING_CLINICIAN_REVIEW",
        )
        self.assertEqual(result["received_count"], 3)
        self.assertEqual(result["pending_count"], 0)
        self.assertEqual(result["case_version"], 2)

    def test_staff_review_endpoint_returns_evidence(self):
        response = self.client.get(
            "/demo/staff/review",
            headers={"X-Demo-Confirmation": "yes"},
        )

        self.assertEqual(response.status_code, 200)

        packet = response.json()
        self.assertEqual(packet["case_version"], 1)
        self.assertEqual(
            packet["pending_orders"][0]["order_id"],
            "T-03",
        )
        self.assertEqual(
            packet["pending_orders"][0]["candidates"][0]["source_id"],
            "LABREC-101",
        )

    def test_staff_review_requires_confirmation(self):
        response = self.client.get("/demo/staff/review")

        self.assertEqual(response.status_code, 403)



    def test_confirmed_report_advances_to_clinician_review(self):
        response = self.client.post(
            "/demo/staff/receive-confirmed-report",
            headers={"X-Demo-Confirmation": "yes"},
            json={
                "confirmation_id": "LABCONF-001",
                "expected_version": 1,
                "staff_attested": True,
            },
        )

        self.assertEqual(response.status_code, 200)

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(
            patient["state"],
            "AWAITING_CLINICIAN_REVIEW",
        )
        self.assertEqual(patient["received_count"], 3)
        self.assertEqual(patient["case_version"], 2)

    def test_report_requires_staff_attestation(self):
        response = self.client.post(
            "/demo/staff/receive-confirmed-report",
            headers={"X-Demo-Confirmation": "yes"},
            json={
                "confirmation_id": "LABCONF-001",
                "expected_version": 1,
                "staff_attested": False,
            },
        )

        self.assertEqual(response.status_code, 409)

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(patient["received_count"], 2)

    def test_stale_confirmation_is_rejected(self):
        payload = {
            "confirmation_id": "LABCONF-001",
            "expected_version": 1,
            "staff_attested": True,
        }
        headers = {"X-Demo-Confirmation": "yes"}

        first = self.client.post(
            "/demo/staff/receive-confirmed-report",
            headers=headers,
            json=payload,
        )
        second = self.client.post(
            "/demo/staff/receive-confirmed-report",
            headers=headers,
            json=payload,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(patient["case_version"], 2)
        self.assertEqual(patient["received_count"], 3)


    def test_clinician_cannot_approve_missing_report(self):
        response = self.client.post(
            "/demo/clinician/approve",
            headers={"X-Demo-Confirmation": "yes"},
            json={
                "expected_version": 1,
                "clinician_attested": True,
            },
        )

        self.assertEqual(response.status_code, 409)

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(
            patient["state"], "AWAITING_REPORTS"
        )

    def test_clinician_approval_updates_patient_state(self):
        headers = {"X-Demo-Confirmation": "yes"}

        received = self.client.post(
            "/demo/staff/receive-confirmed-report",
            headers=headers,
            json={
                "confirmation_id": "LABCONF-001",
                "expected_version": 1,
                "staff_attested": True,
            },
        )
        self.assertEqual(received.status_code, 200)

        approved = self.client.post(
            "/demo/clinician/approve",
            headers=headers,
            json={
                "expected_version": 2,
                "clinician_attested": True,
            },
        )

        self.assertEqual(approved.status_code, 200)
        self.assertFalse(
            approved.json()["notification_sent"]
        )

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(
            patient["state"],
            "APPROVED_FOR_COMMUNICATION",
        )
        self.assertEqual(patient["received_count"], 3)

    def test_clinician_approval_requires_attestation(self):
        headers = {"X-Demo-Confirmation": "yes"}

        received = self.client.post(
            "/demo/staff/receive-confirmed-report",
            headers=headers,
            json={
                "confirmation_id": "LABCONF-001",
                "expected_version": 1,
                "staff_attested": True,
            },
        )
        self.assertEqual(received.status_code, 200)

        response = self.client.post(
            "/demo/clinician/approve",
            headers=headers,
            json={
                "expected_version": 2,
                "clinician_attested": False,
            },
        )

        self.assertEqual(response.status_code, 409)

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(
            patient["state"],
            "AWAITING_CLINICIAN_REVIEW",
        )


    def prepare_approved_case_for_delivery(self):
        headers = {"X-Demo-Confirmation": "yes"}

        received = self.client.post(
            "/demo/staff/receive-confirmed-report",
            headers=headers,
            json={
                "confirmation_id": "LABCONF-001",
                "expected_version": 1,
                "staff_attested": True,
            },
        )
        self.assertEqual(received.status_code, 200)

        approved = self.client.post(
            "/demo/clinician/approve",
            headers=headers,
            json={
                "expected_version": 2,
                "clinician_attested": True,
            },
        )
        self.assertEqual(approved.status_code, 200)

        return headers

    def test_notification_requires_clinician_approval(self):
        response = self.client.post(
            "/demo/clinic/queue-notification",
            headers={"X-Demo-Confirmation": "yes"},
            json={"expected_version": 1},
        )

        self.assertEqual(response.status_code, 409)

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(
            patient["state"], "AWAITING_REPORTS"
        )

    def test_queue_is_not_delivery(self):
        headers = self.prepare_approved_case_for_delivery()

        response = self.client.post(
            "/demo/clinic/queue-notification",
            headers=headers,
            json={"expected_version": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["outcome"], "queued"
        )

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(
            patient["state"], "DELIVERY_UNCONFIRMED"
        )

    def test_verified_delivery_updates_patient_status(self):
        headers = self.prepare_approved_case_for_delivery()

        queued = self.client.post(
            "/demo/clinic/queue-notification",
            headers=headers,
            json={"expected_version": 2},
        )
        self.assertEqual(queued.status_code, 200)

        delivered = self.client.post(
            "/demo/clinic/deliver-notification",
            headers=headers,
            json={"expected_version": 2},
        )

        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(
            delivered.json()["notification_status"],
            "delivered",
        )
        self.assertEqual(
            delivered.json()["fictional_destination_receipts"],
            1,
        )

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(patient["state"], "DELIVERED")

    def test_delivery_cannot_be_repeated(self):
        headers = self.prepare_approved_case_for_delivery()

        queued = self.client.post(
            "/demo/clinic/queue-notification",
            headers=headers,
            json={"expected_version": 2},
        )
        self.assertEqual(queued.status_code, 200)

        first = self.client.post(
            "/demo/clinic/deliver-notification",
            headers=headers,
            json={"expected_version": 2},
        )
        second = self.client.post(
            "/demo/clinic/deliver-notification",
            headers=headers,
            json={"expected_version": 2},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)


    def prepare_delivered_case_for_ack(self):
        headers = self.prepare_approved_case_for_delivery()

        queued = self.client.post(
            "/demo/clinic/queue-notification",
            headers=headers,
            json={"expected_version": 2},
        )
        self.assertEqual(queued.status_code, 200)

        delivered = self.client.post(
            "/demo/clinic/deliver-notification",
            headers=headers,
            json={"expected_version": 2},
        )
        self.assertEqual(delivered.status_code, 200)

        return headers

    def test_acknowledgement_requires_delivery(self):
        headers = self.prepare_approved_case_for_delivery()

        queued = self.client.post(
            "/demo/clinic/queue-notification",
            headers=headers,
            json={"expected_version": 2},
        )
        self.assertEqual(queued.status_code, 200)

        response = self.client.post(
            "/demo/patient/acknowledge",
            headers=headers,
            json={
                "expected_version": 2,
                "patient_attested": True,
            },
        )

        self.assertEqual(response.status_code, 409)

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(
            patient["state"], "DELIVERY_UNCONFIRMED"
        )

    def test_acknowledgement_requires_attestation(self):
        headers = self.prepare_delivered_case_for_ack()

        response = self.client.post(
            "/demo/patient/acknowledge",
            headers=headers,
            json={
                "expected_version": 2,
                "patient_attested": False,
            },
        )

        self.assertEqual(response.status_code, 409)

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(patient["state"], "DELIVERED")

    def test_acknowledgement_persists(self):
        headers = self.prepare_delivered_case_for_ack()

        response = self.client.post(
            "/demo/patient/acknowledge",
            headers=headers,
            json={
                "expected_version": 2,
                "patient_attested": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["state"], "ACKNOWLEDGED"
        )

        patient = self.client.get(
            "/demo/active-case/status"
        ).json()

        self.assertEqual(patient["state"], "ACKNOWLEDGED")
        self.assertEqual(patient["case_version"], 2)

    def test_duplicate_acknowledgement_is_rejected(self):
        headers = self.prepare_delivered_case_for_ack()

        payload = {
            "expected_version": 2,
            "patient_attested": True,
        }

        first = self.client.post(
            "/demo/patient/acknowledge",
            headers=headers,
            json=payload,
        )

        second = self.client.post(
            "/demo/patient/acknowledge",
            headers=headers,
            json=payload,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

    def test_active_case_timeline_endpoint(self):
        response = self.client.get(
            "/demo/active-case/timeline"
        )

        self.assertEqual(response.status_code, 200)

        history = response.json()

        self.assertEqual(history["case_id"], "CASE-001")
        self.assertEqual(history["case_version"], 1)
        self.assertEqual(history["events"], [])
        self.assertTrue(history["read_only"])


    def test_synthea_research_http_summary(self):
        response = self.client.get("/demo/research/synthea")

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(
            data["resource_counts"]["ServiceRequest"],
            413,
        )
        self.assertFalse(data["linked_to_active_demo"])
        self.assertFalse(data["clinical_outcomes_evaluated"])

    def queue_notification(self):
        headers = self.prepare_approved_case_for_delivery()

        queued = self.client.post(
            "/demo/clinic/queue-notification",
            headers=headers,
            json={"expected_version": 2},
        )
        self.assertEqual(queued.status_code, 200)

        return headers, queued.json()["notification_id"]

    def set_outbox_status(self, status):
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute(
                "UPDATE notification_outbox SET status = ?",
                (status,),
            )

    def destination(self):
        return FakeNotificationGateway(
            self.db_path.with_name("destination.db")
        )

    def test_status_survives_internal_outbox_states(self):
        self.queue_notification()

        for status, expected in (
            ("sending", "DELIVERY_UNCONFIRMED"),
            ("unknown", "DELIVERY_UNCONFIRMED"),
            ("superseded", "DELIVERY_FAILED"),
        ):
            self.set_outbox_status(status)

            response = self.client.get("/demo/active-case/status")

            self.assertEqual(response.status_code, 200, status)
            self.assertEqual(response.json()["state"], expected)

    def test_interrupted_delivery_is_verified_not_resent(self):
        headers, notification_id = self.queue_notification()

        with self.assertRaises(SimulatedWorkerCrash):
            dispatch_notification(
                self.db_path,
                notification_id,
                self.destination(),
                simulate_crash_after_send=True,
            )

        response = self.client.post(
            "/demo/clinic/deliver-notification",
            headers=headers,
            json={"expected_version": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["notification_status"], "delivered"
        )
        self.assertEqual(self.destination().delivery_count(), 1)

    def test_unconfirmed_delivery_can_be_retried_once(self):
        headers, _ = self.queue_notification()
        self.set_outbox_status("unknown")

        for _ in range(2):
            response = self.client.post(
                "/demo/clinic/deliver-notification",
                headers=headers,
                json={"expected_version": 2},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            self.client.get("/demo/active-case/status").json()["state"],
            "DELIVERED",
        )
        self.assertEqual(self.destination().delivery_count(), 1)

    def test_repeated_approval_reports_current_state(self):
        headers, _ = self.queue_notification()

        response = self.client.post(
            "/demo/clinician/approve",
            headers=headers,
            json={"expected_version": 2, "clinician_attested": True},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["state"], "DELIVERY_UNCONFIRMED"
        )

    def test_attestation_requires_json_boolean(self):
        response = self.client.post(
            "/demo/staff/receive-confirmed-report",
            headers={"X-Demo-Confirmation": "yes"},
            json={
                "confirmation_id": "LABCONF-001",
                "expected_version": 1,
                "staff_attested": "true",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self.client.get("/demo/active-case/status").json()[
                "received_count"
            ],
            2,
        )

    def investigate_with(self, client_class):
        local = TestClient(self.app, client=("127.0.0.1", 50000))

        with patch.dict(os.environ, {
            "VULTR_SERVERLESS_INFERENCE_API_KEY": "test-key",
            "VULTR_MODEL": "test-model",
        }), patch("api.local_agent.OpenAI", client_class):
            try:
                return local.post(
                    "/demo/agent/investigate",
                    headers={"X-Demo-Confirmation": "yes"},
                )
            finally:
                local.close()

    def test_inference_timeout_returns_clear_error(self):
        class TimingOutClient:
            def __init__(self, **_):
                self.chat = self
                self.completions = self

            def create(self, **_):
                raise APITimeoutError(
                    request=httpx.Request("POST", "https://example.test")
                )

        response = self.investigate_with(TimingOutClient)

        self.assertEqual(response.status_code, 504)
        self.assertIn("No case data was changed", response.json()["detail"])

    def test_investigation_explains_why_it_stopped(self):
        class SilentClient:
            def __init__(self, **_):
                self.chat = self
                self.completions = self

            def create(self, **_):
                message = SimpleNamespace(content="", tool_calls=None)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=message)]
                )

        response = self.investigate_with(SilentClient)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "INCOMPLETE")
        self.assertTrue(response.json()["reason"])

if __name__ == "__main__":
    unittest.main()
