
import copy
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from research.synthea_fhir import (
    audit_resources,
    audit_zip,
)


def sample():
    return {
        "Patient": [
            {"resourceType": "Patient", "id": "P1"}
        ],
        "ServiceRequest": [{
            "resourceType": "ServiceRequest",
            "id": "O1",
            "subject": {"reference": "Patient/P1"},
        }],
        "Observation": [{
            "resourceType": "Observation",
            "id": "V1",
            "subject": {"reference": "Patient/P1"},
            "valueString": "Fictional test value",
        }],
        "DiagnosticReport": [{
            "resourceType": "DiagnosticReport",
            "id": "R1",
            "status": "final",
            "subject": {"reference": "Patient/P1"},
            "basedOn": [
                {"reference": "ServiceRequest/O1"}
            ],
            "result": [
                {"reference": "Observation/V1"}
            ],
        }],
    }


class TestSyntheaAudit(unittest.TestCase):

    def test_explicit_links_are_detected(self):
        result = audit_resources(sample())
        checks = result["relationship_checks"]

        self.assertEqual(checks["patient_linked"], 1)
        self.assertEqual(checks["order_linked"], 1)
        self.assertEqual(
            checks["with_resolved_observations"], 1
        )

    def test_missing_order_link_is_not_inferred(self):
        data = sample()
        data["DiagnosticReport"][0]["basedOn"] = []

        result = audit_resources(data)

        self.assertEqual(
            result["relationship_checks"]["order_linked"], 0
        )

    def test_wrong_patient_does_not_link_order(self):
        data = copy.deepcopy(sample())
        data["ServiceRequest"][0]["subject"] = {
            "reference": "Patient/OTHER"
        }

        result = audit_resources(data)

        self.assertEqual(
            result["relationship_checks"]["order_linked"], 0
        )

    def test_archive_audit_does_not_export_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.zip"

            with ZipFile(path, "w") as archive:
                for kind, records in sample().items():
                    archive.writestr(
                        f"{kind}.000.ndjson",
                        "\n".join(json.dumps(r) for r in records),
                    )

            result = audit_zip(path)

        self.assertEqual(
            result["relationship_checks"]["reports"], 1
        )
        self.assertNotIn(
            "Fictional test value",
            json.dumps(result),
        )


if __name__ == "__main__":
    unittest.main()
