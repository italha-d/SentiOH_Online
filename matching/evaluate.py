from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.load_data import load_bundle
from matching.matcher import resolve_exposure, VALID_STATES

CLASS_ORDER = [
    "CONFIRMED",
    "POSSIBLE",
    "NOT_AFFECTED",
    "INSUFFICIENT_EVIDENCE",
]


def _safe_div(a, b):
    return a / b if b else 0.0


def evaluate_scenarios(data, scenarios):
    rows = []
    for scenario in scenarios:
        recall = next(
            r for r in data["recalls"]
            if r["recall_id"] == scenario["recall_id"]
        )
        product = next(
            p for p in data["products"]
            if p["sku"] == scenario["sku"]
        )
        pred = resolve_exposure(
            recall,
            product,
            data["batches"],
            data["inventory"],
            data["dispatches"],
        )
        rows.append({
            "scenario_id": scenario["scenario_id"],
            "scenario_type": scenario["scenario_type"],
            "recall_id": scenario["recall_id"],
            "sku": scenario["sku"],
            "expected": scenario["expected_status"],
            "predicted": pred["status"],
            "reason_code": pred["reason_code"],
            "pass": pred["status"] == scenario["expected_status"],
        })

    matrix = {
        expected: {predicted: 0 for predicted in CLASS_ORDER}
        for expected in CLASS_ORDER
    }
    for row in rows:
        if row["expected"] in matrix and row["predicted"] in matrix[row["expected"]]:
            matrix[row["expected"]][row["predicted"]] += 1

    per_class = {}
    for cls in CLASS_ORDER:
        tp = matrix[cls][cls]
        fp = sum(matrix[other][cls] for other in CLASS_ORDER if other != cls)
        fn = sum(matrix[cls][other] for other in CLASS_ORDER if other != cls)
        support = sum(matrix[cls].values())
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        per_class[cls] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

    total = len(rows)
    correct = sum(r["pass"] for r in rows)
    macro_precision = sum(v["precision"] for v in per_class.values()) / len(CLASS_ORDER)
    macro_recall = sum(v["recall"] for v in per_class.values()) / len(CLASS_ORDER)
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(CLASS_ORDER)
    support_total = sum(v["support"] for v in per_class.values())
    weighted_f1 = _safe_div(
        sum(v["f1"] * v["support"] for v in per_class.values()),
        support_total,
    )

    confusion_rows = [
        {
            "expected": expected,
            **{predicted: matrix[expected][predicted] for predicted in CLASS_ORDER},
        }
        for expected in CLASS_ORDER
    ]

    return {
        "dataset_type": "SYNTHETIC_PROTOTYPE_EVALUATION",
        "scenario_count": total,
        "accuracy": _safe_div(correct, total),
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "per_class": per_class,
        "confusion_matrix": confusion_rows,
        "scenario_results": rows,
        "warning": (
            "Metrics are calculated only on locked synthetic prototype scenarios "
            "and are not real-world FSAI/RASFF performance estimates."
        ),
    }


def load_scenarios(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(data_dir="demo_data", scenarios_path=None):
    data_dir = Path(data_dir)
    scenarios_path = (
        Path(scenarios_path)
        if scenarios_path
        else data_dir / "ground_truth_scenarios.csv"
    )
    data = load_bundle(data_dir)
    scenarios = load_scenarios(scenarios_path)
    return evaluate_scenarios(data, scenarios)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="demo_data")
    parser.add_argument("--scenarios", default=None)
    parser.add_argument("--output", default="outputs/evaluation_results.json")
    args = parser.parse_args()

    result = run(args.data_dir, args.scenarios)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "scenario_count": result["scenario_count"],
        "accuracy": result["accuracy"],
        "macro_precision": result["macro_precision"],
        "macro_recall": result["macro_recall"],
        "macro_f1": result["macro_f1"],
        "weighted_f1": result["weighted_f1"],
        "output": str(output),
    }, indent=2))
