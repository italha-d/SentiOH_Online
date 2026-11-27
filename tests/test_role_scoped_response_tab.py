from __future__ import annotations

from ui.single_dashboard import (
    _role_response_cases,
    _role_response_items_for_case,
)
from workflow.approvals import approve_task
from workflow.roles import (
    COMMUNICATIONS_TEAM,
    LOGISTICS_MANAGER,
    LOGISTICS_OPERATOR,
    PROCUREMENT_MANAGER,
    PROCUREMENT_TEAM,
    QUALITY_FOOD_SAFETY_MANAGER,
    RECALL_INCIDENT_MANAGER,
    SENIOR_RESPONSIBLE_MANAGER,
    STORE_SITE_MANAGER,
    WAREHOUSE_MANAGER,
    WAREHOUSE_OPERATOR,
)
from workflow.workflow import open_case


def _confirmed_case():
    return open_case({
        "recall_id": "FSAI_TEST_ROLE_SCOPE",
        "sku": "SKU-ROLE",
        "product_name": "Role Test Product",
        "status": "CONFIRMED",
        "batch": "LOT-1",
        "matched_batches": ["LOT-1"],
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
        "stock": 20,
        "dispatched": 8,
    })


def _possible_case():
    return open_case({
        "recall_id": "FSAI_TEST_POSSIBLE_ROLE_SCOPE",
        "sku": "SKU-POSSIBLE",
        "product_name": "Possible Product",
        "status": "POSSIBLE",
        "batch": None,
        "matched_batches": [],
        "reason_code": "LOT_INFORMATION_MISSING",
        "stock": 15,
        "dispatched": 4,
    })


def _titles(items):
    return {task["title"] for task in items["tasks"]}


def test_confirmed_case_shows_only_role_relevant_tasks_and_reviews():
    case = _confirmed_case()

    warehouse_operator = _role_response_items_for_case(
        case,
        WAREHOUSE_OPERATOR,
    )
    assert _titles(warehouse_operator) == {
        "Hold remaining stock",
        "Verify physical quantity",
    }
    assert len(warehouse_operator["reviews"]) == 0

    warehouse_manager = _role_response_items_for_case(
        case,
        WAREHOUSE_MANAGER,
    )
    assert _titles(warehouse_manager) == {
        "Hold remaining stock",
        "Pause further dispatch of affected lot",
    }
    assert warehouse_manager["approval_task_ids"] == {
        task["task_id"]
        for task in warehouse_manager["tasks"]
    }

    site_manager = _role_response_items_for_case(
        case,
        STORE_SITE_MANAGER,
    )
    assert _titles(site_manager) == {
        "Hold remaining stock",
    }

    logistics_operator = _role_response_items_for_case(
        case,
        LOGISTICS_OPERATOR,
    )
    assert _titles(logistics_operator) == {
        "Trace downstream distribution",
        "Pause further dispatch of affected lot",
    }

    logistics_manager = _role_response_items_for_case(
        case,
        LOGISTICS_MANAGER,
    )
    assert _titles(logistics_manager) == {
        "Pause further dispatch of affected lot",
    }

    procurement_team = _role_response_items_for_case(
        case,
        PROCUREMENT_TEAM,
    )
    assert _titles(procurement_team) == {
        "Prepare supplier communication draft",
    }

    procurement_manager = _role_response_items_for_case(
        case,
        PROCUREMENT_MANAGER,
    )
    assert _titles(procurement_manager) == {
        "Prepare supplier communication draft",
    }

    communications = _role_response_items_for_case(
        case,
        COMMUNICATIONS_TEAM,
    )
    assert _titles(communications) == {
        "Prepare customer communication draft",
    }

    quality = _role_response_items_for_case(
        case,
        QUALITY_FOOD_SAFETY_MANAGER,
    )
    assert _titles(quality) == {
        "Prepare customer communication draft",
        "Record completion evidence",
    }
    assert {
        review["title"]
        for review in quality["reviews"]
    } == {
        "Review confirmed exposure finding",
    }

    incident = _role_response_items_for_case(
        case,
        RECALL_INCIDENT_MANAGER,
    )
    assert _titles(incident) == {
        "Prepare customer communication draft",
    }
    assert {
        review["title"]
        for review in incident["reviews"]
    } == {
        "Review downstream distribution trace",
    }

    senior = _role_response_items_for_case(
        case,
        SENIOR_RESPONSIBLE_MANAGER,
    )
    assert senior["total"] == 0


def test_possible_case_is_role_scoped():
    case = _possible_case()

    warehouse = _role_response_items_for_case(
        case,
        WAREHOUSE_OPERATOR,
    )
    assert _titles(warehouse) == {
        "Verify physical batch or lot",
    }

    quality = _role_response_items_for_case(
        case,
        QUALITY_FOOD_SAFETY_MANAGER,
    )
    assert _titles(quality) == {
        "Check use-by/best-before evidence",
    }
    assert {
        review["title"]
        for review in quality["reviews"]
    } == {
        "Review unresolved exposure evidence",
    }

    procurement = _role_response_items_for_case(
        case,
        PROCUREMENT_TEAM,
    )
    assert _titles(procurement) == {
        "Request missing supplier documentation",
    }

    manager = _role_response_items_for_case(
        case,
        WAREHOUSE_MANAGER,
    )
    assert manager["total"] == 0


def test_assigned_protected_task_stays_visible_while_waiting_for_approval():
    case = _confirmed_case()

    before = _role_response_items_for_case(
        case,
        WAREHOUSE_OPERATOR,
    )
    hold = next(
        task
        for task in before["tasks"]
        if task["title"] == "Hold remaining stock"
    )
    assert hold["status"] == "WAITING_FOR_APPROVAL"
    assert hold["task_id"] in before["operational_task_ids"]
    assert hold["task_id"] not in before["approval_task_ids"]


def test_task_becomes_ready_for_assigned_operator_after_authorised_approval():
    case = _confirmed_case()
    hold = next(
        task
        for task in case["tasks"]
        if task["title"] == "Hold remaining stock"
    )

    approve_task(
        case,
        hold["task_id"],
        "Warehouse Manager Test",
        "Approved for containment.",
        approver_role=WAREHOUSE_MANAGER,
    )

    warehouse = _role_response_items_for_case(
        case,
        WAREHOUSE_OPERATOR,
    )
    refreshed = next(
        task
        for task in warehouse["tasks"]
        if task["title"] == "Hold remaining stock"
    )

    assert refreshed["status"] == "APPROVED"
    assert refreshed["task_id"] in warehouse["operational_task_ids"]


def test_response_case_list_contains_only_cases_requiring_logged_in_role():
    confirmed = _confirmed_case()
    possible = _possible_case()

    cases = {
        confirmed["case_id"]: confirmed,
        possible["case_id"]: possible,
    }

    warehouse_manager_cases = _role_response_cases(
        cases,
        WAREHOUSE_MANAGER,
    )
    assert set(warehouse_manager_cases) == {
        confirmed["case_id"],
    }

    procurement_team_cases = _role_response_cases(
        cases,
        PROCUREMENT_TEAM,
    )
    assert set(procurement_team_cases) == {
        confirmed["case_id"],
        possible["case_id"],
    }


def test_resolved_case_closure_is_visible_only_to_closure_roles():
    case = _confirmed_case()
    for task in case["tasks"]:
        task["status"] = "COMPLETED"
    for review in case["reviews"]:
        review["status"] = "REVIEWED"
    case["state"] = "RESOLVED"

    incident = _role_response_items_for_case(
        case,
        RECALL_INCIDENT_MANAGER,
    )
    senior = _role_response_items_for_case(
        case,
        SENIOR_RESPONSIBLE_MANAGER,
    )
    warehouse = _role_response_items_for_case(
        case,
        WAREHOUSE_OPERATOR,
    )

    assert incident["can_close"] is True
    assert senior["can_close"] is True
    assert warehouse["can_close"] is False
    assert warehouse["total"] == 0


def test_response_tab_source_is_explicitly_role_scoped():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (
        root / "ui" / "single_dashboard.py"
    ).read_text(encoding="utf-8")

    assert 'st.header("4. Response Cases")' in source
    assert 'st.subheader("My Response Actions")' in source
    assert "Only actions assigned to, awaiting approval from, or awaiting review by this logged-in role are shown." in source
    assert "_role_response_cases(" in source
    assert 'st.subheader(f"Actions for {current_role}")' in source
    assert "Actions owned by other roles are hidden from this Response tab." in source
