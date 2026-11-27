from pathlib import Path
import json
from ingestion.load_data import load_bundle
from tools.context import ToolContext
from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner
from workflow.versioning import register_recall_version

ROOT = Path(__file__).resolve().parents[1]

def test_demo_recall_update_reuses_case_and_increments_revision():
    data = load_bundle(ROOT/"demo_data")
    ctx = ToolContext(data, {})
    agent = SentiOHAgent(ctx, RulePlanner())

    first = agent.run("FSAI_DEMO_001")
    case_id = first.case_id
    assert ctx.cases[case_id]["analysis_revision"] == 1

    update = json.loads((ROOT/"demo_data"/"recall_updates.json").read_text())[0]
    recall = next(r for r in data["recalls"] if r["recall_id"] == update["recall_id"])
    for key, value in update["patch"].items():
        recall[key] = value

    changed = register_recall_version(ctx.cases[case_id], recall)
    assert changed is True
    assert ctx.cases[case_id]["state"] == "ANALYSING"
    assert ctx.cases[case_id]["needs_reanalysis"] is True

    second = agent.run("FSAI_DEMO_001")
    assert second.case_id == case_id
    assert ctx.cases[case_id]["analysis_revision"] == 2
    assert ctx.cases[case_id]["exposure"]["matched_batches"] == ["SS16726", "SS16727"]
    assert ctx.cases[case_id]["exposure"]["stock"] == 66
    assert ctx.cases[case_id]["exposure"]["dispatched"] == 37
