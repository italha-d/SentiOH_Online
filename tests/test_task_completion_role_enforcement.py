from workflow.approvals import complete_task
from workflow.tasks import create_tasks
from workflow.roles import WAREHOUSE_MANAGER, WAREHOUSE_OPERATOR


def _confirmed_exposure():
    return {
        "status": "CONFIRMED",
        "recall_id": "R-TEST",
        "sku": "SKU-1",
        "batch": "LOT-1",
        "reason_code": "EXACT_BATCH_MATCH",
        "stock": 5,
        "dispatched": 0,
    }


def test_operational_task_cannot_be_completed_by_wrong_logged_in_role():
    task = next(
        item for item in create_tasks(_confirmed_exposure())
        if item["title"] == "Verify physical quantity"
    )
    case = {
        "case_id": "CASE-1",
        "state": "RESPONSE_ACTIVE",
        "tasks": [task],
        "reviews": [],
        "audit": [],
        "exposure": _confirmed_exposure(),
    }

    try:
        complete_task(
            case,
            task["task_id"],
            "Galway Warehouse Manager",
            actor_role=WAREHOUSE_MANAGER,
        )
    except PermissionError as exc:
        assert WAREHOUSE_OPERATOR in str(exc)
    else:
        raise AssertionError("Wrong role was allowed to complete another role's task")

    complete_task(
        case,
        task["task_id"],
        "Warehouse Operator",
        actor_role=WAREHOUSE_OPERATOR,
    )
    assert task["status"] == "COMPLETED"
