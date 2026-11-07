"""Persistent outbox for simulated, clinician-approved follow-up.

This module does not send messages. The future worker must use
an idempotent test endpoint and independently verify delivery.
"""

from storage.db import connect_db
from storage.repository import StaleCaseVersion


class NotificationNotApproved(ValueError):
    pass


class NotificationForbidden(PermissionError):
    pass


def initialize_outbox_schema(db_path):
    with connect_db(db_path) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS notification_outbox (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                case_version INTEGER NOT NULL,
                approval_id INTEGER NOT NULL,
                requested_by TEXT NOT NULL,
                instructions TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN (
                        'queued', 'sending', 'sent',
                        'unknown', 'failed', 'delivered',
                        'superseded'
                    )),
                created_at TEXT NOT NULL DEFAULT
                    (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE (case_id, case_version),
                FOREIGN KEY (case_id) REFERENCES cases(case_id),
                FOREIGN KEY (approval_id)
                    REFERENCES clinician_approvals(approval_id),
                FOREIGN KEY (requested_by)
                    REFERENCES demo_actors(actor_id)
            )
        """)


def queue_approved_notification(
    db_path,
    case_id,
    *,
    expected_version,
    requester_id,
):
    """Queue the exact clinician-approved instructions.

    This is a demo domain function. The API must authenticate
    requester_id instead of accepting an untrusted actor string.
    """

    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id is required")

    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("Expected version must be positive")

    if not isinstance(requester_id, str) or not requester_id.strip():
        raise ValueError("requester_id is required")

    with connect_db(db_path) as db:
        db.execute("BEGIN IMMEDIATE")

        actor = db.execute(
            """
            SELECT role, active FROM demo_actors
            WHERE actor_id = ?
            """,
            (requester_id,),
        ).fetchone()

        if actor not in (("clinician", 1), ("coordinator", 1)):
            raise NotificationForbidden(
                "An active authorized clinic actor is required"
            )

        case = db.execute(
            """
            SELECT version FROM cases
            WHERE case_id = ? AND fictional = 1
            """,
            (case_id,),
        ).fetchone()

        if case is None:
            raise KeyError(f"Unknown fictional case: {case_id}")

        current_version = case[0]

        if current_version != expected_version:
            raise StaleCaseVersion(
                f"Expected {expected_version}, current {current_version}"
            )

        approval = db.execute(
            """
            SELECT a.approval_id, a.instructions
            FROM clinician_approvals AS a
            JOIN demo_actors AS clinician
              ON clinician.actor_id = a.clinician_id
            WHERE a.case_id = ?
              AND a.case_version = ?
              AND clinician.role = 'clinician'
              AND clinician.active = 1
            """,
            (case_id, current_version),
        ).fetchone()

        if approval is None:
            raise NotificationNotApproved(
                "No current active clinician approval"
            )

        approval_id, instructions = approval

        existing = db.execute(
            """
            SELECT notification_id FROM notification_outbox
            WHERE case_id = ? AND case_version = ?
            """,
            (case_id, current_version),
        ).fetchone()

        if existing is not None:
            return {
                "outcome": "duplicate",
                "notification_id": existing[0],
                "case_version": current_version,
            }

        key = f"demo-followup:{case_id}:{current_version}:{approval_id}"

        cursor = db.execute(
            """
            INSERT INTO notification_outbox (
                case_id, case_version, approval_id,
                requested_by, instructions, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                case_id, current_version, approval_id,
                requester_id, instructions, key,
            ),
        )

        return {
            "outcome": "queued",
            "notification_id": cursor.lastrowid,
            "case_version": current_version,
        }


def get_notification(db_path, notification_id):
    """Internal read. Do not expose instructions publicly."""

    with connect_db(db_path) as db:
        row = db.execute(
            """
            SELECT notification_id, case_id, case_version,
                   approval_id, instructions, idempotency_key,
                   status
            FROM notification_outbox
            WHERE notification_id = ?
            """,
            (notification_id,),
        ).fetchone()

    if row is None:
        return None

    names = (
        "notification_id", "case_id", "case_version",
        "approval_id", "instructions", "idempotency_key",
        "status",
    )
    return dict(zip(names, row))


def reserve_notification(db_path, notification_id):
    """Internal worker claim; no external message is sent here.

    A stale queued message becomes superseded. A message may
    only be claimed once while it remains in 'sending'.
    """

    with connect_db(db_path) as db:
        db.execute("BEGIN IMMEDIATE")

        row = db.execute(
            """
            SELECT n.status, n.case_version, n.approval_id,
                   n.idempotency_key, n.instructions,
                   c.version, a.approval_id, clinician.active
            FROM notification_outbox AS n
            JOIN cases AS c ON c.case_id = n.case_id
            LEFT JOIN clinician_approvals AS a
              ON a.approval_id = n.approval_id
             AND a.case_id = n.case_id
             AND a.case_version = n.case_version
            LEFT JOIN demo_actors AS clinician
              ON clinician.actor_id = a.clinician_id
             AND clinician.role = 'clinician'
            WHERE n.notification_id = ?
            """,
            (notification_id,),
        ).fetchone()

        if row is None:
            raise KeyError("Unknown notification")

        (status, version, approval_id, key, instructions,
         current_version, linked_approval, clinician_active) = row

        if status != "queued":
            return {"outcome": "not_queued", "status": status}

        if (
            version != current_version
            or linked_approval != approval_id
            or clinician_active != 1
        ):
            db.execute(
                """
                UPDATE notification_outbox
                SET status = 'superseded'
                WHERE notification_id = ?
                """,
                (notification_id,),
            )
            return {"outcome": "superseded"}

        db.execute(
            """
            UPDATE notification_outbox
            SET status = 'sending'
            WHERE notification_id = ?
            """,
            (notification_id,),
        )

        return {
            "outcome": "claimed",
            "idempotency_key": key,
            "instructions": instructions,
            "case_version": version,
        }


def reclaim_unconfirmed_notification(db_path, notification_id):
    """Internal worker claim for a delivery left unconfirmed.

    Only an 'unknown' message is claimed. The caller must recheck
    authorization and reuse the original idempotency key.
    """

    with connect_db(db_path) as db:
        db.execute("BEGIN IMMEDIATE")

        row = db.execute(
            """
            SELECT status, case_version, idempotency_key, instructions
            FROM notification_outbox
            WHERE notification_id = ?
            """,
            (notification_id,),
        ).fetchone()

        if row is None:
            raise KeyError("Unknown notification")

        status, version, key, instructions = row

        if status != "unknown":
            return {"outcome": "not_unknown", "status": status}

        db.execute(
            """
            UPDATE notification_outbox
            SET status = 'sending'
            WHERE notification_id = ?
            """,
            (notification_id,),
        )

        return {
            "outcome": "claimed",
            "idempotency_key": key,
            "instructions": instructions,
            "case_version": version,
        }
