import sqlite3
import tempfile
import unittest
from pathlib import Path

from storage.db import connect_db, initialize_db


class TestDatabaseFoundation(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        initialize_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_required_tables_exist(self):
        with connect_db(self.db_path) as db:
            rows = db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table'"
            ).fetchall()

        tables = {row[0] for row in rows}

        self.assertTrue(
            {"cases", "test_orders", "reports"} <= tables
        )

    def test_order_requires_existing_case(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with connect_db(self.db_path) as db:
                db.execute(
                    """
                    INSERT INTO test_orders
                    (case_id, order_id, patient_id, test_code)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("UNKNOWN", "T-01", "PAT-001", "LAB-A"),
                )

    def test_failed_transaction_rolls_back(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with connect_db(self.db_path) as db:
                db.execute(
                    """
                    INSERT INTO cases
                    (case_id, patient_id, version, fictional)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("CASE-001", "PAT-001", 1, 1),
                )

                db.execute(
                    """
                    INSERT INTO reports
                    (case_id, report_id, order_id,
                     patient_id, test_code)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("UNKNOWN", "R-01", "T-01",
                     "PAT-001", "LAB-A"),
                )

        with connect_db(self.db_path) as db:
            result = db.execute(
                "SELECT case_id FROM cases WHERE case_id = ?",
                ("CASE-001",),
            ).fetchone()

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
