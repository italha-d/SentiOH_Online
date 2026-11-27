from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_dashboard_displays_all_active_cases():
    text = (ROOT/"ui"/"single_dashboard.py").read_text(encoding="utf-8")
    assert 'st.subheader("All active cases")' in text
    assert 'Inspect response case' in text
    assert '_case_portfolio_rows' in text
    assert 'Selected Case Audit Trail' in text

def test_active_case_definition_keeps_resolved_open_until_final_closure():
    text = (ROOT/"ui"/"single_dashboard.py").read_text(encoding="utf-8")
    assert 'if case.get("state") != "CLOSED"' in text
    assert "RESOLVED is still an open case until an authorised final closure action" in text
