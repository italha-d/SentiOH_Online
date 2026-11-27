from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.orchestrator import SentiOHAgent
from agent.planner import OllamaToolPlanner
from ingestion.load_data import load_bundle
from tools.context import ToolContext


def run_recall(recall_id):
    data = load_bundle(ROOT / "demo_data")
    ctx = ToolContext(data=data, cases={})
    planner = OllamaToolPlanner()
    agent = SentiOHAgent(ctx, planner)

    print(f"\n=== {recall_id} ===")
    state = agent.run(recall_id)

    print("Planner:", planner.display_name)
    print("Status:", state.status)
    print("Stop reason:", state.stop_reason)
    print("Exposure:", (state.exposure or {}).get("status"))
    print("Reason:", (state.exposure or {}).get("reason_code"))
    print("Case:", state.case_id)
    print("Task narratives:", state.llm_task_narratives_generated)

    print("\nTool timeline:")
    for event in state.events:
        if event.tool:
            print(
                f"  step {event.step}: {event.tool} "
                f"| {event.summary}"
            )

    if state.evidence_gap_analysis:
        print("\nEvidence-gap analysis:")
        print(state.evidence_gap_analysis)

    if state.llm_recommendation:
        print("\nLocal LLM recommendation:")
        print(state.llm_recommendation)

    if state.case_id:
        case = ctx.cases[state.case_id]
        print("\nTask narrative sources:")
        for task in case.get("tasks", []):
            print(
                f"  {task['title']}: "
                f"{task.get('narrative_source')} "
                f"({task.get('narrative_model')})"
            )

    return state


def main():
    planner = OllamaToolPlanner()
    health = planner.health()
    if not health.get("ok"):
        print("FAIL: Ollama is not reachable.")
        print(health.get("error"))
        return 2

    if not health.get("model_installed"):
        print(
            f"FAIL: {planner.model} is not installed. "
            f"Run: ollama pull {planner.model}"
        )
        return 3

    confirmed = run_recall("FSAI_DEMO_001")
    possible = run_recall("FSAI_DEMO_002")

    if (confirmed.exposure or {}).get("status") != "CONFIRMED":
        print("FAIL: confirmed demo recall did not resolve CONFIRMED.")
        return 4

    if (possible.exposure or {}).get("status") != "POSSIBLE":
        print("FAIL: possible demo recall did not resolve POSSIBLE.")
        return 5

    if not confirmed.llm_recommendation:
        print("FAIL: no LLM recommendation generated.")
        return 6

    if not possible.evidence_gap_analysis:
        print("FAIL: no evidence-gap analysis generated.")
        return 7

    if confirmed.llm_task_narratives_generated == 0:
        print("FAIL: no confirmed-task narratives were generated.")
        return 8

    if possible.llm_task_narratives_generated == 0:
        print("FAIL: no possible-task narratives were generated.")
        return 9

    print("\nPASS: local Llama 3.2 agent completed end-to-end enrichment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
