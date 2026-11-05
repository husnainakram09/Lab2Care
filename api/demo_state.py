
"""Shared fictional demo database.

Local development only. Never store real patient records here.
"""

import json
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
