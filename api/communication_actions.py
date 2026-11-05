
"""Fictional notification queue and delivery integration.

Local demo only. No real notification service.
"""

import sqlite3
from pathlib import Path

from core.followup import build_patient_status
from services.delivery_worker import dispatch_notification
from services.fake_notification import FakeNotificationGateway
from storage.approvals import get_current_approval
from storage.outbox import (
    get_notification,
    queue_approved_notification,
)
from storage.repository import get_case


CASE_ID = "CASE-001"


def get_current_notification(db_path):
    """Find the persisted notification for the active case version."""
    case = get_case(db_path, CASE_ID)

    if case is None:
        return None

    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute(
            """
            SELECT notification_id
            FROM notification_outbox
            WHERE case_id = ? AND case_version = ?
            ORDER BY notification_id DESC
            LIMIT 1
            """,
            (CASE_ID, case["version"]),
        ).fetchone()

    if row is None:
        return None

    return get_notification(db_path, row[0])


def queue_demo_update(db_path, *, expected_version):
    case = get_case(db_path, CASE_ID)

    if case is None:
        raise ValueError("Fictional case not found")

    if case["version"] != expected_version:
        raise ValueError("Stale case version")

    if get_current_notification(db_path) is not None:
        raise ValueError(
            "Notification already exists for this case version"
        )

    approval = get_current_approval(db_path, CASE_ID)

    state = build_patient_status(
        case,
        approval=approval,
    )["state"]

    if state != "APPROVED_FOR_COMMUNICATION":
        raise ValueError(
            "Current clinician approval required before queuing"
        )

    result = queue_approved_notification(
        db_path,
        CASE_ID,
        expected_version=expected_version,
        requester_id="STAFF-01",
    )

    return {
        **result,
        "action": "SIMULATED_NOTIFICATION_QUEUED",
        "data_mode": "fictional",
    }


def deliver_demo_update(db_path, *, expected_version):
    case = get_case(db_path, CASE_ID)

    if case is None:
        raise ValueError("Fictional case not found")

    if case["version"] != expected_version:
        raise ValueError("Stale case version")

    notification = get_current_notification(db_path)

    if notification is None:
        raise ValueError("No queued notification found")

    if notification["status"] != "queued":
        raise ValueError(
            "Notification is not in the queued state"
        )

    destination_db = (
        Path(db_path).with_name("destination.db")
    )

    gateway = FakeNotificationGateway(destination_db)

    result = dispatch_notification(
        db_path,
        notification["notification_id"],
        gateway,
    )

    updated = get_notification(
        db_path,
        notification["notification_id"],
    )

    return {
        "action": "SIMULATED_NOTIFICATION_DELIVERY",
        "notification_id": notification["notification_id"],
        "outcome": result["outcome"],
        "notification_status": updated["status"],
        "fictional_destination_receipts":
            gateway.delivery_count(),
        "case_version": case["version"],
        "data_mode": "fictional",
    }
