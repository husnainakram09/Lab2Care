
"""Current patient-facing status of the shared fictional case.

Read-only. Combines the case, current approval, current-version
notification and acknowledgement exactly as the patient sees them.
"""

from api.communication_actions import get_current_notification
from core.followup import build_patient_status, delivery_from_outbox
from storage.acknowledgements import is_notification_acknowledged
from storage.approvals import get_current_approval
from storage.repository import get_case


CASE_ID = "CASE-001"


def read_active_case_status(db_path):
    """Return (case, status), or (None, None) if the case is missing."""

    case = get_case(db_path, CASE_ID)

    if case is None:
        return None, None

    approval = get_current_approval(db_path, CASE_ID)
    notification = get_current_notification(db_path)
    delivery = delivery_from_outbox(notification)

    acknowledged = (
        delivery is not None
        and delivery["status"] == "delivered"
        and is_notification_acknowledged(
            db_path,
            notification["notification_id"],
        )
    )

    status = build_patient_status(
        case,
        approval=approval,
        delivery=delivery,
        acknowledged=acknowledged,
    )

    return case, status
