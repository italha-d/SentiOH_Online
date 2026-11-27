from workflow.workflow import open_case
from workflow.approvals import approve_task, complete_task
from workflow.versioning import register_recall_version
import copy

EXPOSURE={"recall_id":"R1","sku":"SKU1","product_name":"X","status":"CONFIRMED",
          "batch":"B1","reason_code":"EXACT_PRODUCT_AND_LOT_MATCH"}

def test_confirmed_case_has_tasks():
    case=open_case(EXPOSURE)
    assert case["state"]=="CONFIRMED"
    assert len(case["tasks"])>=4

def test_approval_gate_blocks():
    case=open_case(EXPOSURE)
    t=next(x for x in case["tasks"] if x["requires_approval"])
    try:
        complete_task(case,t["task_id"],"Tester")
        assert False
    except PermissionError:
        assert True

def test_approved_task_completes():
    case=open_case(EXPOSURE)
    t=next(x for x in case["tasks"] if x["requires_approval"])
    approve_task(case,t["task_id"],"QA","OK",approver_role=t["approval_roles"][0])
    complete_task(case,t["task_id"],"QA")
    assert t["status"]=="COMPLETED"

def test_recall_change_reopens():
    case=open_case(EXPOSURE)
    r={"product_name":"X","brand":"B","pack_sizes":["1g"],"batch_codes":["A"],"use_by":[],"best_before":[],"hazard":"H"}
    r2=copy.deepcopy(r); r2["batch_codes"].append("B")
    assert register_recall_version(case,r) is False
    assert register_recall_version(case,r2) is True
    assert case["needs_reanalysis"]
