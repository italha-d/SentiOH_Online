from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner
from ingestion.load_data import load_bundle
from tools.context import ToolContext


def main():
    data = load_bundle(ROOT / "demo_data")
    stop_counts = Counter()
    failures = []

    for recall in data["real_recalls"]:
        ctx = ToolContext(data=data, cases={})
        state = SentiOHAgent(
            ctx,
            RulePlanner(),
        ).run(recall["recall_id"])

        stop_counts[state.stop_reason] += 1

        if state.stop_reason == "MAX_AGENT_STEPS_REACHED":
            failures.append(
                f"{recall['official_recall_id']} / "
                f"{recall['product_name']}: MAX_AGENT_STEPS_REACHED"
            )

        if state.status == "ERROR":
            failures.append(
                f"{recall['official_recall_id']} / "
                f"{recall['product_name']}: ERROR {state.stop_reason}"
            )

    print("Official FSAI recall termination summary:")
    for reason, count in sorted(stop_counts.items()):
        print(f"  {reason}: {count}")

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print(" -", failure)
        return 2

    print(
        f"\nPASS: all {len(data['real_recalls'])} official FSAI product-scope "
        "recalls terminate without hitting the maximum-step safety cap."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
