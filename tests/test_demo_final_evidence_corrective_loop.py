from workflow.approvals import approve_task
from workflow.quick_demo import (
    _approval_only_task,
    request_demo_corrective_action,
    submit_demo_corrective_evidence,
)
from workflow.roles import STORE_SITE_MANAGER, RECALL_INCIDENT_MANAGER


def _case_with_two_demo_approvals():
    evidence = {"sku": "SKU398", "affected_site_code": "DUB"}
    first = _approval_only_task(
        "Confirm and complete affected stock containment",
        STORE_SITE_MANAGER,
        evidence,
        "Contain stock",
        "Confirmed exposure",
        assigned_username="site.manager",
        assigned_display_name="Dublin Site Manager",
        affected_site_code="DUB",
        affected_site_name="Dublin Distribution Centre",
    )
    first["demo_approval_ordinal"] = 1
    second = _approval_only_task(
        "Review evidence and close the recall case",
        RECALL_INCIDENT_MANAGER,
        evidence,
        "Final review",
        "Final authorised decision",
        assigned_username="incident.manager",
        assigned_display_name="Recall Incident Lead",
    )
    second["demo_approval_ordinal"] = 2
    second["depends_on_task_ids"] = [first["task_id"]]
    case = {
        "case_id": "C-CORRECTIVE",
        "state": "RESPONDING",
        "exposure": {"status": "CONFIRMED"},
        "tasks": [first, second],
        "reviews": [],
        "audit_timeline": [],
    }
    return case, first, second


def test_incident_manager_can_request_corrective_action_and_site_manager_resubmits():
    case, first, second = _case_with_two_demo_approvals()
    approve_task(
        case,
        first["task_id"],
        "Dublin Site Manager",
        "Contained stock and checked location.",
        approver_role=STORE_SITE_MANAGER,
        approver_username="site.manager",
    )
    assert first["status"] == "COMPLETED"

    corrective = request_demo_corrective_action(
        case,
        second["task_id"],
        "Recall Incident Lead",
        RECALL_INCIDENT_MANAGER,
        "Physical stock-count evidence is missing.",
    )
    assert second["status"] == "WAITING_FOR_CORRECTIVE_ACTION"
    assert corrective["status"] == "PENDING"
    assert corrective["assigned_username"] == "site.manager"
    assert corrective["affected_site_code"] == "DUB"
    assert corrective["task_id"] in second["depends_on_task_ids"]

    submit_demo_corrective_evidence(
        case,
        corrective["task_id"],
        "Dublin Site Manager",
        STORE_SITE_MANAGER,
        "site.manager",
        "Physical count rechecked: 17 affected units isolated; stock-hold reference SH-001 attached.",
    )
    assert corrective["status"] == "COMPLETED"
    assert corrective["corrective_submission"]["submitted_by_username"] == "site.manager"
    assert second["status"] == "WAITING_FOR_APPROVAL"
    assert any(event["action"] == "FINAL_EVIDENCE_FURTHER_ACTION_REQUESTED" for event in case["audit_timeline"])
    assert any(event["action"] == "CORRECTIVE_EVIDENCE_SUBMITTED" for event in case["audit_timeline"])


def test_corrective_loop_can_repeat_until_incident_manager_accepts_evidence():
    case, first, second = _case_with_two_demo_approvals()
    approve_task(case, first["task_id"], "Dublin Site Manager", "Contained", approver_role=STORE_SITE_MANAGER, approver_username="site.manager")

    c1 = request_demo_corrective_action(case, second["task_id"], "Recall Incident Lead", RECALL_INCIDENT_MANAGER, "Need stock count")
    submit_demo_corrective_evidence(case, c1["task_id"], "Dublin Site Manager", STORE_SITE_MANAGER, "site.manager", "Stock count supplied")
    c2 = request_demo_corrective_action(case, second["task_id"], "Recall Incident Lead", RECALL_INCIDENT_MANAGER, "Need containment reference")
    submit_demo_corrective_evidence(case, c2["task_id"], "Dublin Site Manager", STORE_SITE_MANAGER, "site.manager", "Containment reference supplied")

    assert second["corrective_rounds"] == 2
    assert len([t for t in case["tasks"] if t.get("demo_corrective_action")]) == 2
    assert second["status"] == "WAITING_FOR_APPROVAL"
    assert len(second["final_review_history"]) == 4


def test_only_incident_manager_can_request_and_assigned_site_manager_can_submit():
    case, first, second = _case_with_two_demo_approvals()
    approve_task(case, first["task_id"], "Dublin Site Manager", "Contained", approver_role=STORE_SITE_MANAGER, approver_username="site.manager")

    try:
        request_demo_corrective_action(case, second["task_id"], "Dublin Site Manager", STORE_SITE_MANAGER, "Need more evidence")
        assert False, "Expected permission error"
    except PermissionError:
        pass

    corrective = request_demo_corrective_action(case, second["task_id"], "Recall Incident Lead", RECALL_INCIDENT_MANAGER, "Need more evidence")
    try:
        submit_demo_corrective_evidence(case, corrective["task_id"], "Other Manager", STORE_SITE_MANAGER, "cork.manager", "Evidence")
        assert False, "Expected permission error"
    except PermissionError:
        pass


def test_case_can_close_only_after_corrective_evidence_returns_for_final_review():
    from workflow.states import close_case

    case, first, second = _case_with_two_demo_approvals()
    approve_task(case, first["task_id"], "Dublin Site Manager", "Contained", approver_role=STORE_SITE_MANAGER, approver_username="site.manager")
    corrective = request_demo_corrective_action(case, second["task_id"], "Recall Incident Lead", RECALL_INCIDENT_MANAGER, "Need verified stock evidence")

    assert case["state"] == "RESPONDING"
    try:
        close_case(case, actor="Recall Incident Lead", actor_role=RECALL_INCIDENT_MANAGER, comment="Too early")
        assert False, "Case must not close while corrective action is outstanding"
    except ValueError:
        pass

    submit_demo_corrective_evidence(case, corrective["task_id"], "Dublin Site Manager", STORE_SITE_MANAGER, "site.manager", "Verified stock evidence submitted")
    approve_task(case, second["task_id"], "Recall Incident Lead", "Evidence accepted", approver_role=RECALL_INCIDENT_MANAGER, approver_username="incident.manager")
    assert case["state"] == "RESOLVED"

    close_case(case, actor="Recall Incident Lead", actor_role=RECALL_INCIDENT_MANAGER, comment="Evidence accepted after correction")
    assert case["state"] == "CLOSED"
