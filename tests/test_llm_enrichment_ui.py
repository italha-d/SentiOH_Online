from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_exposes_new_local_llm_reasoning_features():
    text = (
        ROOT / "ui" / "single_dashboard.py"
    ).read_text(encoding="utf-8")

    for label in [
        "LLM evidence-gap analysis",
        "Evidence-gap reasoning",
        "Differential re-analysis",
        "Generated from this case's structured evidence",
        "LLM case reasoning",
    ]:
        assert label in text
