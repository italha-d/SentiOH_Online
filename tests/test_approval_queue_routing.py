from workflow.workflow import open_case
from workflow.approvals import approve_task
from workflow.approval_queue import (
    approval_tasks_for_role,
    approval_statistics,
    approvals_left,
)
from workflow.roles import (
    WAREHOUSE_MANAGER,
    STORE_SITE_MANAGER,
    QUALITY_FOOD_SAFETY_MANAGER,
    RECALL_INCIDENT_MANAGER,
    PROCUREMENT_MANAGER,
)

EXPOSURE = {
    "recall_id": "R-QUEUE",
    "sku": "SKU001",
    "product_name": "Demo Product",
    "status": "CONFIRMED",
    "batch": "LOT1",
    "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
    "stock": 10,
    "dispatched": 4,
}


def _task(case, title):
    return next(t for t in case["tasks"] if t["title"] == title)


def test_approval_inbox_only_routes_to_authorised_roles():
    case = open_case(EXPOSURE)
    cases = {case["case_id"]: case}

    warehouse_titles = {
        task["title"] for _, task in approval_tasks_for_role(cases, WAREHOUSE_MANAGER)
    }
    procurement_titles = {
        task["title"] for _, task in approval_tasks_for_role(cases, PROCUREMENT_MANAGER)
    }

    assert "Hold remaining stock" in warehouse_titles
    assert "Pause further dispatch of affected lot" in warehouse_titles
    assert "Prepare supplier communication draft" not in warehouse_titles

    assert "Prepare supplier communication draft" in procurement_titles
    assert "Hold remaining stock" not in procurement_titles


def test_any_one_gate_disappears_for_all_eligible_roles_after_one_decision():
    case = open_case(EXPOSURE)
    cases = {case["case_id"]: case}
    hold = _task(case, "Hold remaining stock")

    assert approvals_left(hold) == 1
    assert approval_tasks_for_role(cases, WAREHOUSE_MANAGER)
    assert approval_tasks_for_role(cases, STORE_SITE_MANAGER)

    approve_task(
        case,
        hold["task_id"],
        "Galway Warehouse Manager",
        "Approved",
        approver_role=WAREHOUSE_MANAGER,
    )

    assert approvals_left(hold) == 0
    assert all(task["task_id"] != hold["task_id"] for _, task in approval_tasks_for_role(cases, WAREHOUSE_MANAGER))
    assert all(task["task_id"] != hold["task_id"] for _, task in approval_tasks_for_role(cases, STORE_SITE_MANAGER))


def test_dual_approval_reports_one_left_after_first_approval():
    case = open_case(EXPOSURE)
    customer = _task(case, "Prepare customer communication draft")
    cases = {case["case_id"]: case}

    assert approvals_left(customer) == 2

    approve_task(
        case,
        customer["task_id"],
        "Food Safety Lead",
        "Wording checked",
        approver_role=QUALITY_FOOD_SAFETY_MANAGER,
    )

    assert approvals_left(customer) == 1
    assert all(
        task["task_id"] != customer["task_id"]
        for _, task in approval_tasks_for_role(cases, QUALITY_FOOD_SAFETY_MANAGER)
    )
    assert any(
        task["task_id"] == customer["task_id"]
        for _, task in approval_tasks_for_role(cases, RECALL_INCIDENT_MANAGER)
    )


def test_global_approval_statistics_show_remaining_decisions():
    case = open_case(EXPOSURE)
    stats = approval_statistics({case["case_id"]: case})
    # Hold (1), dispatch pause (1), supplier (1), customer dual approval (2)
    assert stats["approval_decisions_left"] == 5
    assert stats["waiting_tasks"] == 4
    assert stats["all_routing_complete"] is False
