
"""Controlled fictional staff report-receipt action.

Local demo only. Staff attestation is simulated, not
real authentication or external lab verification.
"""

import json
from pathlib import Path

from api.staff_review import build_staff_review_packet
from storage.repository import get_case, ingest_report


ROOT = Path(__file__).resolve().parents[1]
CONFIRMATION_PATH = (
    ROOT / "fixtures" / "lab_confirmation.json"
)


def receive_confirmed_demo_report(
    db_path,
    confirmation_id,
    expected_version,
    staff_attested,
):
    if staff_attested is not True:
        raise ValueError("Explicit staff attestation required")

    confirmation = json.loads(
        CONFIRMATION_PATH.read_text(encoding="utf-8")
    )

    if confirmation.get("fictional") is not True:
        raise ValueError("Nonfictional source rejected")

    if confirmation_id != confirmation["confirmation_id"]:
        raise ValueError("Unknown confirmation reference")

    if confirmation["status"] != "simulated_report_supplied":
        raise ValueError("Completed report not supplied")

    case = get_case(db_path, "CASE-001")

    if case is None:
        raise ValueError("Case not found")

    if case["version"] != expected_version:
        raise ValueError("Stale case version")

    packet = build_staff_review_packet(db_path)

    matching_orders = [
        order
        for order in packet["pending_orders"]
        if order["order_id"] == confirmation["verified_order_id"]
    ]

    if len(matching_orders) != 1:
        raise ValueError("Order is not pending")

    order = matching_orders[0]

    candidates = [
        candidate
        for candidate in order["candidates"]
        if (
            candidate["source_id"] == confirmation["record_id"]
            and candidate["external_reference"]
                == confirmation["external_reference"]
            and candidate["patient_reference_matches"] is True
        )
    ]

    if len(candidates) != 1:
        raise ValueError("Lab candidate mismatch")

    report = confirmation["report"]

    if (
        report["patient_id"] != case["patient_id"]
        or report["patient_id"] != confirmation["patient_id"]
        or report["order_id"] != order["order_id"]
        or report["test_code"] != order["test_code"]
        or report["test_code"] != confirmation["test_code"]
    ):
        raise ValueError("Report identifiers do not match")

    ingest_report(
        db_path,
        "CASE-001",
        report,
        expected_version=expected_version,
        actor_id="STAFF-01",
    )

    updated = get_case(db_path, "CASE-001")

    return {
        "case_id": "CASE-001",
        "case_version": updated["version"],
        "confirmation_source_id": confirmation_id,
        "report_id": report["report_id"],
        "action": "SIMULATED_STAFF_VERIFIED_REPORT_RECEIPT",
        "next_step": "AWAITING_CLINICIAN_REVIEW",
        "data_mode": "fictional",
    }
