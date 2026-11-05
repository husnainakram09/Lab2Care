
"""Prepare persistent fictional records for the local API."""

import json
from pathlib import Path

from scripts.demo_patient_journey import run_demo


def main():
    target = Path("runtime/demo")

    if any(
        (target / name).exists()
        for name in ("clinic.db", "destination.db", "timeline.json")
    ):
        raise SystemExit(
            "Demo already exists. Refusing to overwrite it."
        )

    result = run_demo(target)

    (target / "timeline.json").write_text(
        json.dumps(result["timeline"], indent=2),
        encoding="utf-8",
    )

    print("Persistent fictional demo created.")
    print("Final outcome:", result["final_delivery_outcome"])
    print("Recorded stages:", len(result["timeline"]))


if __name__ == "__main__":
    main()
