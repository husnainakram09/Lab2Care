"""Local-only HTTP API for a fictional patient follow-up demo.

Do not expose this unauthenticated prototype to real patients.
No real clinical data, clinician identities or notifications.
"""

import json
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException

from api.demo_state import ACTIVE_DB
from core.followup import build_patient_status, delivery_from_outbox
from storage.approvals import get_current_approval
from storage.db import connect_db
from storage.repository import get_case


def create_app(db_path, timeline_path=None):
    db_path = Path(db_path)
    timeline_path = (
        Path(timeline_path)
        if timeline_path is not None
        else db_path.with_name("timeline.json")
    )

    app = FastAPI(
        title="Patient Follow-up Agent - Fictional Demo",
        version="0.1.0",
    )

    @app.get("/health")
    def health():
        try:
            with connect_db(db_path) as db:
                db.execute(
                    "SELECT case_id FROM cases LIMIT 1"
                ).fetchone()
        except sqlite3.Error:
            raise HTTPException(
                status_code=503,
                detail="Demo database unavailable",
            )

        return {
            "service": "patient-followup",
            "status": "ok",
            "data_mode": "fictional",
        }

    @app.get("/demo/cases/{case_id}/status")
    def patient_status(case_id: str):
        case = get_case(db_path, case_id)

        if case is None:
            raise HTTPException(
                status_code=404,
                detail="Demo case not found",
            )

        approval = get_current_approval(
            db_path, case_id
        )

        with connect_db(db_path) as db:
            row = db.execute(
                """
                SELECT case_version, status
                FROM notification_outbox
                WHERE case_id = ?
                  AND case_version = ?
                ORDER BY notification_id DESC
                LIMIT 1
                """,
                (case_id, case["version"]),
            ).fetchone()

        delivery = (
            delivery_from_outbox(
                {"case_version": row[0], "status": row[1]}
            )
            if row is not None
            else None
        )

        result = build_patient_status(
            case,
            approval=approval,
            delivery=delivery,
        )

        return {
            **result,
            "data_mode": "fictional",
        }

    @app.get("/demo/journey")
    def recorded_journey():
        if not timeline_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Recorded demonstration unavailable",
            )

        return {
            "mode": "recorded_fictional_demo",
            "stages": json.loads(
                timeline_path.read_text(
                    encoding="utf-8"
                )
            ),
        }

    return app


# Same database the workflow routes use (api.demo_state.ACTIVE_DB).
app = create_app(
    os.environ.get(
        "FOLLOWUP_DEMO_DB",
        str(ACTIVE_DB),
    )
)
