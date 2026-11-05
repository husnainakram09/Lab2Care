"""Append-only simulated clinician approvals for fictional cases.

This is a domain-level authorization check, not authentication.
A future API must obtain clinician_id from a verified server session.
Never expose demo actor seeding as a public endpoint.
"""

from core.reconcile import reconcile_case
from storage.db import connect_db
from storage.repository import StaleCaseVersion


class ApprovalNotReady(ValueError):
    """Required reports are missing or conflicting."""


class ApprovalForbidden(PermissionError):
    """Actor lacks active clinician authorization."""


class ApprovalConflict(RuntimeError):
    """A different approval exists for this case version."""


def initialize_approval_schema(db_path):
    """Add approval tables to an initialized SQLite database."""

    with connect_db(db_path) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS demo_actors (
                actor_id TEXT PRIMARY KEY,
                role TEXT NOT NULL
                    CHECK (role IN ('clinician', 'coordinator')),
                active INTEGER NOT NULL DEFAULT 1
                    CHECK (active IN (0, 1))
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS clinician_approvals (
                approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                case_version INTEGER NOT NULL,
                clinician_id TEXT NOT NULL,
                instructions TEXT NOT NULL
                    CHECK (length(instructions) > 0),
                created_at TEXT NOT NULL DEFAULT
                    (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE (case_id, case_version),
                FOREIGN KEY (case_id) REFERENCES cases(case_id),
                FOREIGN KEY (clinician_id)
                    REFERENCES demo_actors(actor_id)
            )
        """)

        db.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_approval_update
            BEFORE UPDATE ON clinician_approvals
            BEGIN
                SELECT RAISE(ABORT, 'approvals are append-only');
            END
        """)

        db.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_approval_delete
            BEFORE DELETE ON clinician_approvals
            BEGIN
                SELECT RAISE(ABORT, 'approvals are append-only');
            END
        """)


def seed_demo_actor(db_path, actor_id, role):
    """Local setup only. Must not be a public application action."""

    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValueError("actor_id is required")

    if role not in ("clinician", "coordinator"):
        raise ValueError("Unsupported demo role")

    with connect_db(db_path) as db:
        db.execute(
            "INSERT INTO demo_actors (actor_id, role) VALUES (?, ?)",
            (actor_id, role),
        )


def approve_followup(
    db_path,
    case_id,
    *,
    clinician_id,
    expected_version,
    instructions,
):
    """Record one clinician-authored, version-bound approval.

    The standard demo path requires a complete, conflict-free packet.
    This is not a general clinical escalation policy.
    """

    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id is required")

    if not isinstance(clinician_id, str) or not clinician_id.strip():
        raise ValueError("clinician_id is required")

    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("expected_version must be positive")

    if (
        not isinstance(instructions, str)
        or not 1 <= len(instructions.strip()) <= 500
    ):
        raise ValueError("Instructions must contain 1-500 characters")

    with connect_db(db_path) as db:
        # Lock before checking the current version.
        db.execute("BEGIN IMMEDIATE")

        actor = db.execute(
            "SELECT role, active FROM demo_actors WHERE actor_id = ?",
            (clinician_id,),
        ).fetchone()

        if actor != ("clinician", 1):
            raise ApprovalForbidden("An active clinician is required")

        case = db.execute(
            """
            SELECT patient_id, version
            FROM cases
            WHERE case_id = ? AND fictional = 1
            """,
            (case_id,),
        ).fetchone()

        if case is None:
            raise KeyError(f"Unknown fictional case: {case_id}")

        patient_id, current_version = case

        if current_version != expected_version:
            raise StaleCaseVersion(
                f"Expected {expected_version}, current {current_version}"
            )

        order_rows = db.execute(
            """
            SELECT order_id, patient_id, test_code
            FROM test_orders
            WHERE case_id = ?
            ORDER BY rowid
            """,
            (case_id,),
        ).fetchall()

        report_rows = db.execute(
            """
            SELECT report_id, order_id, patient_id, test_code
            FROM reports
            WHERE case_id = ?
            ORDER BY rowid
            """,
            (case_id,),
        ).fetchall()

        orders = [
            {
                "order_id": row[0],
                "patient_id": row[1],
                "test_code": row[2],
            }
            for row in order_rows
        ]

        reports = [
            {
                "report_id": row[0],
                "order_id": row[1],
                "patient_id": row[2],
                "test_code": row[3],
            }
            for row in report_rows
        ]

        result = reconcile_case(patient_id, orders, reports)

        if not orders or not result["ready_for_doctor_review"]:
            raise ApprovalNotReady(
                "Packet is missing or has unresolved evidence"
            )

        previous = db.execute(
            """
            SELECT approval_id, clinician_id, instructions
            FROM clinician_approvals
            WHERE case_id = ? AND case_version = ?
            """,
            (case_id, current_version),
        ).fetchone()

        if previous is not None:
            if previous[1:] == (clinician_id, instructions):
                return {
                    "outcome": "duplicate",
                    "approval_id": previous[0],
                    "case_version": current_version,
                }

            raise ApprovalConflict(
                "This case version already has an approval"
            )

        cursor = db.execute(
            """
            INSERT INTO clinician_approvals
                (case_id, case_version, clinician_id, instructions)
            VALUES (?, ?, ?, ?)
            """,
            (
                case_id,
                current_version,
                clinician_id,
                instructions,
            ),
        )

        return {
            "outcome": "approved",
            "approval_id": cursor.lastrowid,
            "case_version": current_version,
        }


def get_current_approval(db_path, case_id):
    """Return an approval only if its case version is still current."""

    with connect_db(db_path) as db:
        row = db.execute(
            """
            SELECT a.approval_id, a.case_version,
                   a.clinician_id, a.instructions
            FROM clinician_approvals AS a
            JOIN cases AS c
              ON c.case_id = a.case_id
             AND c.version = a.case_version
            WHERE a.case_id = ?
            """,
            (case_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "approval_id": row[0],
        "case_version": row[1],
        "clinician_id": row[2],
        "instructions": row[3],
        "decision": "approved",
    }
