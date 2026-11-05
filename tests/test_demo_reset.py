
import tempfile
import unittest
from pathlib import Path

from api.demo_state import prepare_demo_db
from core.followup import build_patient_status
from scripts.reset_demo import reset_fictional_demo
from storage.repository import get_case, ingest_report


class TestDemoReset(unittest.TestCase):

    def test_reset_preserves_old_case_and_restarts_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "runtime" / "active" / "clinic.db"
            prepare_demo_db(db)

            ingest_report(
                db,
                "CASE-001",
                {
                    "report_id": "R-03",
                    "order_id": "T-03",
                    "patient_id": "PAT-001",
                    "test_code": "LAB-C",
                    "source_text": "Fictional completed report",
                },
                expected_version=1,
            )

            self.assertEqual(get_case(db, "CASE-001")["version"], 2)

            archive = reset_fictional_demo(db)

            old_case = get_case(archive / "clinic.db", "CASE-001")
            new_case = get_case(db, "CASE-001")

            self.assertEqual(old_case["version"], 2)
            self.assertEqual(new_case["version"], 1)
            self.assertEqual(
                build_patient_status(new_case)["state"],
                "AWAITING_REPORTS",
            )

    def test_reset_rejects_missing_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "runtime" / "active" / "clinic.db"

            with self.assertRaises(FileNotFoundError):
                reset_fictional_demo(db)


if __name__ == "__main__":
    unittest.main()
