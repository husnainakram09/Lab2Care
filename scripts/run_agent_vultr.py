
"""Live, read-only administrative investigation on Vultr.

All data is fictional.
No clinical decisions or patient notifications.
"""

import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

from agent.runner import investigate_case
from agent.tools import LabInvestigationTools
from api.env_file import load_env_file
from storage.db import initialize_db
from storage.repository import create_case


ROOT = Path(__file__).resolve().parents[1]


def main():
    load_env_file()
    key = os.getenv("VULTR_SERVERLESS_INFERENCE_API_KEY")
    model = os.getenv("VULTR_MODEL")

    if not key or not model:
        raise SystemExit(
            "Vultr inference key and VULTR_MODEL are required."
        )

    client = OpenAI(
        api_key=key,
        base_url="https://api.vultrinference.com/v1",
        timeout=45.0,
        max_retries=1,
    )

    fixture = json.loads(
        (ROOT / "fixtures/demo_case.json").read_text(
            encoding="utf-8"
        )
    )

    with tempfile.TemporaryDirectory() as directory:
        db_path = Path(directory) / "clinic.db"

        initialize_db(db_path)
        create_case(db_path, fixture)

        tools = LabInvestigationTools(
            db_path,
            "CASE-001",
            ROOT / "fixtures/lab_inbox.json",
        )

        result = investigate_case(
            client=client,
            model=model,
            tools=tools,
            max_rounds=5,
        )

        summary = {
            "model": model,
            "status": result["status"],
            "tool_sequence": [
                entry["tool"] for entry in result["trace"]
            ],
            "tool_calls": len(result["trace"]),
            "clarification_drafts": len(result["drafts"]),
            "evidence_ids": [
                source_id
                for draft in result["drafts"]
                for source_id in draft["evidence_source_ids"]
            ],
            "executed_actions": 0,
            "data_mode": "fictional",
        }

        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
