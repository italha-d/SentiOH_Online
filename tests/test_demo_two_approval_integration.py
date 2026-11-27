from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner
from ingestion.load_data import load_bundle
from tools.context import ToolContext
from storage.case_store import CaseStore
from workflow.approvals import approve_task
from workflow.approval_queue import approval_tasks_for_role
from workflow.quick_demo import (
    QUICK_CLOSE_PROFILE,
    streamline_existing_confirmed_case_for_demo,
)
from workflow.roles import WAREHOUSE_MANAGER, STORE_SITE_MANAGER, RECALL_INCIDENT_MANAGER
from workflow.states import close_case
from workflow.audit_export import audit_download_bytes


ROOT = Path(__file__).resolve().parents[1]


def _showcases():
    return json.loads(
        (ROOT / "demo_data" / "real_fsai_showcase_scenarios.json")
        .read_text(encoding="utf-8")
    )


def test_all_confirmed_demo_recalls_streamline_to_exactly_two_approvals():
    data = load_bundle(ROOT / "demo_data")
    confirmed = [
        item for item in _showcases()
        if item["expected_status"] == "CONFIRMED"
    ]
    assert len(confirmed) == 3

    for item in confirmed:
        ctx = ToolContext(data=data, cases={})
        state = SentiOHAgent(ctx, RulePlanner()).run(item["recall_id"])
        assert state.exposure["status"] == "CONFIRMED"
        assert state.case_id

        before = ctx.cases[state.case_id]
        assert len(before["tasks"]) > 2

        recall = next(
            r for r in data["real_recalls"]
            if r["recall_id"] == item["recall_id"]
        )
        case = streamline_existing_confirmed_case_for_demo(
            ctx,
            state.case_id,
            source_recall=recall,
        )

        assert case["demo_only"] is True
        assert case["demo_profile"] == QUICK_CLOSE_PROFILE
        assert len(case["tasks"]) == 2
        assert len(case["reviews"]) == 0
        assert all(task["approval_only"] for task in case["tasks"])
        assert all(task["requires_approval"] for task in case["tasks"])
        assert case["demo_full_workflow_reference"]["task_count"] > 2
        assert case["state"] == "RESPONDING"


def test_demo_approvals_are_sequential_and_resolve_after_second_decision():
    data = load_bundle(ROOT / "demo_data")
    item = next(
        item for item in _showcases()
        if item["expected_status"] == "CONFIRMED"
    )
    ctx = ToolContext(data=data, cases={})
    state = SentiOHAgent(ctx, RulePlanner()).run(item["recall_id"])
    recall = next(
        r for r in data["real_recalls"]
        if r["recall_id"] == item["recall_id"]
    )
    case = streamline_existing_confirmed_case_for_demo(
        ctx,
        state.case_id,
        source_recall=recall,
    )

    first = case["tasks"][0]
    second = case["tasks"][1]

    # Only approval 1 is routed initially, to the manager responsible for
    # the affected stock location. The prepared 2026.38 demo stock is in Dublin.
    assert first["affected_site_code"] == "DUB"
    assert first["assigned_username"] == "site.manager"
    assert first["approval_roles"] == [STORE_SITE_MANAGER]
    assert [task["task_id"] for _, task in approval_tasks_for_role(ctx.cases, STORE_SITE_MANAGER, username="site.manager")] == [first["task_id"]]
    assert approval_tasks_for_role(ctx.cases, STORE_SITE_MANAGER, username="cork.manager") == []
    assert approval_tasks_for_role(ctx.cases, RECALL_INCIDENT_MANAGER) == []

    with pytest.raises(PermissionError):
        approve_task(
            case,
            second["task_id"],
            "Incident Manager",
            "Too early",
            approver_role=RECALL_INCIDENT_MANAGER,
        )

    approve_task(
        case,
        first["task_id"],
        "Dublin Site Manager",
        "Containment evidence approved.",
        approver_role=STORE_SITE_MANAGER,
        approver_username="site.manager",
    )
    assert first["status"] == "COMPLETED"
    assert [task["task_id"] for _, task in approval_tasks_for_role(ctx.cases, RECALL_INCIDENT_MANAGER)] == [second["task_id"]]

    approve_task(
        case,
        second["task_id"],
        "Incident Manager",
        "Response package approved.",
        approver_role=RECALL_INCIDENT_MANAGER,
    )
    assert second["status"] == "COMPLETED"
    assert case["state"] == "RESOLVED"

    close_case(
        case,
        actor="Incident Manager",
        comment="Quick demo closure complete.",
        actor_role=RECALL_INCIDENT_MANAGER,
    )
    assert case["state"] == "CLOSED"


def test_live_demo_has_two_top_level_tabs_and_incident_manager_starts():
    source = (ROOT / "ui" / "single_dashboard.py").read_text(encoding="utf-8")
    assert 'st.tabs(["Live Demo", "Official FSAI"])' in source
    assert "NEW VERIFIED FSAI RECALL" in source
    assert '"Run investigation"' in source
    assert 'current_user.get("role") != RECALL_INCIDENT_MANAGER' in source
    assert "SentiOHAgent(ctx, planner).run" in source
    assert "LLM selected" in source


def test_live_demo_role_handoff_is_location_manager_then_incident_manager():
    source = (ROOT / "ui" / "single_dashboard.py").read_text(encoding="utf-8")
    assert "first_user = first_task.get(\"assigned_username\")" in source
    assert "NEXT HUMAN: {first_name}" in source
    assert "first_user = first_task.get(\"assigned_username\")" in source
    assert "INCIDENT MANAGER FINAL ACTION" in source
    assert "NEXT HUMAN: Recall / Incident Manager" in source
    assert "Approve and complete containment task" in source
    assert "Approve and close case" in source


def test_demo_session_preserves_active_case_across_role_sign_in():
    login_source = (ROOT / "ui" / "login.py").read_text(encoding="utf-8")
    # Signing out removes only auth_user, so the active demo case and investigation
    # state remain available when the next authorised role signs in.
    assert 'st.session_state.pop("auth_user", None)' in login_source
    assert 'st.session_state.get("active_case_id")' in login_source



def test_live_demo_reset_is_soft_deleted_and_retained_for_audit(tmp_path):
    data = load_bundle(ROOT / "demo_data")
    item = next(
        item for item in _showcases()
        if item["expected_status"] == "CONFIRMED"
    )
    store = CaseStore(
        path=tmp_path / "cases.db",
        audit_dir=tmp_path / "audit_exports",
    )
    ctx = ToolContext(data=data, cases={}, case_store=store)
    state = SentiOHAgent(ctx, RulePlanner()).run(item["recall_id"])
    recall = next(
        r for r in data["real_recalls"]
        if r["recall_id"] == item["recall_id"]
    )
    case = streamline_existing_confirmed_case_for_demo(
        ctx,
        state.case_id,
        source_recall=recall,
    )
    case_id = case["case_id"]

    archived = ctx.archive_case_for_audit(
        case_id,
        actor="Incident Manager",
        actor_role=RECALL_INCIDENT_MANAGER,
        reason="Presenter reset the Live Demo.",
    )

    assert archived["demo_archived"] is True
    assert archived["demo_record_status"] == "RESET_DELETED_RETAINED_FOR_AUDIT"
    assert archived["demo_reset"]["previous_state"] == "RESPONDING"
    assert archived["demo_reset"]["previous_exposure_status"] == "CONFIRMED"
    assert archived["demo_reset"]["reset_by"] == "Incident Manager"
    assert any(
        event.get("action") == "LIVE_DEMO_RESET_ARCHIVED"
        for event in archived.get("audit_timeline", [])
    )

    # Soft reset must not remove the case from memory or SQLite.
    assert case_id in ctx.cases
    reloaded = store.load_cases()
    assert case_id in reloaded
    assert reloaded[case_id]["demo_archived"] is True

    # The downloadable audit record must include the reset/deletion marker.
    payload = audit_download_bytes(archived).decode("utf-8")
    assert "RESET_DELETED_RETAINED_FOR_AUDIT" in payload
    assert "LIVE_DEMO_RESET_ARCHIVED" in payload


def test_brand_logo_precedes_visible_live_demo_tabs_and_graph_is_small():
    source = (ROOT / "ui" / "single_dashboard.py").read_text(encoding="utf-8")
    render_start = source.index("def render(st, current_user=None):")
    render_source = source[render_start:]
    assert render_source.index("render_brand_header(st, width=650)") < render_source.index(
        'st.tabs(["Live Demo", "Official FSAI"])'
    )
    assert 'width: 100% !important' in source
    assert 'max-width: 100% !important' in source
    assert 'height: auto !important' in source
    assert 'div[data-testid="stGraphVizChart"] > div' in source
    assert 'max-width: 100% !important' in source
    assert 'Exposure and traceability graph' in source
    assert 'Reset / Deleted Demo Cases · retained for audit' in source
