from workflow.workflow import open_case
from workflow.action_center import (
    human_action_summary,
    personal_action_summary,
    case_action_progress,
    management_case_rows,
    case_attention_rows,
)
from workflow.roles import (
    WAREHOUSE_MANAGER,
    QUALITY_FOOD_SAFETY_MANAGER,
    RECALL_INCIDENT_MANAGER,
)

EXPOSURE = {
    "recall_id": "R-ACTION",
    "sku": "SKU001",
    "product_name": "Demo Product",
    "status": "CONFIRMED",
    "batch": "LOT1",
    "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
    "stock": 10,
    "dispatched": 4,
}


def test_human_action_summary_counts_approvals_reviews_and_operations():
    case = open_case(EXPOSURE)
    summary = human_action_summary({case["case_id"]: case})
    assert summary["approval_decisions_left"] == 5
    assert summary["reviews_left"] == 2
    assert summary["operational_tasks_left"] >= 3
    assert summary["total_human_actions_left"] > summary["approval_decisions_left"]


def test_personal_action_summary_routes_correct_action_types():
    case = open_case(EXPOSURE)
    cases = {case["case_id"]: case}

    warehouse = personal_action_summary(cases, WAREHOUSE_MANAGER)
    quality = personal_action_summary(cases, QUALITY_FOOD_SAFETY_MANAGER)
    incident = personal_action_summary(cases, RECALL_INCIDENT_MANAGER)

    assert warehouse["approval_count"] >= 1
    assert quality["review_count"] >= 1
    assert incident["review_count"] >= 1


def test_case_progress_and_management_rows_show_remaining_human_actions():
    case = open_case(EXPOSURE)
    progress = case_action_progress(case)
    assert progress["approval_required"] == 5
    assert progress["approval_left"] == 5
    assert progress["reviews_required"] == 2
    assert progress["reviews_left"] == 2

    rows = management_case_rows({case["case_id"]: case})
    assert rows[0]["case_id"] == case["case_id"]
    assert rows[0]["human_actions_left"] == progress["total_human_actions_left"]


def test_attention_rows_identify_who_must_act():
    case = open_case(EXPOSURE)
    rows = case_attention_rows(case)
    assert any(
        row["type"] == "APPROVAL"
        and "Warehouse Manager" in row["required_from"]
        for row in rows
    )
    assert any(
        row["type"] == "REVIEW"
        and row["required_from"] == QUALITY_FOOD_SAFETY_MANAGER
        for row in rows
    )
    assert any(row["type"] == "OPERATION" for row in rows)
