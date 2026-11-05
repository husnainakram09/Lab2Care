
"""Audit Synthea-generated FHIR R4 relationships.

Research only. No medical interpretation, automatic report
attachment, clinician decisions or patient notifications.
"""

from collections import Counter
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json


KINDS = (
    "Patient", "ServiceRequest",
    "DiagnosticReport", "Observation",
)


def reference_id(reference, kind):
    """Resolve ordinary relative or absolute FHIR references."""
    if not isinstance(reference, str):
        return None

    prefix = f"{kind}/"

    if reference.startswith(prefix):
        remainder = reference[len(prefix):]
    elif f"/{prefix}" in reference:
        remainder = reference.rsplit(f"/{prefix}", 1)[-1]
    else:
        return None

    return remainder.split("/")[0] or None


def audit_resources(resources):
    patients = {
        r["id"] for r in resources["Patient"]
        if r.get("id")
    }
    orders = {
        r["id"]: r for r in resources["ServiceRequest"]
        if r.get("id")
    }
    observations = {
        r["id"]: r for r in resources["Observation"]
        if r.get("id")
    }

    counts = Counter()
    examples = []

    for report in resources["DiagnosticReport"]:
        patient_id = reference_id(
            report.get("subject", {}).get("reference"),
            "Patient",
        )

        patient_exists = patient_id in patients

        order_linked = False
        for item in report.get("basedOn", []):
            order_id = reference_id(
                item.get("reference"), "ServiceRequest"
            )
            order = orders.get(order_id)

            if (
                patient_exists
                and order is not None
                and reference_id(
                    order.get("subject", {}).get("reference"),
                    "Patient",
                ) == patient_id
            ):
                order_linked = True
                break

        resolved_observations = 0

        for item in report.get("result", []):
            observation_id = reference_id(
                item.get("reference"), "Observation"
            )
            observation = observations.get(observation_id)

            if (
                patient_exists
                and observation is not None
                and reference_id(
                    observation.get("subject", {}).get("reference"),
                    "Patient",
                ) == patient_id
            ):
                resolved_observations += 1

        counts["reports"] += 1
        counts["patient_linked"] += int(patient_exists)
        counts["order_linked"] += int(order_linked)
        counts["with_resolved_observations"] += int(
            resolved_observations > 0
        )

        if len(examples) < 3:
            examples.append({
                "report_id": report.get("id"),
                "fhir_status": report.get("status"),
                "patient_linked": patient_exists,
                "order_linked": order_linked,
                "resolved_observation_count":
                    resolved_observations,
            })

    return {
        "resource_counts": {
            kind: len(resources[kind]) for kind in KINDS
        },
        "relationship_checks": dict(counts),
        "first_three_report_examples": examples,
        "interpretation": (
            "FHIR relationship audit only. Missing references "
            "are not proof of failed clinical follow-up."
        ),
    }


def audit_zip(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    resources = {kind: [] for kind in KINDS}

    with ZipFile(path) as archive:
        for member in archive.namelist():
            filename = Path(member).name

            if not filename.endswith(".ndjson"):
                continue

            kind = filename.split(".")[0]

            if kind not in resources:
                continue

            with archive.open(member) as stream:
                for raw in stream:
                    if not raw.strip():
                        continue

                    record = json.loads(raw)
                    if record.get("resourceType") != kind:
                        raise ValueError(
                            f"Unexpected resource in {member}"
                        )
                    resources[kind].append(record)

    if not resources["Patient"]:
        raise ValueError("No FHIR Patient records found")

    result = audit_resources(resources)
    result["source"] = (
        "SMART on FHIR / Synthea-generated sample"
    )
    result["license"] = "CC0"
    result["archive_sha256"] = digest
    return result


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source = root / "research/data/synthea_fhir_10.zip"
    destination = (
        root / "research/results/synthea_fhir_profile.json"
    )

    result = audit_zip(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2))
    print(f"\nSaved audit: {destination}")
