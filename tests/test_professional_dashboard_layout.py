from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_is_organised_into_five_professional_tabs():
    text = (ROOT / "ui" / "single_dashboard.py").read_text(encoding="utf-8")
    assert "st.tabs(" in text
    for label in [
        '"Overview"',
        '"Investigation"',
        '"Exposure & Evidence"',
        '"Response"',
        '"Validation"',
    ]:
        assert label in text


def test_task_cards_are_compact_by_default():
    text = (ROOT / "ui" / "single_dashboard.py").read_text(encoding="utf-8")
    assert "View task rationale, evidence and audit detail" in text
    assert "Open audit trail and lifecycle" in text
    assert "Open traceability graph" in text
    assert "View Recall Inbox" in text


def test_dashboard_has_neutral_professional_metric_styling():
    text = (ROOT / "ui" / "single_dashboard.py").read_text(encoding="utf-8")
    assert 'div[data-testid="stMetric"]' in text
    assert "border-radius: 12px" in text
    assert "max-width: 1500px" in text
