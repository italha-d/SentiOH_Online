from workflow.workflow import open_case
from workflow.roles import WAREHOUSE_MANAGER, QUALITY_FOOD_SAFETY_MANAGER
import ui.login as login


EXPOSURE = {
    "recall_id": "R-LOGIN",
    "sku": "SKU001",
    "product_name": "Demo Product",
    "status": "CONFIRMED",
    "batch": "LOT1",
    "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
    "stock": 10,
    "dispatched": 4,
}


class FakeStore:
    def __init__(self, cases):
        self._cases = cases

    def load_cases(self):
        return self._cases


def test_prelogin_role_attention_survives_after_manager_logs_out(monkeypatch):
    case = open_case(EXPOSURE)
    cases = {case["case_id"]: case}
    monkeypatch.setattr(login, "CaseStore", lambda: FakeStore(cases))

    status = login._public_status()
    rows = login._public_role_attention_rows()

    assert status["active_cases"] == 1
    assert status["human_actions_pending"] > 0
    assert status["approvals_left"] > 0
    assert any(
        row["role"] == WAREHOUSE_MANAGER
        and row["approvals / rejections"] > 0
        for row in rows
    )
    assert any(
        row["role"] == QUALITY_FOOD_SAFETY_MANAGER
        and row["mark as reviewed"] > 0
        for row in rows
    )


def test_prelogin_attention_rows_do_not_expose_case_or_product_details(monkeypatch):
    case = open_case(EXPOSURE)
    cases = {case["case_id"]: case}
    monkeypatch.setattr(login, "CaseStore", lambda: FakeStore(cases))

    rows = login._public_role_attention_rows()
    forbidden = {"case_id", "recall_id", "sku", "product", "batch", "customer"}
    assert rows
    assert all(not (forbidden & set(row)) for row in rows)


def test_sidebar_source_contains_all_three_quick_action_types():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / "ui" / "login.py").read_text(encoding="utf-8")

    assert "My actions" in text
    assert "Approve" in text
    assert "Reject" in text
    assert "Mark as reviewed" in text
    assert "Mark as done" in text
    assert "_sidebar_approval_item" in text
    assert "_sidebar_review_item" in text
    assert "_sidebar_work_item" in text


def test_prelogin_screen_renders_who_needs_to_act_table():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / "ui" / "login.py").read_text(encoding="utf-8")

    assert "Who needs to act" in text
    assert "_public_role_attention_rows" in text
    assert "st.dataframe(" in text
    assert "Only role-level action counts are shown before sign-in." in text


def test_login_uses_pitch_tagline():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / "ui" / "login.py").read_text(encoding="utf-8")
    assert "From food-safety alert to evidence-backed action" in text
    assert "Evidence-grounded, human-supervised agentic recall response" not in text


def test_prelogin_demo_escalation_explicitly_points_to_incident_manager(monkeypatch):
    from workflow.quick_demo import _approval_only_task
    from workflow.approvals import reject_task
    from workflow.roles import STORE_SITE_MANAGER, RECALL_INCIDENT_MANAGER

    task = _approval_only_task(
        "Confirm and complete affected stock containment",
        STORE_SITE_MANAGER,
        {"sku": "SKU398"},
        "Contain stock",
        "Confirmed exposure",
        assigned_username="site.manager",
        assigned_display_name="Dublin Site Manager",
        affected_site_code="DUB",
        affected_site_name="Dublin Distribution Centre",
    )
    task["demo_approval_ordinal"] = 1
    final = _approval_only_task(
        "Review evidence and close the recall case",
        RECALL_INCIDENT_MANAGER,
        {"sku": "SKU398"},
        "Final review",
        "Human closure",
        assigned_username="incident.manager",
        assigned_display_name="Recall Incident Lead",
    )
    final["demo_approval_ordinal"] = 2
    final["depends_on_task_ids"] = [task["task_id"]]
    case = {
        "case_id": "C-DEMO-ESC", "state": "RESPONDING",
        "demo_profile": "QUICK_CLOSE_TWO_APPROVALS",
        "exposure": {"status": "CONFIRMED"},
        "tasks": [task, final], "reviews": [], "audit": [],
        "created_time": "2026-09-12T18:00:00+00:00",
    }
    reject_task(
        case, task["task_id"], "Dublin Site Manager",
        "Need a recount", approver_role=STORE_SITE_MANAGER,
        approver_username="site.manager",
    )
    monkeypatch.setattr(login, "CaseStore", lambda: FakeStore({case["case_id"]: case}))

    rows = login._public_role_attention_rows()
    assert rows == [{
        "role": RECALL_INCIDENT_MANAGER,
        "approvals / rejections": 0,
        "mark as reviewed": 1,
        "mark work done": 0,
        "total actions": 1,
    }]
