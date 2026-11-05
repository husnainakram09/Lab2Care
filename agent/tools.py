
"""Read-only administrative investigation tools.

Fictional records only. No medical interpretation,
clinical decisions, external writes or LLM calls.
"""

import json
from pathlib import Path

from core.reconcile import reconcile_case
from storage.repository import get_case


class LabInvestigationTools:

    def __init__(self, db_path, case_id, lab_source):
        self.db_path = db_path
        self.case_id = case_id

        self.source = json.loads(
            Path(lab_source).read_text(encoding="utf-8")
        )

        if self.source.get("fictional") is not True:
            raise ValueError("Only fictional lab sources allowed")

        if get_case(db_path, case_id) is None:
            raise KeyError("Unknown case")

    def _case(self):
        case = get_case(self.db_path, self.case_id)

        if case is None:
            raise KeyError("Case no longer exists")

        return case

    def get_pending_orders(self):
        case = self._case()

        result = reconcile_case(
            case["patient_id"],
            case["orders"],
            case["reports"],
        )

        pending = set(result["missing_order_ids"])

        return {
            "case_id": self.case_id,
            "case_version": case["version"],
            "pending_orders": [
                {
                    "order_id": order["order_id"],
                    "test_code": order["test_code"],
                }
                for order in case["orders"]
                if order["order_id"] in pending
            ],
        }

    def search_lab_records(self, order_id):
        case = self._case()

        pending = self.get_pending_orders()
        pending_ids = {
            item["order_id"]
            for item in pending["pending_orders"]
        }

        if order_id not in pending_ids:
            raise ValueError(
                "Only a currently pending order is searchable"
            )

        order = next(
            item for item in case["orders"]
            if item["order_id"] == order_id
        )

        candidates = []
        withheld_patient_mismatch_count = 0

        for record in self.source["records"]:
            if record["case_id"] != self.case_id:
                continue

            if record["test_code"] != order["test_code"]:
                continue

            same_patient = (
                record["patient_id"] == case["patient_id"]
            )

            if not same_patient:
                withheld_patient_mismatch_count += 1
                continue

            same_order = (
                record["order_reference"] == order_id
            )

            candidates.append({
                "source_id": record["record_id"],
                "external_reference":
                    record["order_reference"],
                "lab_status": record["status"],
                "patient_reference_matches": same_patient,
                "order_reference_matches": same_order,
                "requires_staff_verification": True,
                "message_ids": [
                    message["message_id"]
                    for message in self.source["messages"]
                    if (
                       message["case_id"] == self.case_id
                       and message["record_id"] == record["record_id"]
                    )
                ],
            })

        return {
            "order_id": order_id,
            "candidates": candidates,
            "withheld_patient_mismatch_count":
                withheld_patient_mismatch_count,
            "automatically_attached": False,
        }

    def inspect_lab_message(self, message_id):
        case = self._case()

        for message in self.source["messages"]:
            if (
                message["message_id"] != message_id
                or message["case_id"] != self.case_id
            ):
                continue

            record = next(
                (
                    item
                    for item in self.source["records"]
                    if (
                        item["record_id"] == message["record_id"]
                        and item["case_id"] == self.case_id
                        and item["patient_id"] == case["patient_id"]
                    )
                 ),
                 None,
            )

            if record is None:
                raise KeyError(
                    "Message unavailable for this case"
                )

            return {
                "source_id": message_id,
                "record_id": message["record_id"],
                "body": message["body"],
                "untrusted_external_text": True,
            }

        raise KeyError("Message unavailable for this case")

    def draft_staff_clarification(self, order_id, record_id):
        search = self.search_lab_records(order_id)

        matching = [
            item for item in search["candidates"]
            if item["source_id"] == record_id
        ]

        if not matching:
            raise ValueError(
                "Evidence does not belong to this pending order"
            )

        candidate = matching[0]

        return {
            "status": "NEEDS_STAFF_REVIEW",
            "action": "REQUEST_REFERENCE_CONFIRMATION",
            "evidence_source_ids": [record_id],
            "draft": (
                "Please confirm whether external reference "
                f"{candidate['external_reference']} corresponds "
                f"to clinic order {order_id}. "
                "Do not attach a report until authorized staff "
                "verify the original identifiers."
            ),
            "executed": False,
        }


    def draft_missing_report_escalation(self, order_id):
        pending = self.get_pending_orders()

        pending_ids = {
            item["order_id"]
            for item in pending["pending_orders"]
        }

        if order_id not in pending_ids:
            raise ValueError("Order is not currently pending")

        search = self.search_lab_records(order_id)

        if search["candidates"]:
            raise ValueError(
                "Candidate evidence exists; investigate it first"
            )

        return {
            "status": "NEEDS_STAFF_REVIEW",
            "action": "REQUEST_MISSING_REPORT_STATUS",
            "order_id": order_id,
            "evidence_source_ids": [],
            "draft": (
                f"Clinic order {order_id} remains unresolved. "
                "No eligible patient-matching lab record was found "
                "in the available fictional lab source. "
                "Authorized clinic staff should contact the "
                "laboratory to verify the order and report status. "
                "Do not mark the report complete."
            ),
            "executed": False,
        }
