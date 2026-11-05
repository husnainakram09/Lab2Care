import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.reconcile import reconcile_case
from storage.db import initialize_db
from storage.repository import create_case, get_case


DATA = json.loads(
    (Path(__file__).resolve().parents[1]
     / "fixtures/demo_case.json").read_text()
)


class TestCaseRepository(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cases.db"
        initialize_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_case_round_trip(self):
        create_case(self.db_path, DATA)

        restored = get_case(self.db_path, "CASE-001")

        self.assertEqual(
            restored,
            {**DATA, "version": 1},
        )

    def test_reconciliation_after_database_reload(self):
        create_case(self.db_path, DATA)
        restored = get_case(self.db_path, "CASE-001")

        result = reconcile_case(
            restored["patient_id"],
            restored["orders"],
            restored["reports"],
        )

        self.assertEqual(result["missing_order_ids"], ["T-03"])
        self.assertFalse(result["ready_for_doctor_review"])

    def test_duplicate_report_rolls_back_case(self):
        invalid = copy.deepcopy(DATA)
        invalid["reports"].append(
            copy.deepcopy(invalid["reports"][0])
        )

        with self.assertRaises(sqlite3.IntegrityError):
            create_case(self.db_path, invalid)

        self.assertIsNone(
            get_case(self.db_path, "CASE-001")
        )

    def test_cases_are_isolated(self):
        other = copy.deepcopy(DATA)
        other["case_id"] = "CASE-002"
        other["patient_id"] = "PAT-002"

        for order in other["orders"]:
            order["patient_id"] = "PAT-002"

        for report in other["reports"]:
            report["patient_id"] = "PAT-002"

        create_case(self.db_path, DATA)
        create_case(self.db_path, other)

        first = get_case(self.db_path, "CASE-001")
        second = get_case(self.db_path, "CASE-002")

        self.assertEqual(first["patient_id"], "PAT-001")
        self.assertEqual(second["patient_id"], "PAT-002")
        self.assertEqual(len(first["reports"]), 2)
        self.assertEqual(len(second["reports"]), 2)

    def test_nonfictional_case_rejected(self):
        invalid = copy.deepcopy(DATA)
        invalid["fictional"] = False

        with self.assertRaises(ValueError):
            create_case(self.db_path, invalid)

        self.assertIsNone(
            get_case(self.db_path, "CASE-001")
        )


if __name__ == "__main__":
    unittest.main()
