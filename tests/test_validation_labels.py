from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_validation_panel_uses_clear_labels():
    text = (ROOT/"ui"/"single_dashboard.py").read_text(encoding="utf-8")
    assert 'st.header("6. System Validation & Demo Dataset")' in text
    assert 'st.subheader("System Validation")' in text
    assert 'st.subheader("Demo Environment")' in text
    assert 'Test scenarios passed' in text
    assert 'Scenario pass rate' in text
