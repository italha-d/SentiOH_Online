from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_login_screen_shows_role_handoff_without_operational_case_counts():
    text = (ROOT / "ui" / "login.py").read_text(encoding="utf-8")
    require_login = text.split("def require_login(st):", 1)[1].split("def _sidebar_approval_item", 1)[0]
    assert "Active response cases" not in require_login
    assert "Human actions pending" not in require_login
    assert "Critical approvals pending" not in require_login
    assert "Who needs to act" in require_login
    assert "Only role-level action counts are shown before sign-in." in require_login
    assert "Authorised user sign-in" in require_login


def test_authenticated_dashboard_contains_action_centre_features():
    text = (ROOT / "ui" / "single_dashboard.py").read_text(encoding="utf-8")
    for label in [
        "Attention Required",
        "My Approval Inbox",
        "My Review Inbox",
        "My Operational Work",
        "Mark as reviewed",
        "Incident Management Overview",
        "Who currently needs to act",
        "Human actions left",
        "ALL HUMAN ACTIONS COMPLETE",
    ]:
        assert label in text


def test_role_action_routing_remains_available_after_authentication():
    text = (ROOT / "ui" / "login.py").read_text(encoding="utf-8")
    assert "_sidebar_approval_item" in text
    assert "_sidebar_review_item" in text
    assert "_sidebar_work_item" in text
    assert "personal_action_summary" in text
