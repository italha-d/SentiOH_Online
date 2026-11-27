from pathlib import Path
from matching.evaluate import run

ROOT = Path(__file__).resolve().parents[1]

def test_synthetic_evaluation_outputs_precision_recall_f1():
    result = run(ROOT/"demo_data")
    assert result["scenario_count"] >= 10
    assert 0 <= result["accuracy"] <= 1
    assert 0 <= result["macro_precision"] <= 1
    assert 0 <= result["macro_recall"] <= 1
    assert 0 <= result["macro_f1"] <= 1
    assert set(result["per_class"]) == {
        "CONFIRMED", "POSSIBLE", "NOT_AFFECTED", "INSUFFICIENT_EVIDENCE"
    }
    assert result["dataset_type"] == "SYNTHETIC_PROTOTYPE_EVALUATION"
