from workflow.workflow import open_case
from workflow.approvals import approve_task

def test_approval_records_auditable_event():
    case = open_case({
        "recall_id": "R1",
        "sku": "SKU1",
        "status": "CONFIRMED",
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
        "stock": 5,
        "dispatched": 1,
    })
    task = next(t for t in case["tasks"] if t["requires_approval"])
    approve_task(case, task["task_id"], "Quality Manager", "Checked", approver_role=task["approval_roles"][0])
    event = case["audit_timeline"][-1]
    assert event["event_id"].startswith("EVT-")
    assert event["time"]
    assert event["actor"] == "Quality Manager"
    assert event["action"] == "TASK_APPROVED"
    assert event["details"]["task_id"] == task["task_id"]
