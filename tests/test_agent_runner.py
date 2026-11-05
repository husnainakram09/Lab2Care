
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.runner import investigate_case
from agent.tools import LabInvestigationTools
from storage.db import initialize_db
from storage.repository import create_case, get_case


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads(
    (ROOT / "fixtures/demo_case.json").read_text()
)


def tool_call(name, arguments, call_id):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


def answer(calls=None, content=""):
    message = SimpleNamespace(
        tool_calls=calls or [],
        content=content,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)]
    )


class FakeModelClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.chat = self
        self.completions = self
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


class TestAgentRunner(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "clinic.db"

        initialize_db(self.path)
        create_case(self.path, DATA)

        self.tools = LabInvestigationTools(
            self.path,
            "CASE-001",
            ROOT / "fixtures/lab_inbox.json",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_multistep_investigation_produces_staff_draft(self):
        client = FakeModelClient([
            answer([
                tool_call("get_pending_orders", {}, "c1"),
                tool_call(
                    "search_lab_records",
                    {"order_id": "T-03"},
                    "c2",
                ),
            ]),
            answer([
                tool_call(
                    "inspect_lab_message",
                    {"message_id": "MSG-101"},
                    "c3",
                ),
                tool_call(
                    "draft_staff_clarification",
                    {
                        "order_id": "T-03",
                        "record_id": "LABREC-101",
                    },
                    "c4",
                ),
            ]),
            answer(
                content="External reference needs staff verification."
            ),
        ])

        before = get_case(self.path, "CASE-001")

        result = investigate_case(
            client, "mock-model", self.tools
        )

        self.assertEqual(
            result["status"], "NEEDS_STAFF_REVIEW"
        )
        self.assertEqual(len(result["trace"]), 4)
        self.assertEqual(len(result["drafts"]), 1)
        self.assertFalse(result["drafts"][0]["executed"])
        self.assertEqual(
            before,
            get_case(self.path, "CASE-001"),
        )

    def test_unapproved_tool_is_blocked(self):
        client = FakeModelClient([
            answer([
                tool_call("delete_case", {}, "c1"),
            ]),
        ])

        result = investigate_case(
            client, "mock-model", self.tools
        )

        self.assertEqual(result["status"], "BLOCKED")

    def test_model_without_investigation_is_incomplete(self):
        client = FakeModelClient([
            answer(content="Everything looks fine."),
        ])

        result = investigate_case(
            client, "mock-model", self.tools
        )

        self.assertEqual(result["status"], "INCOMPLETE")

    def test_extra_tool_arguments_are_blocked(self):
        client = FakeModelClient([
            answer([
                tool_call(
                    "get_pending_orders",
                    {"case_id": "CASE-OTHER"},
                    "c1",
                ),
            ]),
        ])

        result = investigate_case(
            client, "mock-model", self.tools
        )

        self.assertEqual(result["status"], "BLOCKED")

    def test_round_limit_stops_repeated_calls(self):
        client = FakeModelClient([
            answer([
                tool_call("get_pending_orders", {}, "c1"),
            ]),
        ])

        result = investigate_case(
            client,
            "mock-model",
            self.tools,
            max_rounds=1,
        )

        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(client.calls, 1)

    def test_duplicate_clarification_is_counted_once(self):
        arguments = {
            "order_id": "T-03",
            "record_id": "LABREC-101",
        }

        client = FakeModelClient([
            answer([
                tool_call(
                    "draft_staff_clarification",
                    arguments,
                    "call-1",
                ),
                tool_call(
                    "draft_staff_clarification",
                    arguments,
                    "call-2",
                ),
            ]),
            answer(content="Staff clarification required."),
        ])

        result = investigate_case(
            client,
            "mock-model",
            self.tools,
        )

        self.assertEqual(
            result["status"], "NEEDS_STAFF_REVIEW"
        )
        self.assertEqual(len(result["trace"]), 2)
        self.assertEqual(len(result["drafts"]), 1)


    def test_no_candidate_model_can_escalate(self):
        self.tools.source["records"] = [
            record
            for record in self.tools.source["records"]
            if record["record_id"] == "LABREC-102"
        ]

        client = FakeModelClient([
            answer([
                tool_call(
                    "search_lab_records",
                    {"order_id": "T-03"},
                    "c1",
                ),
            ]),
            answer([
                tool_call(
                    "draft_missing_report_escalation",
                    {"order_id": "T-03"},
                    "c2",
                ),
            ]),
            answer(content="Staff must check with the lab."),
        ])

        result = investigate_case(
            client, "mock-model", self.tools
        )

        self.assertEqual(
            result["status"], "NEEDS_STAFF_REVIEW"
        )
        self.assertEqual(len(result["drafts"]), 1)
        self.assertEqual(
            result["drafts"][0]["action"],
            "REQUEST_MISSING_REPORT_STATUS",
        )


if __name__ == "__main__":
    unittest.main()
