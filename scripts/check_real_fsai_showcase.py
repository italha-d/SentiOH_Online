from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner
from ingestion.load_data import load_bundle
from matching.matcher import resolve_exposure, search_catalogue
from tools.context import ToolContext


def main():
    data = load_bundle(ROOT / "demo_data")
    scenarios = json.loads(
        (ROOT / "demo_data" / "real_fsai_showcase_scenarios.json")
        .read_text(encoding="utf-8")
    )

    failures = []
    counts = Counter(item["expected_status"] for item in scenarios)

    required = {
        "CONFIRMED": 3,
        "POSSIBLE": 3,
        "NOT_AFFECTED": 3,
    }
    if dict(counts) != required:
        failures.append(
            f"Expected exactly {required}; observed {dict(counts)}"
        )

    for item in scenarios:
        recall = next(
            r for r in data["real_recalls"]
            if r["recall_id"] == item["recall_id"]
        )
        product = next(
            p for p in data["products"]
            if p["sku"] == item["sku"]
        )
        candidates = search_catalogue(
            recall,
            data["products"],
            limit=5,
        )
        result = resolve_exposure(
            recall,
            product,
            data["batches"],
            data["inventory"],
            data["dispatches"],
        )

        expected = (
            item["expected_status"],
            item["expected_reason_code"],
        )
        observed = (
            result["status"],
            result["reason_code"],
        )

        if observed != expected:
            failures.append(
                f"{item['scenario_id']}: expected {expected}, got {observed}"
            )
        elif not candidates or candidates[0]["sku"] != item["sku"]:
            failures.append(
                f"{item['scenario_id']}: intended showcase SKU "
                f"{item['sku']} is not the top catalogue candidate"
            )
        else:
            print(
                f"PASS {item['scenario_id']}: "
                f"FSAI {item['official_recall_id']} -> {item['sku']} -> "
                f"{result['status']} / {result['reason_code']} "
                f"stock={result.get('stock', 0)} "
                f"dispatched={result.get('dispatched', 0)}"
            )

    # All actionable showcase scenarios must run through the whole agent path
    # and create a governed case.
    for item in [
        scenario
        for scenario in scenarios
        if scenario["expected_status"] in {"CONFIRMED", "POSSIBLE"}
    ]:
        ctx = ToolContext(data=data, cases={})
        state = SentiOHAgent(ctx, RulePlanner()).run(item["recall_id"])

        if (state.exposure or {}).get("status") != item["expected_status"]:
            failures.append(
                f"{item['scenario_id']} agent path: "
                f"expected {item['expected_status']}, "
                f"got {(state.exposure or {}).get('status')}"
            )
        elif not state.case_id:
            failures.append(
                f"{item['scenario_id']} agent path: "
                "no governed response case created"
            )
        elif state.stop_reason == "MAX_AGENT_STEPS_REACHED":
            failures.append(
                f"{item['scenario_id']} agent path hit the safety step cap"
            )
        else:
            print(
                f"PASS agent path {item['scenario_id']}: "
                f"steps={state.step} case={state.case_id} "
                f"stop={state.stop_reason}"
            )

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print(" -", failure)
        return 2

    print(
        "\nPASS: 9 genuine FSAI showcase scenarios are connected "
        "(3 CONFIRMED, 3 POSSIBLE, 3 NOT_AFFECTED)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
