
"""Model-driven investigation of the caller's fictional case.

No patient communication, report attachment, or clinical
approval. Paid inference is bounded by an in-process budget.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from openai import APIError, APITimeoutError, OpenAI

from agent.runner import investigate_case
from agent.tools import LabInvestigationTools
from api.access import DemoCase, demo_case_for_action
from api.inference_budget import budget_from_environment
from storage.repository import get_case


router = APIRouter()
ROOT = Path(__file__).resolve().parents[1]
budget = budget_from_environment()


@router.post("/demo/agent/investigate")
def investigate_demo(demo: DemoCase = Depends(demo_case_for_action)):

    key = os.getenv("VULTR_SERVERLESS_INFERENCE_API_KEY")
    model = os.getenv("VULTR_MODEL")

    if not key or not model:
        raise HTTPException(
            status_code=503,
            detail="Vultr inference not configured",
        )

    refusal = budget.acquire(demo.session_id or "shared")

    if refusal is not None:
        raise HTTPException(status_code=429, detail=refusal)

    try:
        return _investigate(demo.db_path, key, model)
    finally:
        budget.release()


def _investigate(db_path, key, model):
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

    try:
        result = investigate_case(
            client=client,
            model=model,
            tools=tools,
            max_rounds=5,
        )
    except APITimeoutError:
        raise HTTPException(
            status_code=504,
            detail=(
                "Vultr inference did not respond in time. "
                "No case data was changed. Try again shortly."
            ),
        )
    except APIError:
        raise HTTPException(
            status_code=502,
            detail=(
                "Vultr inference request failed. "
                "No case data was changed. Try again shortly."
            ),
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
        "reason": result.get("reason"),
        "tool_sequence": [
            item["tool"]
            for item in result["trace"]
        ],
        "staff_drafts": result["drafts"],
        "case_unchanged": True,
        "data_mode": "fictional",
    }
