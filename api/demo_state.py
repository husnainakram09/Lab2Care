
"""Shared fictional demo database.

Local development only. Never store real patient records here.
"""

import json
import os
import re
import secrets
import shutil
import threading
import time
from pathlib import Path

from storage.db import initialize_db
from storage.approvals import (
    initialize_approval_schema,
    seed_demo_actor,
)
from storage.outbox import initialize_outbox_schema
from storage.repository import create_case
from storage.acknowledgements import (
    initialize_acknowledgement_schema,
)

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DB = ROOT / "runtime" / "active" / "clinic.db"

# Guest mode gives every visitor a private fictional case, so a
# public demo cannot be completed or jammed for the next visitor.
SESSIONS_DIR = ROOT / "runtime" / "sessions"
SESSION_COOKIE = "lab2care_session"
SESSION_TTL_SECONDS = 24 * 60 * 60
MAX_GUEST_SESSIONS = int(os.getenv("FOLLOWUP_MAX_GUEST_SESSIONS", "300"))

_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{43}$")
_session_lock = threading.Lock()


def prepare_demo_db(db_path=None):
    """Create a fresh fictional case without overwriting data."""
    db_path = Path(db_path) if db_path else ACTIVE_DB

    if db_path.exists():
        raise FileExistsError(
            f"Demo database already exists: {db_path}"
        )

    db_path.parent.mkdir(parents=True, exist_ok=True)

    fixture = json.loads(
        (ROOT / "fixtures" / "demo_case.json").read_text(
            encoding="utf-8"
        )
    )

    initialize_db(db_path)
    initialize_approval_schema(db_path)
    initialize_outbox_schema(db_path)
    initialize_acknowledgement_schema(db_path)

    create_case(db_path, fixture)

    seed_demo_actor(db_path, "DOC-01", "clinician")
    seed_demo_actor(db_path, "STAFF-01", "coordinator")

    return db_path


def get_demo_db():
    """Return the existing shared demo case."""
    if not ACTIVE_DB.is_file():
        raise FileNotFoundError(
            "Run prepare_demo_db before starting the demo"
        )

    return ACTIVE_DB


def guest_sessions_enabled():
    return os.getenv("FOLLOWUP_GUEST_SESSIONS") == "1"


def new_session_id():
    return secrets.token_urlsafe(32)


def is_valid_session_id(session_id):
    return (
        isinstance(session_id, str)
        and _SESSION_ID.fullmatch(session_id) is not None
    )


def get_guest_db(session_id):
    """Return this visitor's fictional case, creating it if needed.

    An expired or evicted session is silently replaced by a fresh
    case. Only a server-generated session ID format is accepted.
    """
    if not is_valid_session_id(session_id):
        raise ValueError("Invalid demo session")

    session_dir = SESSIONS_DIR / session_id
    db_path = session_dir / "clinic.db"

    with _session_lock:
        if db_path.is_file() and not _expired(session_dir):
            return db_path

        _remove(session_dir)
        _prune_sessions(keep=MAX_GUEST_SESSIONS - 1)

        # Build in staging so a half-created case is never visible.
        staging = SESSIONS_DIR / f".new-{session_id}"
        _remove(staging)
        prepare_demo_db(staging / "clinic.db")
        staging.rename(session_dir)

    return db_path


def discard_guest_session(session_id):
    """Best-effort removal of one visitor's fictional case."""
    if is_valid_session_id(session_id):
        with _session_lock:
            _remove(SESSIONS_DIR / session_id)


def _expired(session_dir):
    try:
        age = time.time() - session_dir.stat().st_mtime
    except FileNotFoundError:
        return True

    return age > SESSION_TTL_SECONDS


def _prune_sessions(keep):
    """Remove expired sessions, then the oldest beyond the cap."""
    if not SESSIONS_DIR.is_dir():
        return

    sessions = []

    for path in SESSIONS_DIR.iterdir():
        if not path.is_dir():
            continue

        if path.name.startswith(".new-") or _expired(path):
            _remove(path)
        else:
            sessions.append(path)

    sessions.sort(key=lambda path: path.stat().st_mtime)

    for path in sessions[:max(0, len(sessions) - keep)]:
        _remove(path)


def _remove(path):
    # A file still open on Windows is retried at the next prune.
    shutil.rmtree(path, ignore_errors=True)
