import pytest

from workflow.workflow import open_case
from workflow.approvals import approve_task, reject_task, complete_task
from workflow.states import transition_case, close_case
from workflow.roles import (
    WAREHOUSE_MANAGER,
    WAREHOUSE_OPERATOR,
    STORE_SITE_MANAGER,
    QUALITY_FOOD_SAFETY_MANAGER,
    RECALL_INCIDENT_MANAGER,
    PROCUREMENT_MANAGER,
    SENIOR_RESPONSIBLE_MANAGER,
)

EXPOSURE = {
    "recall_id": "R-GOV",
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


def test_protected_tasks_define_role_based_authority():
    case = open_case(EXPOSURE)
    hold = _task(case, "Hold remaining stock")
    assert hold["assigned_to"] == "Warehouse Operator"
    assert set(hold["approval_roles"]) == {WAREHOUSE_MANAGER, STORE_SITE_MANAGER}
    assert hold["approval_mode"] == "ANY_ONE"

    customer = _task(case, "Prepare customer communication draft")
    assert set(customer["approval_roles"]) == {
        QUALITY_FOOD_SAFETY_MANAGER,
        RECALL_INCIDENT_MANAGER,
    }
    assert customer["approval_mode"] == "ALL_ROLES"


def test_unauthorised_role_cannot_approve_or_reject():
    case = open_case(EXPOSURE)
    hold = _task(case, "Hold remaining stock")
    with pytest.raises(PermissionError):
        approve_task(
            case,
            hold["task_id"],
            "Demo Operator",
            "No authority",
            approver_role=WAREHOUSE_OPERATOR,
        )
    with pytest.raises(PermissionError):
        reject_task(
            case,
            hold["task_id"],
            "Demo Operator",
            "No authority",
            approver_role=WAREHOUSE_OPERATOR,
        )


def test_any_one_authorised_manager_can_approve_stock_hold():
    case = open_case(EXPOSURE)
    hold = _task(case, "Hold remaining stock")
    approve_task(
        case,
        hold["task_id"],
        "Galway Warehouse Manager",
        "Containment approved",
        approver_role=WAREHOUSE_MANAGER,
    )
    assert hold["status"] == "APPROVED"
    complete_task(case, hold["task_id"], "Warehouse Operator")
    assert hold["status"] == "COMPLETED"


def test_dual_approval_remains_blocked_until_both_roles_approve():
    case = open_case(EXPOSURE)
    customer = _task(case, "Prepare customer communication draft")

    approve_task(
        case,
        customer["task_id"],
        "Food Safety Lead",
        "Clinical wording checked",
        approver_role=QUALITY_FOOD_SAFETY_MANAGER,
    )
    assert customer["status"] == "WAITING_FOR_APPROVAL"
    with pytest.raises(PermissionError):
        complete_task(case, customer["task_id"], "Customer Communications Team")

    approve_task(
        case,
        customer["task_id"],
        "Incident Lead",
        "Response scope checked",
        approver_role=RECALL_INCIDENT_MANAGER,
    )
    assert customer["status"] == "APPROVED"


def test_rejection_requires_reason_and_does_not_change_exposure_truth():
    case = open_case(EXPOSURE)
    supplier = _task(case, "Prepare supplier communication draft")

    with pytest.raises(ValueError):
        reject_task(
            case,
            supplier["task_id"],
            "Procurement Manager",
            "",
            approver_role=PROCUREMENT_MANAGER,
        )

    reject_task(
        case,
        supplier["task_id"],
        "Procurement Manager",
        "Supplier has already acknowledged through an existing controlled channel.",
        approver_role=PROCUREMENT_MANAGER,
    )
    assert supplier["status"] == "REJECTED"
    assert case["exposure"]["status"] == "CONFIRMED"
    assert case["state"] == "CONFIRMED"


def test_case_closure_requires_incident_or_senior_authority():
    case = open_case(EXPOSURE)
    transition_case(case, "RESPONDING")
    transition_case(case, "RESOLVED")

    with pytest.raises(PermissionError):
        close_case(
            case,
            "Warehouse Manager",
            "Attempted close",
            actor_role=WAREHOUSE_MANAGER,
        )

    close_case(
        case,
        "Senior Responsible Manager",
        "All evidence reviewed",
        actor_role=SENIOR_RESPONSIBLE_MANAGER,
    )
    assert case["state"] == "CLOSED"
