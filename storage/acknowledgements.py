
"""Append-only fictional patient receipt acknowledgements.

This records simulated message receipt, not acceptance of
medical instructions or completion of clinical follow-up.
"""

import sqlite3
from contextlib import closing

from core.followup import build_patient_status
from storage.approvals import get_current_approval
from storage.outbox import get_notification
from storage.repository import get_case


CASE_ID = "CASE-001"


def initialize_acknowledgement_schema(db_path):
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS patient_acknowledgements (
                notification_id INTEGER PRIMARY KEY,
                case_id TEXT NOT NULL,
                case_version INTEGER NOT NULL,
                actor_id TEXT NOT NULL,
                acknowledged_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (notification_id)
                    REFERENCES notification_outbox(notification_id)
            );

            CREATE TRIGGER IF NOT EXISTS acknowledgement_no_update
            BEFORE UPDATE ON patient_acknowledgements
            BEGIN
                SELECT RAISE(ABORT, 'Acknowledgements are immutable');
            END;

            CREATE TRIGGER IF NOT EXISTS acknowledgement_no_delete
            BEFORE DELETE ON patient_acknowledgements
            BEGIN
                SELECT RAISE(ABORT, 'Acknowledgements are immutable');
            END;
        """)


def is_notification_acknowledged(db_path, notification_id):
    with closing(sqlite3.connect(str(db_path))) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM patient_acknowledgements
            WHERE notification_id = ?
            """,
            (notification_id,),
        ).fetchone()

    return row is not None


def record_demo_acknowledgement(
    db_path, *, expected_version, patient_attested
):
    if patient_attested is not True:
        raise ValueError(
            "Explicit fictional patient acknowledgement required"
        )

    with closing(
        sqlite3.connect(str(db_path), timeout=5.0)
    ) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")

        try:
            case = get_case(db_path, CASE_ID)

            if case is None:
                raise ValueError("Fictional case not found")

            if case["version"] != expected_version:
                raise ValueError("Stale case version")

            row = conn.execute(
                """
                SELECT notification_id
                FROM notification_outbox
                WHERE case_id = ? AND case_version = ?
                ORDER BY notification_id DESC
                LIMIT 1
                """,
                (CASE_ID, expected_version),
            ).fetchone()

            if row is None:
                raise ValueError("No notification available")

            notification_id = row[0]
            notification = get_notification(
                db_path, notification_id
            )

            approval = get_current_approval(
                db_path, CASE_ID
            )

            state = build_patient_status(
                case,
                approval=approval,
                delivery=notification,
            )["state"]

            if state != "DELIVERED":
                raise ValueError(
                    "Verified delivery required before acknowledgement"
                )

            existing = conn.execute(
                """
                SELECT 1 FROM patient_acknowledgements
                WHERE notification_id = ?
                """,
                (notification_id,),
            ).fetchone()

            if existing is not None:
                raise ValueError(
                    "Notification already acknowledged"
                )

            conn.execute(
                """
                INSERT INTO patient_acknowledgements
                    (notification_id, case_id, case_version, actor_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    notification_id,
                    CASE_ID,
                    expected_version,
                    "PAT-001",
                ),
            )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

    return {
        "action": "SIMULATED_PATIENT_ACKNOWLEDGEMENT",
        "state": "ACKNOWLEDGED",
        "notification_id": notification_id,
        "case_version": expected_version,
        "data_mode": "fictional",
    }
