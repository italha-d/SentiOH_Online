from .common import get_context
from matching.matcher import resolve_exposure
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]

def render(st):
    ctx = get_context(st)
    d = ctx.data
    st.title("Validation")
    st.write(
        "This page evaluates the deterministic resolver on locked synthetic "
        "ground-truth scenarios. These are prototype test results, not real-world FSAI metrics."
    )
    with open(ROOT/"demo_data"/"ground_truth_scenarios.csv", newline="", encoding="utf-8") as f:
        scenarios = list(csv.DictReader(f))

    results=[]
    for s in scenarios:
        recall=next(r for r in d["recalls"] if r["recall_id"]==s["recall_id"])
        product=next(p for p in d["products"] if p["sku"]==s["sku"])
        pred=resolve_exposure(recall,product,d["batches"],d["inventory"],d["dispatches"])
        results.append({
            "scenario_id":s["scenario_id"],
            "scenario_type":s["scenario_type"],
            "sku":s["sku"],
            "expected":s["expected_status"],
            "predicted":pred["status"],
            "pass":pred["status"]==s["expected_status"],
            "reason_code":pred["reason_code"],
        })
    pass_rate=sum(x["pass"] for x in results)/len(results) if results else 0.0
    st.metric("Locked synthetic scenario pass rate",f"{pass_rate:.1%}")
    st.dataframe(results,use_container_width=True,hide_index=True)

    coverage={}
    for r in results:
        coverage.setdefault(r["scenario_type"],{"total":0,"passed":0})
        coverage[r["scenario_type"]]["total"]+=1
        coverage[r["scenario_type"]]["passed"]+=int(r["pass"])
    st.subheader("Scenario coverage")
    st.dataframe([
        {"scenario_type":k,"passed":v["passed"],"total":v["total"]}
        for k,v in sorted(coverage.items())
    ],use_container_width=True,hide_index=True)
