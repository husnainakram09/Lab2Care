
"""Read-only evidence packet for fictional clinic staff.

Uses the shared case and permitted lab investigation tools.
Does not verify identities, attach reports or send messages.
"""

from pathlib import Path

from agent.tools import LabInvestigationTools


ROOT = Path(__file__).resolve().parents[1]


def build_staff_review_packet(
    db_path,
    case_id="CASE-001",
    lab_path=None,
):
    source = (
        lab_path
        if lab_path is not None
        else ROOT / "fixtures" / "lab_inbox.json"
    )

    tools = LabInvestigationTools(
        db_path,
        case_id,
        source,
    )

    initial = tools.get_pending_orders()
    pending_orders = []

    for order in initial["pending_orders"]:
        search = tools.search_lab_records(order["order_id"])
        candidates = []

        for candidate in search["candidates"]:
            messages = [
                tools.inspect_lab_message(message_id)
                for message_id in candidate["message_ids"]
            ]

            candidates.append({
                "source_id": candidate["source_id"],
                "external_reference":
                    candidate["external_reference"],
                "lab_status": candidate["lab_status"],
                "patient_reference_matches":
                    candidate["patient_reference_matches"],
                "order_reference_matches":
                    candidate["order_reference_matches"],
                "requires_staff_verification": True,
                "messages": messages,
            })

        pending_orders.append({
            "order_id": order["order_id"],
            "test_code": order["test_code"],
            "candidates": candidates,
            "withheld_patient_mismatch_count":
                search["withheld_patient_mismatch_count"],
        })

    return {
        "case_id": initial["case_id"],
        "case_version": initial["case_version"],
        "pending_orders": pending_orders,
        "status": (
            "STAFF_REVIEW_REQUIRED"
            if pending_orders
            else "NO_PENDING_ORDERS"
        ),
        "data_mode": "fictional",
        "read_only": True,
        "note": (
            "External laboratory records are unverified "
            "administrative evidence. Authorized staff must "
            "confirm uncertain references before report ingestion."
        ),
    }
