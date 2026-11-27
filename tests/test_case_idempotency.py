from pathlib import Path

from ingestion.load_data import load_bundle
from tools.context import ToolContext
from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner
from tools.workflow_tools import open_response_case

ROOT = Path(__file__).resolve().parents[1]


def context():
    return ToolContext(load_bundle(ROOT / "demo_data"), {})


def test_repeated_full_analysis_reuses_same_case():
    ctx = context()
    agent = SentiOHAgent(ctx, RulePlanner())

    first = agent.run("FSAI_DEMO_001")
    first_case_id = first.case_id

    assert len(ctx.cases) == 1
    assert first.case_action == "CREATED"

    second = agent.run("FSAI_DEMO_001")

    assert len(ctx.cases) == 1
    assert second.case_id == first_case_id
    assert second.case_action == "REUSED_UNCHANGED"


def test_unchanged_analysis_preserves_existing_task_progress():
    ctx = context()
    agent = SentiOHAgent(ctx, RulePlanner())

    first = agent.run("FSAI_DEMO_001")
    case = ctx.cases[first.case_id]
    task = next(t for t in case["tasks"] if not t["requires_approval"])
    task["status"] = "COMPLETED"
    task_id = task["task_id"]

    second = agent.run("FSAI_DEMO_001")
    same_case = ctx.cases[second.case_id]

    assert second.case_action == "REUSED_UNCHANGED"
    assert next(t for t in same_case["tasks"] if t["task_id"] == task_id)["status"] == "COMPLETED"


def test_changed_exposure_updates_same_case_id():
    ctx = context()

    first_exposure = {
        "recall_id": "TEST_RECALL",
        "sku": "SKU001",
        "product_name": "Test Product",
        "status": "POSSIBLE",
        "reason_code": "LOT_INFORMATION_MISSING",
        "stock": 10,
        "dispatched": 0,
    }
    first = open_response_case(ctx, first_exposure)
    case_id = first["case_id"]

    second_exposure = dict(first_exposure)
    second_exposure.update({
        "status": "CONFIRMED",
        "batch": "LOT1",
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
        "stock": 8,
        "dispatched": 2,
    })

    second = open_response_case(ctx, second_exposure)

    assert len(ctx.cases) == 1
    assert second["case_id"] == case_id
    assert second["case_action"] == "UPDATED"
    assert ctx.cases[case_id]["analysis_revision"] == 2
    assert ctx.cases[case_id]["exposure"]["status"] == "CONFIRMED"
    assert len(ctx.cases[case_id]["task_history"]) == 1
