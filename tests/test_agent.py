from pathlib import Path
from ingestion.load_data import load_bundle
from tools.context import ToolContext
from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner

ROOT=Path(__file__).resolve().parents[1]

def ctx():
    return ToolContext(load_bundle(ROOT/"demo_data"),{})

def test_agent_runs_to_human_approval_for_confirmed_recall():
    c=ctx()
    agent=SentiOHAgent(c,RulePlanner())
    state=agent.run("FSAI_DEMO_001")
    assert state.exposure["status"]=="CONFIRMED"
    assert state.inventory["total_quantity"]==41
    assert state.dispatches["total_dispatched"]==27
    assert state.case_id in c.cases
    assert state.status=="AWAITING_HUMAN_APPROVAL"
    assert state.stop_reason=="HUMAN_APPROVAL_REQUIRED"
    assert state.step <= 12

def test_agent_possible_case_finishes_with_evidence_tasks():
    c=ctx()
    agent=SentiOHAgent(c,RulePlanner())
    state=agent.run("FSAI_DEMO_002")
    assert state.exposure["status"]=="POSSIBLE"
    assert state.case_id in c.cases
    assert state.status=="COMPLETE"
    case=c.cases[state.case_id]
    assert any("Verify physical batch" in t["title"] for t in case["tasks"])

def test_agent_only_logs_approved_tool_names():
    c=ctx()
    state=SentiOHAgent(c,RulePlanner()).run("FSAI_DEMO_001")
    tools={e.tool for e in state.events if e.tool}
    assert "approve_task" not in tools
    assert "send_email" not in tools


def test_agent_run_supports_live_step_callback_without_changing_outcome():
    c = ctx()
    snapshots = []

    def on_step(state):
        snapshots.append(
            {
                "step": state.step,
                "status": state.status,
                "tools": [
                    event.tool
                    for event in state.events
                    if event.event_type == "TOOL_CALL" and event.tool
                ],
            }
        )

    state = SentiOHAgent(c, RulePlanner()).run(
        "FSAI_DEMO_001",
        on_step=on_step,
    )

    assert snapshots
    assert len(snapshots) == state.step
    assert snapshots[-1]["status"] == "AWAITING_HUMAN_APPROVAL"
    assert snapshots[-1]["tools"][-1] == "request_human_approval"
    assert state.exposure["status"] == "CONFIRMED"
    assert state.stop_reason == "HUMAN_APPROVAL_REQUIRED"
