from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_uses_authenticated_role_routing():
    text = (ROOT / "ui" / "single_dashboard.py").read_text(encoding="utf-8")
    assert "Human approval authority matrix" in text
    assert "My Approval Inbox" in text
    assert "Approval authority:" in text
    assert "Approve proposed action" in text
    assert "Reject proposed action" in text
    assert "Final case closure approval" in text
    assert "current_user" in text
    assert "Approvals left" in text
    assert "All required human approvals" in text
    assert "Decision authority role" not in text
