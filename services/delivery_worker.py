"""Controlled delivery worker for the fictional notification gateway."""

from storage.db import connect_db
from storage.outbox import (
    reclaim_unconfirmed_notification,
    reserve_notification,
)


class SimulatedWorkerCrash(RuntimeError):
    pass


def _preflight(db_path, notification_id):
    """Recheck authorization and case freshness before execution."""

    with connect_db(db_path) as db:
        db.execute("BEGIN IMMEDIATE")

        row = db.execute(
            """
            SELECT n.status, n.case_version, c.version,
                   a.approval_id, clinician.active
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

        status, approved_version, current_version, approval, active = row

        if status != "sending":
            return False

        if (
            approved_version != current_version
            or approval is None
            or active != 1
        ):
            db.execute(
                """
                UPDATE notification_outbox
                SET status = 'superseded'
                WHERE notification_id = ?
                """,
                (notification_id,),
            )
            return False

        return True


def verify_delivery(db_path, notification_id, gateway):
    """Reconcile application state with the test destination.

    Never infer delivery merely because a send was attempted.
    """

    with connect_db(db_path) as db:
        db.execute("BEGIN IMMEDIATE")

        row = db.execute(
            """
            SELECT n.status, n.case_version,
                   n.idempotency_key, n.instructions,
                   c.version
            FROM notification_outbox AS n
            JOIN cases AS c ON c.case_id = n.case_id
            WHERE n.notification_id = ?
            """,
            (notification_id,),
        ).fetchone()

        if row is None:
            raise KeyError("Unknown notification")

        status, case_version, key, instructions, current_version = row

        if status not in ("sending", "unknown"):
            return {"outcome": status}

        receipt = gateway.lookup(key)

        if (
            receipt is not None
            and receipt["body"] == instructions
            and receipt["status"] == "delivered"
        ):
            # Preserve the observed historical delivery, even if
            # the case has changed since the external write.
            db.execute(
                """
                UPDATE notification_outbox
                SET status = 'delivered'
                WHERE notification_id = ?
                """,
                (notification_id,),
            )

            return {
                "outcome": "delivered",
                "historical_version": (
                    case_version != current_version
                ),
            }

        if case_version != current_version:
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
            SET status = 'unknown'
            WHERE notification_id = ?
            """,
            (notification_id,),
        )

        return {"outcome": "unknown"}


def dispatch_notification(
    db_path,
    notification_id,
    gateway,
    *,
    simulate_crash_after_send=False,
):
    """Claim, send, and verify a fictional notification."""

    claimed = reserve_notification(db_path, notification_id)

    if claimed["outcome"] != "claimed":
        return claimed

    return _send_claimed(
        db_path,
        notification_id,
        gateway,
        claimed,
        simulate_crash_after_send=simulate_crash_after_send,
    )


def recover_notification(db_path, notification_id, gateway):
    """Resolve a delivery whose outcome was never confirmed.

    The destination is checked first. Only when it holds no receipt
    is the message resent, under the same idempotency key, so the
    destination cannot record it twice.
    """

    verified = verify_delivery(db_path, notification_id, gateway)

    if verified["outcome"] != "unknown":
        return verified

    claimed = reclaim_unconfirmed_notification(
        db_path, notification_id
    )

    if claimed["outcome"] != "claimed":
        return claimed

    return _send_claimed(db_path, notification_id, gateway, claimed)


def _send_claimed(
    db_path,
    notification_id,
    gateway,
    claimed,
    *,
    simulate_crash_after_send=False,
):
    if not _preflight(db_path, notification_id):
        return {"outcome": "superseded"}

    try:
        gateway.send(
            claimed["idempotency_key"],
            claimed["instructions"],
        )
    except Exception:
        # Remote outcome may be ambiguous. Never blindly resend.
        with connect_db(db_path) as db:
            db.execute(
                """
                UPDATE notification_outbox
                SET status = 'unknown'
                WHERE notification_id = ?
                  AND status = 'sending'
                """,
                (notification_id,),
            )
        raise

    if simulate_crash_after_send:
        raise SimulatedWorkerCrash(
            "Crash after destination write, before local receipt"
        )

    return verify_delivery(db_path, notification_id, gateway)
