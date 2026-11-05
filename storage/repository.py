"""Persistent storage for fictional follow-up cases."""

from storage.db import connect_db


def create_case(db_path, case):
    """Atomically save one fictional case and its source records."""

    if case.get("fictional") is not True:
        raise ValueError("Only explicitly fictional cases are allowed")

    with connect_db(db_path) as db:
        db.execute(
            """
            INSERT INTO cases
                (case_id, patient_id, version, fictional)
            VALUES (?, ?, ?, ?)
            """,
            (
                case["case_id"],
                case["patient_id"],
                case.get("version", 1),
                1,
            ),
        )

        for order in case["orders"]:
            db.execute(
                """
                INSERT INTO test_orders
                    (case_id, order_id, patient_id, test_code)
                VALUES (?, ?, ?, ?)
                """,
                (
                    case["case_id"],
                    order["order_id"],
                    order["patient_id"],
                    order["test_code"],
                ),
            )

        for report in case["reports"]:
            db.execute(
                """
                INSERT INTO reports
                    (case_id, report_id, order_id,
                     patient_id, test_code, source_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    case["case_id"],
                    report["report_id"],
                    report["order_id"],
                    report["patient_id"],
                    report["test_code"],
                    report.get("source_text"),
                ),
            )


def get_case(db_path, case_id):
    """Reconstruct a stored case without changing its evidence."""

    with connect_db(db_path) as db:
        row = db.execute(
            """
            SELECT case_id, patient_id, version, fictional
            FROM cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if row is None:
            return None

        orders = db.execute(
            """
            SELECT order_id, patient_id, test_code
            FROM test_orders
            WHERE case_id = ?
            ORDER BY rowid
            """,
            (case_id,),
        ).fetchall()

        reports = db.execute(
            """
            SELECT report_id, order_id, patient_id,
                   test_code, source_text
            FROM reports
            WHERE case_id = ?
            ORDER BY rowid
            """,
            (case_id,),
        ).fetchall()

    report_records = []

    for report in reports:
        item = {
            "report_id": report[0],
            "order_id": report[1],
            "patient_id": report[2],
            "test_code": report[3],
        }

        if report[4] is not None:
            item["source_text"] = report[4]

        report_records.append(item)

    return {
        "fictional": bool(row[3]),
        "case_id": row[0],
        "patient_id": row[1],
        "version": row[2],
        "orders": [
            {
                "order_id": order[0],
                "patient_id": order[1],
                "test_code": order[2],
            }
            for order in orders
        ],
        "reports": report_records,
    }


class StaleCaseVersion(RuntimeError):
    """The caller used an outdated case version."""


class ReportConflict(ValueError):
    """A report ID already exists with different content."""


def ingest_report(
    db_path,
    case_id,
    report,
    *,
    expected_version,
    actor_id="simulated-lab",
):
    """Ingest one fictional report atomically.

    Exact retries are harmless. Conflicting retries and stale
    new writes are rejected. No clinical interpretation occurs.
    """
    required = ("report_id", "order_id",
                "patient_id", "test_code")

    for field in required:
        value = report.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid report field: {field}")

    if (type(expected_version) is not int
            or expected_version < 1):
        raise ValueError("expected_version must be positive")

    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValueError("actor_id is required")

    incoming = (
        report["order_id"],
        report["patient_id"],
        report["test_code"],
        report.get("source_text"),
    )

    with connect_db(db_path) as db:
        # Acquire the writer lock before reading case state.
        db.execute("BEGIN IMMEDIATE")

        case = db.execute(
            """
            SELECT version FROM cases
            WHERE case_id = ? AND fictional = 1
            """,
            (case_id,),
        ).fetchone()

        if case is None:
            raise KeyError(f"Unknown case: {case_id}")

        current_version = case[0]

        existing = db.execute(
            """
            SELECT order_id, patient_id, test_code,
                   source_text
            FROM reports
            WHERE case_id = ? AND report_id = ?
            """,
            (case_id, report["report_id"]),
        ).fetchone()

        # Idempotent retries take precedence over stale-version
        # rejection because the requested write already succeeded.
        if existing is not None:
            if existing == incoming:
                return {
                    "outcome": "duplicate",
                    "case_version": current_version,
                }

            raise ReportConflict(
                "Report ID exists with conflicting content"
            )

        if expected_version != current_version:
            raise StaleCaseVersion(
                f"Expected {expected_version}, "
                f"current {current_version}"
            )

        db.execute(
            """
            INSERT INTO reports
                (case_id, report_id, order_id,
                 patient_id, test_code, source_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                report["report_id"],
                *incoming,
            ),
        )

        new_version = current_version + 1

        db.execute(
            """
            UPDATE cases
            SET version = ?
            WHERE case_id = ? AND version = ?
            """,
            (new_version, case_id, current_version),
        )

        db.execute(
            """
            INSERT INTO case_events
                (case_id, case_version, event_type,
                 report_id, actor_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                case_id,
                new_version,
                "REPORT_INGESTED",
                report["report_id"],
                actor_id,
            ),
        )

        return {
            "outcome": "ingested",
            "case_version": new_version,
        }
