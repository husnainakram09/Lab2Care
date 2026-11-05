
"""Local fictional patient follow-up application.

Development only. Not for public deployment.
"""

import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi import Request
from api.staff_review import build_staff_review_packet

if os.getenv("FOLLOWUP_ENABLE_LOCAL_AGENT") != "1":
    raise RuntimeError("Local agent demo is disabled")

from api.main import app
from api.local_agent import router
from api.demo_state import get_demo_db

from core.followup import build_patient_status
from api.communication_actions import (
    get_current_notification,
    queue_demo_update,
    deliver_demo_update,
)
from storage.approvals import get_current_approval
from storage.repository import get_case
from storage.acknowledgements import (
    is_notification_acknowledged,
    record_demo_acknowledgement,
)

if not any(
    getattr(route, "path", None) == "/demo/agent/investigate"
    for route in app.routes
):
    app.include_router(router)


@app.get("/", include_in_schema=False)
def local_homepage():
    page = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "index.html"
    )

    return FileResponse(
        page,
        media_type="text/html",
    )


@app.get("/demo/active-case/status")
def active_case_status():
    """Read the actual shared fictional database."""

    try:
        db_path = get_demo_db()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Shared fictional database not initialized",
        )

    case = get_case(db_path, "CASE-001")

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Fictional case not found",
        )

    approval = get_current_approval(
        db_path,
        "CASE-001",
    )

    from api.communication_actions import get_current_notification

    delivery = get_current_notification(db_path)

    acknowledged = (
        delivery is not None
        and is_notification_acknowledged(
            db_path,
            delivery["notification_id"],
        )
    )

    status = build_patient_status(
        case,
        approval=approval,
        delivery=delivery,
        acknowledged=acknowledged,
    )

    return {
        **status,
        "case_version": case["version"],
        "data_mode": "fictional",
        "scenario": "active_unresolved_report",
        "note": (
            "This status is read from the persistent "
            "fictional case. AI investigation alone "
            "cannot complete reports or approve follow-up."
        ),
    }


@app.get("/demo/staff/review")
def staff_review(request: Request):
    """Local-only fictional staff evidence review."""

    if request.headers.get("X-Demo-Confirmation") != "yes":
        raise HTTPException(
            status_code=403,
            detail="Local demo confirmation required",
        )

    try:
        db_path = get_demo_db()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Shared fictional database unavailable",
        )

    return build_staff_review_packet(db_path)


from pydantic import BaseModel

from api.staff_actions import receive_confirmed_demo_report


class ConfirmedReportRequest(BaseModel):
    confirmation_id: str
    expected_version: int
    staff_attested: bool


@app.post("/demo/staff/receive-confirmed-report")
def receive_confirmed_report(
    payload: ConfirmedReportRequest,
    request: Request,
):
    if (
        request.client is None
        or request.client.host
            not in {"127.0.0.1", "::1", "testclient"}
        or request.headers.get("X-Demo-Confirmation") != "yes"
    ):
        raise HTTPException(
            status_code=403,
            detail="Local fictional staff demo only",
        )

    try:
        db_path = get_demo_db()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Demo database unavailable",
        )

    try:
        return receive_confirmed_demo_report(
            db_path,
            confirmation_id=payload.confirmation_id,
            expected_version=payload.expected_version,
            staff_attested=payload.staff_attested,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


from api.clinician_actions import simulate_clinician_approval


class ClinicianApprovalRequest(BaseModel):
    expected_version: int
    clinician_attested: bool


@app.post("/demo/clinician/approve")
def approve_fictional_followup(
    payload: ClinicianApprovalRequest,
    request: Request,
):
    if (
        request.client is None
        or request.client.host
            not in {"127.0.0.1", "::1", "testclient"}
        or request.headers.get("X-Demo-Confirmation") != "yes"
    ):
        raise HTTPException(
            status_code=403,
            detail="Local fictional clinician demo only",
        )

    try:
        db_path = get_demo_db()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Shared demo database unavailable",
        )

    try:
        return simulate_clinician_approval(
            db_path,
            expected_version=payload.expected_version,
            clinician_attested=payload.clinician_attested,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


class CommunicationRequest(BaseModel):
    expected_version: int


def require_local_communication_access(request: Request):
    if (
        request.client is None
        or request.client.host
            not in {"127.0.0.1", "::1", "testclient"}
        or request.headers.get("X-Demo-Confirmation") != "yes"
    ):
        raise HTTPException(
            status_code=403,
            detail="Local fictional demo only",
        )


@app.post("/demo/clinic/queue-notification")
def queue_fictional_notification(
    payload: CommunicationRequest,
    request: Request,
):
    require_local_communication_access(request)

    try:
        db_path = get_demo_db()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Demo database unavailable",
        )

    try:
        return queue_demo_update(
            db_path,
            expected_version=payload.expected_version,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


@app.post("/demo/clinic/deliver-notification")
def deliver_fictional_notification(
    payload: CommunicationRequest,
    request: Request,
):
    require_local_communication_access(request)

    try:
        db_path = get_demo_db()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Demo database unavailable",
        )

    try:
        return deliver_demo_update(
            db_path,
            expected_version=payload.expected_version,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


class PatientAcknowledgementRequest(BaseModel):
    expected_version: int
    patient_attested: bool


@app.post("/demo/patient/acknowledge")
def acknowledge_fictional_update(
    payload: PatientAcknowledgementRequest,
    request: Request,
):
    require_local_communication_access(request)

    try:
        db_path = get_demo_db()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Demo database unavailable",
        )

    try:
        return record_demo_acknowledgement(
            db_path,
            expected_version=payload.expected_version,
            patient_attested=payload.patient_attested,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


from api.audit_timeline import build_case_timeline


@app.get("/demo/active-case/timeline")
def active_case_timeline():
    """Read persisted history for the active fictional case."""
    try:
        db_path = get_demo_db()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Demo database unavailable",
        )

    return build_case_timeline(db_path, "CASE-001")


from api.research_evidence import get_synthea_evidence


@app.get("/demo/research/synthea")
def synthea_research_summary():
    """Aggregate, synthetic research context only."""
    try:
        return get_synthea_evidence()
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(
            status_code=503,
            detail="Synthea research summary unavailable",
        ) from error
