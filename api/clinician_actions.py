
"""Simulated clinician approval for the fictional demo.

Not real authentication, medical advice, or clinical approval.
The AI agent cannot invoke this action.
"""

from core.followup import build_patient_status
from storage.approvals import (
    approve_followup,
    get_current_approval,
)
from storage.repository import get_case


DEMO_INSTRUCTIONS = (
    "Your three ordered reports have been received. "
    "Please contact the fictional clinic to discuss "
    "your follow-up arrangements. "
    "This simulated communication contains no diagnosis "
    "or treatment recommendation."
)


def simulate_clinician_approval(
    db_path,
    *,
    expected_version,
    clinician_attested,
):
    if clinician_attested is not True:
        raise ValueError(
            "Explicit simulated clinician attestation required"
        )

    case = get_case(db_path, "CASE-001")

    if case is None:
        raise ValueError("Fictional case not found")

    if case["version"] != expected_version:
        raise ValueError("Stale case version")

    current = build_patient_status(case)

    if current["state"] != "AWAITING_CLINICIAN_REVIEW":
        raise ValueError(
            "All reports must be received and require "
            "clinician review before approval"
        )

    approve_followup(
        db_path,
        "CASE-001",
        clinician_id="DOC-01",
        expected_version=expected_version,
        instructions=DEMO_INSTRUCTIONS,
    )

    approval = get_current_approval(
        db_path,
        "CASE-001",
    )

    updated_case = get_case(db_path, "CASE-001")

    status = build_patient_status(
        updated_case,
        approval=approval,
    )

    return {
        "case_id": "CASE-001",
        "case_version": updated_case["version"],
        "action": "SIMULATED_CLINICIAN_APPROVAL",
        "state": status["state"],
        "clinician_actor": "DOC-01",
        "notification_sent": False,
        "data_mode": "fictional",
    }
