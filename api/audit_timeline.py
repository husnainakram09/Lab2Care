
"""Read-only audit timeline for the fictional patient case.

Shows persisted administrative events, not inferred clinical
outcomes. Delivery status is a snapshot, not a timed event.
"""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from storage.repository import get_case


def build_case_timeline(db_path, case_id="CASE-001"):
    case = get_case(db_path, case_id)

    if case is None:
        raise ValueError("Fictional case not found")

    events = []
    notification_snapshot = None

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row

        reports = conn.execute(
            """
            SELECT event_id, case_version, event_type,
                   report_id, actor_id, created_at
            FROM case_events
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchall()

        for row in reports:
            events.append({
                "kind": "case_event",
                "title": "Report event recorded",
                "detail": (
                    f"Report {row['report_id']} recorded by "
                    f"{row['actor_id']}. "
                    f"Event type: {row['event_type']}."
                ),
                "case_version": row["case_version"],
                "occurred_at": row["created_at"],
                "source": f"case_events:{row['event_id']}",
                "_rank": 1,
            })

        approvals = conn.execute(
            """
            SELECT approval_id, case_version, clinician_id,
                   created_at
            FROM clinician_approvals
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchall()

        for row in approvals:
            events.append({
                "kind": "clinician_approval",
                "title": "Clinician approval recorded",
                "detail": (
                    "Fictional clinician "
                    f"{row['clinician_id']} approved "
                    "administrative follow-up instructions."
                ),
                "case_version": row["case_version"],
                "occurred_at": row["created_at"],
                "source": (
                    f"clinician_approvals:{row['approval_id']}"
                ),
                "_rank": 2,
            })

        notifications = conn.execute(
            """
            SELECT notification_id, case_version, requested_by,
                   status, created_at
            FROM notification_outbox
            WHERE case_id = ?
            ORDER BY notification_id
            """,
            (case_id,),
        ).fetchall()

        for row in notifications:
            events.append({
                "kind": "notification_queued",
                "title": "Notification queued",
                "detail": (
                    "Fictional staff "
                    f"{row['requested_by']} requested "
                    "the clinician-approved notification."
                ),
                "case_version": row["case_version"],
                "occurred_at": row["created_at"],
                "source": (
                    f"notification_outbox:"
                    f"{row['notification_id']}"
                ),
                "_rank": 3,
            })

            if row["case_version"] == case["version"]:
                notification_snapshot = {
                    "notification_id": row["notification_id"],
                    "status": row["status"],
                }

        acknowledgements = conn.execute(
            """
            SELECT notification_id, case_version, actor_id,
                   acknowledged_at
            FROM patient_acknowledgements
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchall()

        for row in acknowledgements:
            events.append({
                "kind": "patient_acknowledgement",
                "title": "Message receipt acknowledged",
                "detail": (
                    "Fictional patient actor "
                    f"{row['actor_id']} acknowledged receipt "
                    f"of notification {row['notification_id']}."
                ),
                "case_version": row["case_version"],
                "occurred_at": row["acknowledged_at"],
                "source": (
                    "patient_acknowledgements:"
                    f"{row['notification_id']}"
                ),
                "_rank": 4,
            })

    def event_sort_key(event):
        raw = event["occurred_at"]

        if raw is None:
            timestamp = "9999-12-31 23:59:59"
        else:
            parsed = datetime.fromisoformat(
                raw.replace("Z", "+00:00")
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            timestamp = parsed.astimezone(
                timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")

        return (
            timestamp,
            event["case_version"],
            event["_rank"],
            event["source"],
        )

    events.sort(key=event_sort_key)

    for event in events:
        del event["_rank"]

    return {
        "case_id": case_id,
        "case_version": case["version"],
        "events": events,
        "notification_snapshot": notification_snapshot,
        "baseline_note": (
            "The fictional case begins with preloaded orders "
            "and reports. These initial fixture records are "
            "not represented as audit events."
        ),
        "timestamp_resolution": "seconds",
        "delivery_timing_note": (
            "The notification outbox stores creation time "
            "and current status. It does not independently "
            "record the exact time delivery was verified."
        ),
        "data_mode": "fictional",
        "read_only": True,
    }
