"""Runnable, fully fictional patient follow-up integration demo.

No real patients, laboratory integrations, model calls,
clinician authentication or real-world notifications.
"""

import json
import tempfile
from pathlib import Path

from core.followup import build_patient_status
from services.delivery_worker import dispatch_notification
from services.fake_notification import FakeNotificationGateway
from storage.approvals import (
    approve_followup,
    get_current_approval,
    initialize_approval_schema,
    seed_demo_actor,
)
from storage.db import initialize_db
from storage.outbox import (
    get_notification,
    initialize_outbox_schema,
    queue_approved_notification,
)
from storage.repository import (
    create_case,
    get_case,
    ingest_report,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "demo_case.json"
)


def run_demo(workspace):
    """Execute one end-to-end simulated patient journey."""

    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    clinic_db = workspace / "clinic.db"
    destination_db = workspace / "destination.db"

    if clinic_db.exists() or destination_db.exists():
        raise FileExistsError(
            "Use a fresh demo directory to avoid overwriting data"
        )

    demo_case = json.loads(FIXTURE.read_text())

    initialize_db(clinic_db)
    initialize_approval_schema(clinic_db)
    initialize_outbox_schema(clinic_db)

    create_case(clinic_db, demo_case)

    seed_demo_actor(clinic_db, "DOC-01", "clinician")
    seed_demo_actor(clinic_db, "STAFF-01", "coordinator")

    timeline = []

    def snapshot(stage, notification_id=None):
        case = get_case(clinic_db, "CASE-001")
        approval = get_current_approval(clinic_db, "CASE-001")

        delivery = None
        if notification_id is not None:
            notification = get_notification(
                clinic_db, notification_id
            )
            delivery = {
                "case_version": notification["case_version"],
                "status": notification["status"],
            }

        status = build_patient_status(
            case,
            approval=approval,
            delivery=delivery,
        )

        timeline.append({
            "stage": stage,
            **status,
        })

    # 1. Patient is waiting for the third test report.
    snapshot("Two reports received")

    # 2. The missing report arrives.
    ingest_report(
        clinic_db,
        "CASE-001",
        {
            "report_id": "R-03",
            "order_id": "T-03",
            "patient_id": "PAT-001",
            "test_code": "LAB-C",
            "source_text": "Fictional report C",
        },
        expected_version=1,
    )

    snapshot("Third report received")

    # 3. Simulated clinician approves exact instructions.
    approve_followup(
        clinic_db,
        "CASE-001",
        clinician_id="DOC-01",
        expected_version=2,
        instructions=(
            "Please contact the clinic to arrange follow-up."
        ),
    )

    snapshot("Clinician approved follow-up")

    # 4. Coordinator queues clinician-authored instructions.
    queued = queue_approved_notification(
        clinic_db,
        "CASE-001",
        expected_version=2,
        requester_id="STAFF-01",
    )

    notification_id = queued["notification_id"]

    snapshot("Message queued", notification_id)

    # 5. Separate fictional destination records the message.
    gateway = FakeNotificationGateway(destination_db)

    result = dispatch_notification(
        clinic_db,
        notification_id,
        gateway,
    )

    if result["outcome"] != "delivered":
        raise RuntimeError("Delivery was not confirmed")

    snapshot("Delivery verified", notification_id)

    return {
        "timeline": timeline,
        "case_version": get_case(
            clinic_db, "CASE-001"
        )["version"],
        "destination_receipts": gateway.delivery_count(),
        "final_delivery_outcome": result["outcome"],
    }


def main():
    print(
        "\nFICTIONAL PATIENT FOLLOW-UP DEMO\n"
        "No real patient, doctor or notification service.\n"
    )

    with tempfile.TemporaryDirectory() as directory:
        result = run_demo(directory)

        for index, step in enumerate(
            result["timeline"], start=1
        ):
            print(f"{index}. {step['stage']}")
            print(f"   State: {step['state']}")
            print(f"   Patient message: {step['message']}")
            print()

        print(
            "Verified fictional destination receipts:",
            result["destination_receipts"],
        )
        print(
            "Final simulated outcome:",
            result["final_delivery_outcome"],
        )


if __name__ == "__main__":
    main()
