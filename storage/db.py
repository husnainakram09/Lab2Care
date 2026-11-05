"""SQLite storage for fictional follow-up cases."""

import sqlite3
from contextlib import contextmanager


@contextmanager
def connect_db(db_path):
    connection = sqlite3.connect(str(db_path))
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_db(db_path):
    with connect_db(db_path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
                    CHECK (version >= 1),
                fictional INTEGER NOT NULL
                    CHECK (fictional = 1)
            );

            CREATE TABLE IF NOT EXISTS test_orders (
                case_id TEXT NOT NULL,
                order_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                test_code TEXT NOT NULL,
                PRIMARY KEY (case_id, order_id),
                FOREIGN KEY (case_id)
                    REFERENCES cases(case_id)
            );

            CREATE TABLE IF NOT EXISTS reports (
                case_id TEXT NOT NULL,
                report_id TEXT NOT NULL,
                order_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                test_code TEXT NOT NULL,
                source_text TEXT,
                PRIMARY KEY (case_id, report_id),
                FOREIGN KEY (case_id)
                    REFERENCES cases(case_id)
            );

            CREATE TABLE IF NOT EXISTS case_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                case_version INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                report_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT
                    (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                FOREIGN KEY (case_id)
                    REFERENCES cases(case_id),
                UNIQUE (case_id, case_version)
            );

            CREATE TRIGGER IF NOT EXISTS prevent_event_update
            BEFORE UPDATE ON case_events
            BEGIN
                SELECT RAISE(ABORT, 'events are append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_event_delete
            BEFORE DELETE ON case_events
            BEGIN
                SELECT RAISE(ABORT, 'events are append-only');
            END;
        """)
