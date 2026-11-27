from pathlib import Path

from ingestion.load_data import load_bundle
from tools.context import ToolContext
from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner
from tools.workflow_tools import request_human_approval

ROOT = Path(__file__).resolve().parents[1]


def test_agent_handoff_exposes_human_authority_roles():
    data = load_bundle(ROOT / "demo_data")
    ctx = ToolContext(data=data, cases={})
    state = SentiOHAgent(ctx, RulePlanner()).run("FSAI_DEMO_001")
    assert state.status == "AWAITING_HUMAN_APPROVAL"
    result = request_human_approval(ctx, state.case_id)
    assert result["status"] == "AWAITING_HUMAN_APPROVAL"
    assert result["waiting_tasks"]
    assert all(item["approval_roles"] for item in result["waiting_tasks"])
    assert all(item["approval_mode"] in {"ANY_ONE", "ALL_ROLES"} for item in result["waiting_tasks"])
