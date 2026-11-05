
"""Aggregate Synthea FHIR research evidence.

No raw patient records are returned or linked to CASE-001.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "research/results/synthea_fhir_profile.json"


def get_synthea_evidence(profile_path=None):
    path = Path(profile_path) if profile_path else PROFILE

    audit = json.loads(path.read_text(encoding="utf-8"))

    counts = audit["resource_counts"]
    links = audit["relationship_checks"]

    resources = {
        key: counts[key]
        for key in (
            "Patient",
            "ServiceRequest",
            "DiagnosticReport",
            "Observation",
        )
    }

    relationships = {
        key: links[key]
        for key in (
            "reports",
            "patient_linked",
            "order_linked",
            "with_resolved_observations",
        )
    }

    for value in (*resources.values(), *relationships.values()):
        if type(value) is not int or value < 0:
            raise ValueError("Invalid research count")

    if relationships["reports"] != resources["DiagnosticReport"]:
        raise ValueError("DiagnosticReport count mismatch")

    if any(
        relationships[key] > relationships["reports"]
        for key in (
            "patient_linked",
            "order_linked",
            "with_resolved_observations",
        )
    ):
        raise ValueError("Inconsistent report relationships")

    return {
        "title": "Synthea FHIR bulk-export audit",
        "source": "SMART on FHIR sample bulk datasets",
        "source_url": (
            "https://github.com/smart-on-fhir/"
            "sample-bulk-fhir-datasets"
        ),
        "archive_sha256": audit["archive_sha256"],
        "resource_counts": resources,
        "relationship_checks": relationships,
        "explicit_order_linkage_available":
            relationships["order_linked"] > 0,
        "linked_to_active_demo": False,
        "clinical_outcomes_evaluated": False,
        "data_mode": "synthetic_research_aggregate",
        "interpretation": (
            "The audited DiagnosticReports have patient "
            "references, but none has an explicit resolved "
            "ServiceRequest linkage under the audit method. "
            "This does not establish missed clinical follow-up. "
            "CASE-001 is an independent fictional workflow."
        ),
    }
