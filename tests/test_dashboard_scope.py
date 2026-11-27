from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

def test_no_streamlit_calls_at_module_scope():
    path = ROOT/"ui"/"single_dashboard.py"
    source = path.read_text(encoding="utf-8")
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

def test_case_sections_are_inside_render():
    path = ROOT/"ui"/"single_dashboard.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    official = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_render_official_fsai"
    )
    segment = ast.get_source_segment(source, official)
    assert 'st.header("4. Response Cases")' in segment
    assert 'st.header("5. Selected Case Audit Trail")' in segment
    assert 'st.header("6. System Validation & Demo Dataset")' in segment

    render = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "render"
    )
    render_segment = ast.get_source_segment(source, render)
    assert 'st.tabs(["Live Demo", "Official FSAI"])' in render_segment
    assert "_render_official_fsai" in render_segment
    assert "_render_live_demo_page" in render_segment
