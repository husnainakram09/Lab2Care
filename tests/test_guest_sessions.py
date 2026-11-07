"""Tests for per-visitor guest cases and the inference budget."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import demo_state
from api.inference_budget import InferenceBudget


HEADERS = {"X-Demo-Confirmation": "yes"}
REMOTE = ("203.0.113.9", 40000)


class TestGuestSessions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"FOLLOWUP_ENABLE_LOCAL_AGENT": "1"}):
            from api.dev_main import app

        cls.app = app

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sessions = Path(self.temp.name) / "sessions"

        self.patches = [
            patch.dict(os.environ, {"FOLLOWUP_GUEST_SESSIONS": "1"}),
            patch("api.demo_state.SESSIONS_DIR", self.sessions),
            # Guest mode must never touch the shared case.
            patch(
                "api.demo_state.ACTIVE_DB",
                Path(self.temp.name) / "missing" / "clinic.db",
            ),
        ]

        for item in self.patches:
            item.start()

        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()

        for item in reversed(self.patches):
            item.stop()

        self.temp.cleanup()

    def visitor(self):
        client = TestClient(self.app, client=REMOTE)
        self.clients.append(client)
        client.get("/")
        return client

    def status(self, client):
        return client.get("/demo/active-case/status").json()

    def receive_report(self, client):
        return client.post(
            "/demo/staff/receive-confirmed-report",
            headers=HEADERS,
            json={
                "confirmation_id": "LABCONF-001",
                "expected_version": 1,
                "staff_attested": True,
            },
        )

    def session_dirs(self):
        return sorted(
            path.name for path in self.sessions.iterdir()
            if path.is_dir()
        )

    def test_page_issues_private_session_cookie(self):
        client = TestClient(self.app, client=REMOTE)
        self.clients.append(client)

        response = client.get("/")

        cookie = response.headers["set-cookie"]
        self.assertIn(demo_state.SESSION_COOKIE + "=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("samesite=lax", cookie.lower())
        self.assertEqual(len(self.session_dirs()), 1)
        self.assertEqual(self.status(client)["session_mode"], "guest")

    def test_visitors_cannot_change_each_others_case(self):
        first = self.visitor()
        second = self.visitor()

        self.assertEqual(self.receive_report(first).status_code, 200)

        self.assertEqual(
            self.status(first)["state"], "AWAITING_CLINICIAN_REVIEW"
        )
        self.assertEqual(
            self.status(second)["state"], "AWAITING_REPORTS"
        )
        self.assertEqual(len(self.session_dirs()), 2)

    def test_actions_still_require_confirmation_header(self):
        client = self.visitor()

        response = client.post(
            "/demo/staff/receive-confirmed-report",
            json={
                "confirmation_id": "LABCONF-001",
                "expected_version": 1,
                "staff_attested": True,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.status(client)["received_count"], 2)

    def test_forged_session_cookie_is_replaced(self):
        client = TestClient(self.app, client=REMOTE)
        self.clients.append(client)
        client.cookies.set(demo_state.SESSION_COOKIE, "../../active")

        response = client.get("/demo/active-case/status")

        self.assertEqual(response.status_code, 200)
        issued = response.cookies.get(demo_state.SESSION_COOKIE)
        self.assertTrue(demo_state.is_valid_session_id(issued))
        self.assertEqual(self.session_dirs(), [issued])

    def test_restart_gives_fresh_case_and_discards_old(self):
        client = self.visitor()
        old_session = client.cookies.get(demo_state.SESSION_COOKIE)
        self.receive_report(client)

        response = client.post("/demo/session/restart", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        new_session = client.cookies.get(demo_state.SESSION_COOKIE)
        self.assertNotEqual(new_session, old_session)
        self.assertEqual(self.status(client)["state"], "AWAITING_REPORTS")
        self.assertEqual(self.session_dirs(), [new_session])

    def test_oldest_sessions_are_evicted_at_capacity(self):
        with patch("api.demo_state.MAX_GUEST_SESSIONS", 2):
            oldest = self.visitor().cookies.get(demo_state.SESSION_COOKIE)
            os.utime(self.sessions / oldest, (1, time.time() - 600))

            self.visitor()
            self.visitor()

        self.assertEqual(len(self.session_dirs()), 2)
        self.assertNotIn(oldest, self.session_dirs())

    def test_expired_session_starts_fresh(self):
        client = self.visitor()
        session = client.cookies.get(demo_state.SESSION_COOKIE)
        self.receive_report(client)

        stale = time.time() - demo_state.SESSION_TTL_SECONDS - 60
        os.utime(self.sessions / session, (stale, stale))

        self.assertEqual(self.status(client)["state"], "AWAITING_REPORTS")

    def test_inference_budget_is_enforced_on_endpoint(self):
        client = self.visitor()
        budget = InferenceBudget(
            per_session_per_hour=0,
            global_per_hour=10,
            max_concurrent=1,
        )

        with patch("api.local_agent.budget", budget), patch.dict(
            os.environ,
            {
                "VULTR_SERVERLESS_INFERENCE_API_KEY": "test-key",
                "VULTR_MODEL": "test-model",
            },
        ):
            response = client.post(
                "/demo/agent/investigate", headers=HEADERS
            )

        self.assertEqual(response.status_code, 429)
        self.assertIn("hourly", response.json()["detail"])


class TestSharedModeAccess(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"FOLLOWUP_ENABLE_LOCAL_AGENT": "1"}):
            from api.dev_main import app

        cls.app = app

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "clinic.db"
        demo_state.prepare_demo_db(self.db_path)

        self.patches = [
            patch.dict(os.environ, {"FOLLOWUP_GUEST_SESSIONS": ""}),
            patch("api.demo_state.ACTIVE_DB", self.db_path),
        ]

        for item in self.patches:
            item.start()

        self.client = TestClient(self.app, client=REMOTE)

    def tearDown(self):
        self.client.close()

        for item in reversed(self.patches):
            item.stop()

        self.temp.cleanup()

    def test_shared_case_rejects_remote_changes(self):
        response = self.client.post(
            "/demo/clinician/approve",
            headers=HEADERS,
            json={"expected_version": 1, "clinician_attested": True},
        )

        self.assertEqual(response.status_code, 403)

    def test_restart_is_unavailable_for_shared_case(self):
        response = self.client.post(
            "/demo/session/restart", headers=HEADERS
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("set-cookie", response.headers)


class TestInferenceBudget(unittest.TestCase):

    def setUp(self):
        self.now = 1000.0
        self.budget = InferenceBudget(
            per_session_per_hour=2,
            global_per_hour=3,
            max_concurrent=1,
            clock=lambda: self.now,
        )

    def run_once(self, session):
        refusal = self.budget.acquire(session)

        if refusal is None:
            self.budget.release()

        return refusal

    def test_per_session_limit(self):
        self.assertIsNone(self.run_once("a"))
        self.assertIsNone(self.run_once("a"))
        self.assertIn("demo case", self.run_once("a"))
        self.assertIsNone(self.run_once("b"))

    def test_global_limit_bounds_new_sessions(self):
        for session in ("a", "b", "c"):
            self.assertIsNone(self.run_once(session))

        self.assertIn("budget", self.run_once("d"))

    def test_concurrent_runs_are_limited(self):
        self.assertIsNone(self.budget.acquire("a"))
        self.assertIn("already running", self.budget.acquire("b"))
        self.budget.release()
        self.assertIsNone(self.run_once("b"))

    def test_limits_reset_after_an_hour(self):
        for session in ("a", "a", "b"):
            self.run_once(session)

        self.now += 3601

        self.assertIsNone(self.run_once("a"))


if __name__ == "__main__":
    unittest.main()
