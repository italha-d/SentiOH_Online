from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.load_data import load_bundle, validate_bundle
from tools.context import ToolContext
from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner


def main():
    data = load_bundle(ROOT / "demo_data")
    validation = validate_bundle(ROOT / "demo_data")

    if not validation["ok"]:
        print("FAIL: bundle validation failed")
        for issue in validation["issues"]:
            print(" -", issue)
        return 2

    expectations = json.loads(
        (ROOT / "demo_data" / "recall_demo_expectations.json")
        .read_text(encoding="utf-8")
    )

    recall_ids = {r["recall_id"] for r in data.get("synthetic_recalls", data["recalls"])}
    expected_ids = {e["recall_id"] for e in expectations}

    if recall_ids != expected_ids:
        print("FAIL: recall fixture IDs and expectation IDs differ")
        print("recalls:", sorted(recall_ids))
        print("expected:", sorted(expected_ids))
        return 3

    failures = []

    for expected in expectations:
        rid = expected["recall_id"]
        ctx = ToolContext(data=data, cases={})
        state = SentiOHAgent(ctx, RulePlanner()).run(rid)
        exposure = state.exposure or {}

        observed = {
            "expected_sku": exposure.get("sku"),
            "expected_status": exposure.get("status"),
            "expected_reason_code": exposure.get("reason_code"),
            "expected_stock": exposure.get("stock"),
            "expected_dispatched": exposure.get("dispatched"),
        }

        mismatches = []
        for key, value in observed.items():
            if value != expected[key]:
                mismatches.append(
                    f"{key}: expected={expected[key]!r}, observed={value!r}"
                )

        if mismatches:
            failures.append((rid, mismatches))
            print(f"FAIL {rid}")
            for mismatch in mismatches:
                print("  -", mismatch)
        else:
            print(
                f"PASS {rid}: "
                f"{exposure.get('status')} / {exposure.get('reason_code')} / "
                f"{exposure.get('sku')} / stock={exposure.get('stock')} / "
                f"dispatched={exposure.get('dispatched')}"
            )

    if failures:
        return 4

    print(
        f"PASS: all {len(expectations)} bundled recall fixtures are "
        "internally consistent and resolve as designed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
