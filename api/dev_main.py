
"""Fictional patient follow-up application.

Local development uses one shared fictional case. A public
deployment must set FOLLOWUP_GUEST_SESSIONS=1 so that every
visitor works on a private fictional case.
"""

import os
from pathlib import Path

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, StrictBool

from api.env_file import load_env_file

# Before any setting is read, including the database path in api.main.
load_env_file()

if os.getenv("FOLLOWUP_ENABLE_LOCAL_AGENT") != "1":
    raise RuntimeError("Local agent demo is disabled")

from api.access import (
    DemoCase,
    demo_case_for_action,
    demo_case_for_read,
    demo_case_for_review,
    require_demo_confirmation,
    resolve_demo_case,
    set_session_cookie,
)
from api.audit_timeline import build_case_timeline
from api.case_status import read_active_case_status
from api.clinician_actions import simulate_clinician_approval
from api.communication_actions import (
    queue_demo_update,
    deliver_demo_update,
)
from api.demo_state import (
    SESSION_COOKIE,
    discard_guest_session,
    get_guest_db,
    guest_sessions_enabled,
    new_session_id,
)
from api.local_agent import router
from api.main import app
from api.research_evidence import get_synthea_evidence
from api.staff_actions import receive_confirmed_demo_report
from api.staff_review import build_staff_review_packet
from storage.acknowledgements import record_demo_acknowledgement

if not any(
    getattr(route, "path", None) == "/demo/agent/investigate"
    for route in app.routes
):
    app.include_router(router)


@app.get("/", include_in_schema=False)
def homepage(request: Request):
    page = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "index.html"
    )

    response = FileResponse(
        page,
        media_type="text/html",
    )

    # Issue the session before the page's parallel API calls,
    # so they all share one guest case.
    if guest_sessions_enabled():
        resolve_demo_case(request, response)

    return response


def session_mode():
    return "guest" if guest_sessions_enabled() else "shared"


@app.get("/demo/active-case/status")
def active_case_status(demo: DemoCase = Depends(demo_case_for_read)):
    """Read the caller's persistent fictional case."""

    case, status = read_active_case_status(demo.db_path)

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Fictional case not found",
        )

    return {
        **status,
        "case_version": case["version"],
        "data_mode": "fictional",
        "session_mode": session_mode(),
        "scenario": "active_unresolved_report",
        "note": (
            "This status is read from the persistent "
            "fictional case. AI investigation alone "
            "cannot complete reports or approve follow-up."
        ),
    }


@app.get("/demo/staff/review")
def staff_review(demo: DemoCase = Depends(demo_case_for_review)):
    """Read-only fictional staff evidence review."""

    return build_staff_review_packet(demo.db_path)


class ConfirmedReportRequest(BaseModel):
    confirmation_id: str
    expected_version: int
    staff_attested: StrictBool


@app.post("/demo/staff/receive-confirmed-report")
def receive_confirmed_report(
    payload: ConfirmedReportRequest,
    demo: DemoCase = Depends(demo_case_for_action),
):
    try:
        return receive_confirmed_demo_report(
            demo.db_path,
            confirmation_id=payload.confirmation_id,
            expected_version=payload.expected_version,
            staff_attested=payload.staff_attested,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


class ClinicianApprovalRequest(BaseModel):
    expected_version: int
    clinician_attested: StrictBool


@app.post("/demo/clinician/approve")
def approve_fictional_followup(
    payload: ClinicianApprovalRequest,
    demo: DemoCase = Depends(demo_case_for_action),
):
    try:
        return simulate_clinician_approval(
            demo.db_path,
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


@app.post("/demo/clinic/queue-notification")
def queue_fictional_notification(
    payload: CommunicationRequest,
    demo: DemoCase = Depends(demo_case_for_action),
):
    try:
        return queue_demo_update(
            demo.db_path,
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
    demo: DemoCase = Depends(demo_case_for_action),
):
    try:
        return deliver_demo_update(
            demo.db_path,
            expected_version=payload.expected_version,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


class PatientAcknowledgementRequest(BaseModel):
    expected_version: int
    patient_attested: StrictBool


@app.post("/demo/patient/acknowledge")
def acknowledge_fictional_update(
    payload: PatientAcknowledgementRequest,
    demo: DemoCase = Depends(demo_case_for_action),
):
    try:
        return record_demo_acknowledgement(
            demo.db_path,
            expected_version=payload.expected_version,
            patient_attested=payload.patient_attested,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


@app.post("/demo/session/restart")
def restart_guest_case(request: Request, response: Response):
    """Give this visitor a fresh fictional case (guest mode only)."""

    require_demo_confirmation(request)

    if not guest_sessions_enabled():
        raise HTTPException(
            status_code=404,
            detail=(
                "Guest sessions are disabled. Reset the shared "
                "case offline with scripts.reset_demo."
            ),
        )

    previous = request.cookies.get(SESSION_COOKIE)
    session_id = new_session_id()
    get_guest_db(session_id)
    set_session_cookie(response, session_id)
    discard_guest_session(previous)

    return {
        "action": "GUEST_CASE_RESTARTED",
        "case_version": 1,
        "session_mode": "guest",
        "data_mode": "fictional",
    }


@app.get("/demo/active-case/timeline")
def active_case_timeline(demo: DemoCase = Depends(demo_case_for_read)):
    """Read persisted history for the caller's fictional case."""

    return build_case_timeline(demo.db_path, "CASE-001")


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
