
"""Local-only investigation of the shared fictional case.

No patient communication, report attachment, or clinical
approval. Never expose this endpoint publicly.
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from openai import OpenAI

from agent.runner import investigate_case
from agent.tools import LabInvestigationTools
from api.demo_state import get_demo_db
from storage.repository import get_case


router = APIRouter()
ROOT = Path(__file__).resolve().parents[1]


@router.post("/demo/agent/investigate")
def investigate_demo(request: Request):

    if (
        request.client is None
        or request.client.host not in {"127.0.0.1", "::1"}
        or request.headers.get("X-Demo-Confirmation") != "yes"
    ):
        raise HTTPException(
            status_code=403,
            detail="Local demo access only",
        )

    key = os.getenv("VULTR_SERVERLESS_INFERENCE_API_KEY")
    model = os.getenv("VULTR_MODEL")

    if not key or not model:
        raise HTTPException(
            status_code=503,
            detail="Vultr inference not configured",
        )

    try:
        db_path = get_demo_db()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Shared fictional database unavailable",
        )

    before = get_case(db_path, "CASE-001")

    if before is None:
        raise HTTPException(
            status_code=404,
            detail="Fictional case not found",
        )

    tools = LabInvestigationTools(
        db_path,
        "CASE-001",
        ROOT / "fixtures/lab_inbox.json",
    )

    client = OpenAI(
        api_key=key,
        base_url="https://api.vultrinference.com/v1",
        timeout=45.0,
        max_retries=1,
    )

    result = investigate_case(
        client=client,
        model=model,
        tools=tools,
        max_rounds=5,
    )

    after = get_case(db_path, "CASE-001")

    if before != after:
        raise HTTPException(
            status_code=409,
            detail=(
                "Case changed during investigation. "
                "Review the current case before retrying."
            ),
        )

    return {
        "scenario": "shared_fictional_missing_report",
        "case_id": "CASE-001",
        "case_version": before["version"],
        "model": model,
        "status": result["status"],
        "tool_sequence": [
            item["tool"]
            for item in result["trace"]
        ],
        "staff_drafts": result["drafts"],
        "case_unchanged": True,
        "data_mode": "fictional",
    }
