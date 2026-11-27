from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

def test_dashboard_contains_required_single_screen_content():
    source = (ROOT/"ui"/"single_dashboard.py").read_text(encoding="utf-8")
    expected = [
        "Recall Inbox & Investigation",
        "Public Recall Evidence",
        "Agent Investigation Timeline",
        "Exposure Analysis & Evidence",
        "Recall Source Evidence",
        "Internal Company Evidence",
        "Exposure Graph",
        "Response Cases",
        "Selected Case Audit Trail & Lifecycle",
        "System Validation & Demo Dataset",
        "Confirmed exposures",
        "Possible exposures",
    ]
    for label in expected:
        assert label in source

def test_no_streamlit_calls_at_module_scope():
    source = (ROOT/"ui"/"single_dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if (
                isinstance(fn, ast.Attribute)
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "st"
            ):
                offenders.append((node.lineno, fn.attr))
    assert offenders == []
