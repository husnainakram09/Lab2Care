
"""Archive and reset the local fictional demonstration.

Offline development utility. Never expose as an HTTP endpoint.
Stop the local server before running.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from api.demo_state import ACTIVE_DB, prepare_demo_db
from core.followup import build_patient_status
from storage.repository import get_case


def reset_fictional_demo(active_db=ACTIVE_DB):
    active_db = Path(active_db)
    active_dir = active_db.parent

    if active_db.name != "clinic.db" or active_dir.name != "active":
        raise ValueError("Unexpected demo database location")

    if not active_db.is_file():
        raise FileNotFoundError("Existing fictional demo not found")

    runtime_dir = active_dir.parent
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    archive = runtime_dir / "archives" / f"active-{timestamp}"
    staging = runtime_dir / f".active-next-{timestamp}"

    # Build and validate the replacement before moving the old demo.
    new_db = staging / "clinic.db"
    prepare_demo_db(new_db)

    case = get_case(new_db, "CASE-001")
    state = build_patient_status(case)

    if (
        case["version"] != 1
        or state["state"] != "AWAITING_REPORTS"
        or state["received_count"] != 2
    ):
        raise RuntimeError("Replacement demo validation failed")

    archive.parent.mkdir(parents=True, exist_ok=True)

    # The entire directory is archived, including the fake
    # destination database and any SQLite journal files.
    active_dir.rename(archive)

    try:
        staging.rename(active_dir)
    except Exception:
        archive.rename(active_dir)
        raise

    return archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-fictional-reset",
        action="store_true",
    )
    args = parser.parse_args()

    if not args.confirm_fictional_reset:
        raise SystemExit(
            "Reset not performed. Use --confirm-fictional-reset "
            "after stopping Uvicorn."
        )

    archive = reset_fictional_demo()

    print("Previous fictional demo archived:", archive)
    print("Fresh fictional demo:", ACTIVE_DB)
    print("Initial patient state: AWAITING_REPORTS")
    print("No real patient data or notifications involved.")


if __name__ == "__main__":
    main()
