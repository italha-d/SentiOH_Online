import pytest

from workflow.workflow import open_case
from workflow.reviews import (
    mark_reviewed,
    review_items_for_role,
)
from workflow.approvals import reject_task
from workflow.roles import (
    QUALITY_FOOD_SAFETY_MANAGER,
    RECALL_INCIDENT_MANAGER,
    PROCUREMENT_MANAGER,
)

EXPOSURE = {
    "recall_id": "R-REV",
    "sku": "SKU001",
    "product_name": "Demo Product",
    "status": "CONFIRMED",
    "batch": "LOT1",
    "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
    "stock": 10,
    "dispatched": 4,
}


def test_confirmed_case_creates_required_human_reviews():
    case = open_case(EXPOSURE)
    titles = {review["title"] for review in case["reviews"]}
    assert "Review confirmed exposure finding" in titles
    assert "Review downstream distribution trace" in titles


def test_review_is_only_visible_to_assigned_role():
    case = open_case(EXPOSURE)
    cases = {case["case_id"]: case}

    quality = review_items_for_role(cases, QUALITY_FOOD_SAFETY_MANAGER)
    incident = review_items_for_role(cases, RECALL_INCIDENT_MANAGER)

    assert any(
        review["title"] == "Review confirmed exposure finding"
        for _, review in quality
    )
    assert any(
        review["title"] == "Review downstream distribution trace"
        for _, review in incident
    )


def test_unauthorised_role_cannot_mark_reviewed():
    case = open_case(EXPOSURE)
    review = next(
        review for review in case["reviews"]
        if review["title"] == "Review confirmed exposure finding"
    )
    with pytest.raises(PermissionError):
        mark_reviewed(
            case,
            review["review_id"],
            "Procurement Manager",
            PROCUREMENT_MANAGER,
            "Not my review",
        )


def test_mark_as_reviewed_records_actor_role_and_time():
    case = open_case(EXPOSURE)
    review = next(
        review for review in case["reviews"]
        if review["title"] == "Review confirmed exposure finding"
    )
    mark_reviewed(
        case,
        review["review_id"],
        "Food Safety Lead",
        QUALITY_FOOD_SAFETY_MANAGER,
        "Evidence checked",
    )
    assert review["status"] == "REVIEWED"
    assert review["reviewed_by"] == "Food Safety Lead"
    assert review["reviewed_by_role"] == QUALITY_FOOD_SAFETY_MANAGER
    assert review["reviewed_time"]


def test_rejected_protected_action_creates_incident_followup_review():
    case = open_case(EXPOSURE)
    supplier = next(
        task for task in case["tasks"]
        if task["title"] == "Prepare supplier communication draft"
    )
    reject_task(
        case,
        supplier["task_id"],
        "Procurement Manager",
        "Supplier already handled through controlled channel.",
        approver_role=PROCUREMENT_MANAGER,
    )
    followups = [
        review for review in case["reviews"]
        if review["review_type"] == "REJECTED_ACTION_REVIEW"
    ]
    assert len(followups) == 1
    assert followups[0]["assigned_role"] == RECALL_INCIDENT_MANAGER
    assert followups[0]["status"] == "WAITING_FOR_REVIEW"
