from pathlib import Path
import csv
from ingestion.load_data import load_bundle
from matching.matcher import resolve_exposure

ROOT=Path(__file__).resolve().parents[1]

def test_expanded_dataset_scale():
    d=load_bundle(ROOT/"demo_data")
    assert len(d["products"])==400
    assert 20 <= len(d["suppliers"]) <= 30
    assert len(d["batches"]) >= 800
    assert len(d["sites"]) == 3
    assert len(d["purchase_orders"]) >= 500
    assert len(d["dispatches"]) >= 700

def test_locked_ground_truth_scenarios():
    d=load_bundle(ROOT/"demo_data")
    with open(ROOT/"demo_data"/"ground_truth_scenarios.csv",newline="",encoding="utf-8") as f:
        scenarios=list(csv.DictReader(f))
    failures=[]
    for s in scenarios:
        recall=next(r for r in d["recalls"] if r["recall_id"]==s["recall_id"])
        product=next(p for p in d["products"] if p["sku"]==s["sku"])
        result=resolve_exposure(recall,product,d["batches"],d["inventory"],d["dispatches"])
        if result["status"] != s["expected_status"]:
            failures.append((s["scenario_id"],s["expected_status"],result["status"],result["reason_code"]))
    assert failures == []
