
"""Research-only audit of openly licensed MIMIC-IV demo labs.

No clinical decisions, medical interpretations, or patient messaging.
"""

import csv
import gzip
import hashlib
import json
from pathlib import Path


SOURCE = "MIMIC-IV Clinical Database Demo v2.2 (PhysioNet)"

REQUIRED = {
    "labevent_id",
    "subject_id",
    "itemid",
    "charttime",
    "storetime",
    "value",
    "valuenum",
    "valueuom",
}


def summarize_lab_events(path, expected_sha256):
    path = Path(path)

    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    if digest != expected_sha256:
        raise ValueError(
            "SHA256 mismatch: source cannot be verified"
        )

    rows = 0
    subjects = set()
    items = set()
    event_ids = set()

    nonnumeric = 0
    no_value = 0
    no_unit = 0
    no_storetime = 0

    with gzip.open(
        path, "rt", newline="", encoding="utf-8"
    ) as stream:

        reader = csv.DictReader(stream)

        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("Unexpected laboratory schema")

        for record in reader:
            rows += 1

            if not record["labevent_id"]:
                raise ValueError("Missing laboratory event ID")

            event_ids.add(record["labevent_id"])
            subjects.add(record["subject_id"])
            items.add(record["itemid"])

            nonnumeric += not bool(record["valuenum"])
            no_value += not bool(
                record["value"] or record["valuenum"]
            )
            no_unit += not bool(record["valueuom"])
            no_storetime += not bool(record["storetime"])

    return {
        "source": SOURCE,
        "license": "ODbL-1.0",
        "source_sha256": digest,
        "lab_event_rows": rows,
        "distinct_event_ids": len(event_ids),
        "distinct_deidentified_subjects": len(subjects),
        "distinct_lab_item_ids": len(items),
        "records_without_numeric_value": nonnumeric,
        "records_without_any_value": no_value,
        "records_without_unit": no_unit,
        "records_without_storetime": no_storetime,
        "note": (
            "Research-only data profile. These are not "
            "patient notification or follow-up outcomes."
        ),
    }


if __name__ == "__main__":
    file_path = Path("research/data/labevents.csv.gz")

    expected_hash = (
        "d51a4cf1ea63245abe7d544b0d50a928e9ee2ec"
        "5eb9a5ce85500aed0bd6c6dfc"
    )

    result = summarize_lab_events(
        file_path,
        expected_hash,
    )

    print(json.dumps(result, indent=2))
