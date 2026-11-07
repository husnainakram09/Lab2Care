"""Patient-facing administrative status for fictional follow-up cases.

This is a pure read model, not an authorization service.
Approval and delivery records must eventually come from trusted,
server-side stores, never directly from a patient request.
"""

from core.reconcile import reconcile_case


MESSAGES = {
    "AWAITING_REPORTS":
        "Some ordered reports are still pending. "
        "The clinic is tracking them.",
    "STAFF_REVIEW_REQUIRED":
        "The clinic is checking a report detail. "
        "Follow-up is still pending.",
    "AWAITING_CLINICIAN_REVIEW":
        "Your reports are awaiting clinician review.",
    "APPROVED_FOR_COMMUNICATION":
        "Your clinician has approved follow-up instructions. "
        "The clinic is preparing your update.",
    "DELIVERY_UNCONFIRMED":
        "The clinic is sending your approved update. "
        "Delivery has not yet been confirmed.",
    "DELIVERY_FAILED":
        "Delivery could not be confirmed. "
        "Clinic staff will need to follow up.",
    "DELIVERED":
        "Your clinician-approved follow-up update "
        "has been delivered.",
    "ACKNOWLEDGED":
        "You acknowledged receiving the update. "
        "Any further follow-up is tracked separately.",
}

DELIVERY_STATES = {
    "queued", "sent", "unknown", "failed", "delivered"
}

# Internal outbox worker states are not patient states. A message
# superseded for the current case version lost its authorization,
# so it cannot be sent and staff must follow up.
OUTBOX_TO_DELIVERY_STATUS = {
    "queued": "queued",
    "sending": "unknown",
    "sent": "sent",
    "unknown": "unknown",
    "failed": "failed",
    "delivered": "delivered",
    "superseded": "failed",
}


def delivery_from_outbox(notification):
    """Map a stored outbox row to a patient-safe delivery record."""

    if notification is None:
        return None

    status = OUTBOX_TO_DELIVERY_STATUS.get(notification["status"])

    if status is None:
        return None

    return {
        "case_version": notification["case_version"],
        "status": status,
    }


def build_patient_status(
    case,
    *,
    approval=None,
    delivery=None,
    acknowledged=False,
):
    """Derive patient-safe status from trusted workflow records.

    No medical result values, interpretation or treatment advice
    are returned. This function performs no database writes.
    """
    if not isinstance(case, dict) or case.get("fictional") is not True:
        raise ValueError("A fictional case is required")

    version = case.get("version")
    if type(version) is not int or version < 1:
        raise ValueError("Invalid case version")

    if approval is not None and not isinstance(approval, dict):
        raise ValueError("Invalid approval record")

    if delivery is not None and not isinstance(delivery, dict):
        raise ValueError("Invalid delivery record")

    if type(acknowledged) is not bool:
        raise ValueError("acknowledged must be boolean")

    reconciliation = reconcile_case(
        case["patient_id"],
        case["orders"],
        case["reports"],
    )

    ordered = len(case["orders"])
    received = len(reconciliation["accepted_report_ids"])
    missing = len(reconciliation["missing_order_ids"])

    approval_outdated = (
        approval is not None
        and approval.get("case_version") != version
    )

    current_approval = (
        approval is not None
        and type(approval.get("case_version")) is int
        and approval["case_version"] == version
        and approval.get("decision") == "approved"
    )

    if reconciliation["quarantined"]:
        state = "STAFF_REVIEW_REQUIRED"

    elif missing:
        state = "AWAITING_REPORTS"

    elif not current_approval:
        state = "AWAITING_CLINICIAN_REVIEW"

    elif delivery is None or delivery.get("case_version") != version:
        state = "APPROVED_FOR_COMMUNICATION"

    else:
        delivery_status = delivery.get("status")

        if delivery_status not in DELIVERY_STATES:
            raise ValueError("Invalid delivery status")

        if delivery_status == "failed":
            state = "DELIVERY_FAILED"

        elif delivery_status != "delivered":
            state = "DELIVERY_UNCONFIRMED"

        else:
            state = "ACKNOWLEDGED" if acknowledged else "DELIVERED"

        if acknowledged and delivery_status != "delivered":
            raise ValueError(
                "Acknowledgement requires confirmed delivery"
            )

    return {
        "case_id": case["case_id"],
        "state": state,
        "message": MESSAGES[state],
        "ordered_count": ordered,
        "received_count": received,
        "pending_count": missing,
        "approval_outdated": approval_outdated,
    }
