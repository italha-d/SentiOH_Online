from workflow.tasks import create_tasks


def test_confirmed_tasks_have_detailed_operational_fields():
    exposure={
        "recall_id":"R1","sku":"SKU001","status":"CONFIRMED",
        "batch":"B1","reason_code":"EXACT_PRODUCT_AND_LOT_MATCH",
        "stock":41,"dispatched":27,
    }
    tasks=create_tasks(exposure)
    required={
        "description","why_generated","suggested_steps",
        "completion_evidence","completion_criteria","action_boundary",
    }
    assert len(tasks) >= 4
    for task in tasks:
        assert required.issubset(task.keys())
        assert task["description"]
        assert task["why_generated"]
        assert task["suggested_steps"]
        assert task["completion_evidence"]
        assert task["completion_criteria"]
        assert task["action_boundary"]


def test_possible_tasks_explain_missing_evidence_work():
    exposure={
        "recall_id":"R2","sku":"SKU005","status":"POSSIBLE",
        "reason_code":"LOT_SCOPE_NOT_SPECIFIED","stock":60,"dispatched":15,
    }
    tasks=create_tasks(exposure)
    assert any("batch or lot" in task["title"].lower() for task in tasks)
    assert all(task["status"] == "PENDING" for task in tasks)


def test_protected_tasks_still_require_human_approval():
    exposure={
        "recall_id":"R1","sku":"SKU001","status":"CONFIRMED",
        "batch":"B1","reason_code":"EXACT_PRODUCT_AND_LOT_MATCH",
        "stock":41,"dispatched":27,
    }
    tasks=create_tasks(exposure)
    protected=[task for task in tasks if task["requires_approval"]]
    assert protected
    assert all(task["status"] == "WAITING_FOR_APPROVAL" for task in protected)
