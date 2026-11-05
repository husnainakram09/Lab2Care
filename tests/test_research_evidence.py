
import json
import tempfile
import unittest
from pathlib import Path

from api.research_evidence import get_synthea_evidence


class TestResearchEvidence(unittest.TestCase):

    def test_real_audit_summary_is_aggregate_only(self):
        result = get_synthea_evidence()

        self.assertEqual(
            result["resource_counts"]["DiagnosticReport"],
            780,
        )
        self.assertEqual(
            result["relationship_checks"]["patient_linked"],
            780,
        )
        self.assertEqual(
            result["relationship_checks"]["order_linked"],
            0,
        )

        self.assertFalse(result["linked_to_active_demo"])
        self.assertFalse(result["clinical_outcomes_evaluated"])

        encoded = json.dumps(result)
        self.assertNotIn("first_three_report_examples", encoded)
        self.assertNotIn("report_id", encoded)

    def test_inconsistent_counts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"

            path.write_text(json.dumps({
                "archive_sha256": "test",
                "resource_counts": {
                    "Patient": 11,
                    "ServiceRequest": 413,
                    "DiagnosticReport": 780,
                    "Observation": 2850,
                },
                "relationship_checks": {
                    "reports": 780,
                    "patient_linked": 781,
                    "order_linked": 0,
                    "with_resolved_observations": 367,
                },
            }), encoding="utf-8")

            with self.assertRaises(ValueError):
                get_synthea_evidence(path)


if __name__ == "__main__":
    unittest.main()
