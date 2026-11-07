"""Persistent fictional notification destination.

No real patients are contacted. A 'delivered' receipt means only
that this isolated test destination recorded the message.
"""

import sqlite3
from contextlib import closing


class FakeNotificationGateway:
    def __init__(self, db_path):
        self.db_path = str(db_path)

        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS deliveries (
                    idempotency_key TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (status = 'delivered')
                )
            """)

    def send(self, key, body):
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Idempotency key is required")

        if not isinstance(body, str) or not body.strip():
            raise ValueError("Message body is required")

        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("BEGIN IMMEDIATE")

            previous = db.execute(
                """
                SELECT body, status
                FROM deliveries
                WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()

            if previous is not None:
                if previous[0] != body:
                    raise ValueError(
                        "Same idempotency key, different message"
                    )

                return {
                    "idempotency_key": key,
                    "status": previous[1],
                    "replayed": True,
                }

            db.execute(
                """
                INSERT INTO deliveries
                    (idempotency_key, body, status)
                VALUES (?, ?, 'delivered')
                """,
                (key, body),
            )

        return {
            "idempotency_key": key,
            "status": "delivered",
            "replayed": False,
        }

    def lookup(self, key):
        """Read the destination's authoritative test receipt."""

        with closing(sqlite3.connect(self.db_path)) as db:
            row = db.execute(
                """
                SELECT idempotency_key, body, status
                FROM deliveries
                WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()

        if row is None:
            return None

        return {
            "idempotency_key": row[0],
            "body": row[1],
            "status": row[2],
        }

    def delivery_count(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            return db.execute(
                "SELECT COUNT(*) FROM deliveries"
            ).fetchone()[0]
