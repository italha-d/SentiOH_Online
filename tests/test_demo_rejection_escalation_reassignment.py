from workflow.approvals import reject_task
from workflow.quick_demo import _approval_only_task, reassign_rejected_demo_containment
from workflow.roles import STORE_SITE_MANAGER, RECALL_INCIDENT_MANAGER


def test_rejected_demo_containment_can_be_escalated_and_reassigned_by_incident_manager():
    task = _approval_only_task(
        "Confirm and complete affected stock containment",
        STORE_SITE_MANAGER,
        {"sku": "SKU398"},
        "Contain stock",
        "Confirmed exposure",
        assigned_username="site.manager",
        assigned_display_name="Dublin Site Manager",
        affected_site_code="DUB",
        affected_site_name="Dublin Distribution Centre",
    )
    case = {"case_id": "C-DEMO", "state": "RESPONDING", "exposure": {"status": "CONFIRMED"}, "tasks": [task], "reviews": [], "audit": []}

    reject_task(case, task["task_id"], "Dublin Site Manager", "Stock count needs re-check", approver_role=STORE_SITE_MANAGER, approver_username="site.manager")
    assert task["status"] == "REJECTED"
    assert case["reviews"][0]["status"] == "WAITING_FOR_REVIEW"

    reassign_rejected_demo_containment(case, task["task_id"], "Recall Incident Lead", RECALL_INCIDENT_MANAGER, "DUB")
    assert task["status"] == "WAITING_FOR_APPROVAL"
    assert task["assigned_username"] == "site.manager"
    assert task["approval"] is None
    assert task["approvals"][0]["decision"] == "REJECTED"
    assert task["reissue_count"] == 1
    assert case["reviews"][0]["status"] == "REVIEWED"
    assert any(event["action"] == "REJECTED_TASK_REASSIGNED" for event in case["audit_timeline"])


def test_rejected_demo_containment_cannot_be_reassigned_to_unrelated_city():
    task = _approval_only_task(
        "Confirm and complete affected stock containment",
        STORE_SITE_MANAGER,
        {"sku": "SKU398"},
        "Contain stock",
        "Confirmed exposure",
        assigned_username="site.manager",
        assigned_display_name="Dublin Site Manager",
        affected_site_code="DUB",
        affected_site_name="Dublin Distribution Centre",
    )
    case = {"case_id": "C-DEMO", "state": "RESPONDING", "exposure": {"status": "CONFIRMED"}, "tasks": [task], "reviews": [], "audit": []}
    reject_task(case, task["task_id"], "Dublin Site Manager", "Stock count needs re-check", approver_role=STORE_SITE_MANAGER, approver_username="site.manager")

    import pytest
    with pytest.raises(PermissionError, match="affected stock location"):
        reassign_rejected_demo_containment(
            case, task["task_id"], "Recall Incident Lead",
            RECALL_INCIDENT_MANAGER, "GAL"
        )
