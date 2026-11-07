
"""Which fictional case a request may read or change.

Shared mode serves one persistent case to a local developer.
Guest mode gives every browser its own case, so public visitors
cannot change what anyone else sees. Neither mode is
authentication; all records remain fictional.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request, Response

from api.demo_state import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    get_demo_db,
    get_guest_db,
    guest_sessions_enabled,
    is_valid_session_id,
    new_session_id,
)


LOCAL_CLIENTS = {"127.0.0.1", "::1", "testclient"}


@dataclass(frozen=True)
class DemoCase:
    db_path: Path
    session_id: str | None


def resolve_demo_case(request: Request, response: Response):
    """Return the caller's case; in guest mode, also issue its cookie."""

    if not guest_sessions_enabled():
        try:
            return DemoCase(get_demo_db(), None)
        except FileNotFoundError:
            raise HTTPException(
                status_code=503,
                detail="Fictional demo database not initialized",
            )

    session_id = request.cookies.get(SESSION_COOKIE)

    if not is_valid_session_id(session_id):
        session_id = new_session_id()

    db_path = get_guest_db(session_id)
    set_session_cookie(response, session_id)

    return DemoCase(db_path, session_id)


def set_session_cookie(response: Response, session_id):
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=os.getenv("FOLLOWUP_SECURE_COOKIES") == "1",
    )


def require_demo_confirmation(request: Request):
    # Another site cannot make a browser send this custom header
    # without a CORS preflight, which this app never grants.
    if request.headers.get("X-Demo-Confirmation") != "yes":
        raise HTTPException(
            status_code=403,
            detail="Demo confirmation header required",
        )


def require_shared_case_access(request: Request):
    """The single shared case may only be changed from this machine.

    Behind a reverse proxy every client appears local, which is why
    public deployments must run in guest mode instead.
    """
    if guest_sessions_enabled():
        return

    if (
        request.client is None
        or request.client.host not in LOCAL_CLIENTS
    ):
        raise HTTPException(
            status_code=403,
            detail="The shared demo case accepts local requests only",
        )


def demo_case_for_read(request: Request, response: Response):
    return resolve_demo_case(request, response)


def demo_case_for_review(request: Request, response: Response):
    require_demo_confirmation(request)
    return resolve_demo_case(request, response)


def demo_case_for_action(request: Request, response: Response):
    require_demo_confirmation(request)
    require_shared_case_access(request)
    return resolve_demo_case(request, response)
