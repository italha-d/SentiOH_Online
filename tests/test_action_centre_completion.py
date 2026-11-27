from workflow.workflow import open_case
from workflow.approvals import approve_task, complete_task
from workflow.reviews import mark_reviewed
from workflow.action_center import human_action_summary
from workflow.roles import (
    QUALITY_FOOD_SAFETY_MANAGER,
    RECALL_INCIDENT_MANAGER,
)

EXPOSURE = {
    "recall_id": "R-COMPLETE",
    "sku": "SKU001",
    "product_name": "Demo Product",
    "status": "CONFIRMED",
    "batch": "LOT1",
    "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
    "stock": 10,
    "dispatched": 4,
}


def test_all_human_actions_complete_after_approvals_reviews_and_operations():
    case = open_case(EXPOSURE)

    # Complete every required approval decision.
    for task in case["tasks"]:
        if not task.get("requires_approval"):
            continue
        roles = list(task.get("approval_roles") or [])
        if task.get("approval_mode") == "ALL_ROLES":
            required_roles = roles
        else:
            required_roles = roles[:1]

        for role in required_roles:
            approve_task(
                case,
                task["task_id"],
                f"Demo {role}",
                "Approved for test",
                approver_role=role,
            )

    # Acknowledge every review with its assigned reviewer role.
    for review in list(case.get("reviews", [])):
        mark_reviewed(
            case,
            review["review_id"],
            f"Demo {review['assigned_role']}",
            review["assigned_role"],
            "Reviewed for test",
        )

    # Perform all operational work after approvals.
    for task in case["tasks"]:
        if task.get("status") in {"PENDING", "APPROVED"}:
            complete_task(
                case,
                task["task_id"],
                f"Demo {task['assigned_to']}",
            )

    summary = human_action_summary({case["case_id"]: case})
    assert summary["approval_decisions_left"] == 0
    assert summary["reviews_left"] == 0
    assert summary["operational_tasks_left"] == 0
    assert summary["closure_actions_left"] == 1
    assert summary["total_human_actions_left"] == 1
    assert summary["all_human_actions_complete"] is False
    assert case["state"] == "RESOLVED"
