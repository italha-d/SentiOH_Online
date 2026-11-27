from __future__ import annotations

from .approval_queue import (
    approval_statistics,
    approval_progress,
    approval_tasks_for_role,
    remaining_approval_roles,
    work_tasks_for_role,
)
from .reviews import review_statistics, review_items_for_role
from .roles import CASE_CLOSURE_ROLES


def _approval_authority_label(task):
    roles = list(task.get("approval_roles") or [])
    if not roles:
        return ""
    if task.get("approval_mode") == "ALL_ROLES":
        remaining = remaining_approval_roles(task)
        return " + ".join(remaining or roles)
    return " OR ".join(roles)


def human_action_summary(cases):
    approvals = approval_statistics(cases)
    reviews = review_statistics(cases)

    operational = [
        task
        for case in cases.values()
        for task in case.get("tasks", [])
        if task.get("status") in {"PENDING", "APPROVED"}
    ]

    critical_approval_decisions = 0
    for case in cases.values():
        for task in case.get("tasks", []):
            if (
                task.get("requires_approval")
                and task.get("priority") == "HIGH"
                and task.get("status") == "WAITING_FOR_APPROVAL"
            ):
                critical_approval_decisions += approval_progress(task)["left"]

    closure_actions_left = sum(
        case.get("state") == "RESOLVED"
        for case in cases.values()
    )

    total = (
        approvals["approval_decisions_left"]
        + reviews["reviews_left"]
        + len(operational)
        + closure_actions_left
    )

    return {
        **approvals,
        **reviews,
        "operational_tasks_left": len(operational),
        "critical_approval_decisions_left": critical_approval_decisions,
        "closure_actions_left": closure_actions_left,
        "total_human_actions_left": total,
        "all_human_actions_complete": total == 0 and bool(cases),
    }


def personal_action_summary(cases, role, username=None):
    approvals = approval_tasks_for_role(cases, role, username=username)
    reviews = review_items_for_role(cases, role)
    work = work_tasks_for_role(cases, role)
    closures = [
        case
        for case in cases.values()
        if case.get("state") == "RESOLVED"
        and role in CASE_CLOSURE_ROLES
    ]
    return {
        "approvals": approvals,
        "reviews": reviews,
        "work": work,
        "closures": closures,
        "approval_count": len(approvals),
        "review_count": len(reviews),
        "work_count": len(work),
        "closure_count": len(closures),
        "total": (
            len(approvals)
            + len(reviews)
            + len(work)
            + len(closures)
        ),
    }


def case_action_progress(case):
    protected = [
        task for task in case.get("tasks", [])
        if task.get("requires_approval")
    ]
    approval_required = sum(
        approval_progress(task)["required"]
        for task in protected
    )
    approval_left = sum(
        approval_progress(task)["left"]
        for task in protected
    )

    reviews = case.get("reviews", [])
    reviews_left = sum(
        review.get("status") == "WAITING_FOR_REVIEW"
        for review in reviews
    )

    tasks = case.get("tasks", [])
    tasks_completed = sum(
        task.get("status") == "COMPLETED"
        for task in tasks
    )

    operational_left = sum(
        task.get("status") in {"PENDING", "APPROVED"}
        for task in tasks
    )

    closure_left = 1 if case.get("state") == "RESOLVED" else 0
    total_left = approval_left + reviews_left + operational_left + closure_left

    decision_completed = max(approval_required - approval_left, 0)
    approved_decisions = sum(
        1
        for task in protected
        for item in task.get("approvals", [])
        if item.get("decision") == "APPROVED"
    )
    rejected_actions = sum(
        task.get("status") == "REJECTED"
        for task in protected
    )

    return {
        "approval_required": approval_required,
        "approval_completed": decision_completed,
        "approval_decisions_completed": decision_completed,
        "approved_decisions": approved_decisions,
        "rejected_actions": rejected_actions,
        "approval_left": approval_left,
        "reviews_required": len(reviews),
        "reviews_completed": len(reviews) - reviews_left,
        "reviews_left": reviews_left,
        "tasks_total": len(tasks),
        "tasks_completed": tasks_completed,
        "operational_left": operational_left,
        "closure_left": closure_left,
        "total_human_actions_left": total_left,
    }


def management_case_rows(cases):
    rows = []
    for case in cases.values():
        progress = case_action_progress(case)
        rows.append({
            "case_id": case.get("case_id"),
            "recall_id": case.get("recall_id"),
            "exposure": case.get("exposure", {}).get("status"),
            "state": case.get("state"),
            "approval_decisions": (
                f"{progress['approval_decisions_completed']} / "
                f"{progress['approval_required']}"
            ),
            "rejected_actions": progress["rejected_actions"],
            "reviews": (
                f"{progress['reviews_completed']} / "
                f"{progress['reviews_required']}"
            ),
            "tasks": (
                f"{progress['tasks_completed']} / "
                f"{progress['tasks_total']}"
            ),
            "human_actions_left": progress["total_human_actions_left"],
            "updated": case.get("updated_time") or case.get("created_time"),
        })
    rows.sort(key=lambda row: row.get("updated") or "", reverse=True)
    return rows


def case_attention_rows(case):
    rows = []

    for task in case.get("tasks", []):
        if task.get("status") == "WAITING_FOR_APPROVAL":
            progress = approval_progress(task)
            rows.append({
                "type": "APPROVAL",
                "priority": task.get("priority"),
                "action": task.get("title"),
                "required_from": _approval_authority_label(task),
                "status": f"{progress['left']} approval(s) left",
            })
        elif task.get("status") in {"PENDING", "APPROVED"}:
            rows.append({
                "type": "OPERATION",
                "priority": task.get("priority"),
                "action": task.get("title"),
                "required_from": task.get("assigned_to"),
                "status": "Ready to complete",
            })

    for review in case.get("reviews", []):
        if review.get("status") == "WAITING_FOR_REVIEW":
            rows.append({
                "type": "REVIEW",
                "priority": review.get("priority"),
                "action": review.get("title"),
                "required_from": review.get("assigned_role"),
                "status": "Mark as reviewed",
            })

    if case.get("state") == "RESOLVED":
        rows.append({
            "type": "CLOSURE",
            "priority": "HIGH",
            "action": "Final case closure approval",
            "required_from": (
                "Recall / Incident Manager OR Senior Responsible Manager"
            ),
            "status": "Close resolved case",
        })

    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    rows.sort(key=lambda row: (rank.get(row.get("priority"), 3), row["type"]))
    return rows
