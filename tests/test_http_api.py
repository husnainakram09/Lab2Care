
"""HTTP integration tests for the fictional follow-up demo."""

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from scripts.demo_patient_journey import run_demo
from storage.repository import ingest_report


class TestDemoHTTPAPI(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        result = run_demo(self.root)

        self.db_path = self.root / "clinic.db"
        self.timeline_path = self.root / "timeline.json"

        self.timeline_path.write_text(
            json.dumps(result["timeline"]),
            encoding="utf-8",
        )

        self.client = TestClient(
            create_app(self.db_path, self.timeline_path)
        )

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data_mode"],
            "fictional",
        )

    def test_verified_patient_status(self):
        response = self.client.get(
            "/demo/cases/CASE-001/status"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["state"],
            "DELIVERED",
        )
        self.assertEqual(
            response.json()["received_count"],
            3,
        )

    def test_patient_status_excludes_raw_evidence(self):
        response = self.client.get(
            "/demo/cases/CASE-001/status"
        )

        body = response.text

        for forbidden in (
            "PAT-001",
            "source_text",
            "instructions",
            "LAB-C",
        ):
            self.assertNotIn(forbidden, body)

    def test_unknown_case_returns_404(self):
        response = self.client.get(
            "/demo/cases/UNKNOWN/status"
        )

        self.assertEqual(response.status_code, 404)

    def test_recorded_journey(self):
        response = self.client.get("/demo/journey")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["mode"],
            "recorded_fictional_demo",
        )
        self.assertEqual(
            len(response.json()["stages"]),
            5,
        )

    def test_new_evidence_requires_staff_review(self):
        ingest_report(
            self.db_path,
            "CASE-001",
            {
                "report_id": "R-04",
                "order_id": "T-03",
                "patient_id": "PAT-001",
                "test_code": "LAB-C",
                "source_text": "Fictional conflicting report",
            },
            expected_version=2,
        )

        response = self.client.get(
            "/demo/cases/CASE-001/status"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["state"],
            "STAFF_REVIEW_REQUIRED",
        )

    def test_missing_database_returns_503(self):
        unavailable = TestClient(
            create_app(self.root / "missing.db")
        )

        try:
            response = unavailable.get("/health")
            self.assertEqual(response.status_code, 503)
        finally:
            unavailable.close()


if __name__ == "__main__":
    unittest.main()
