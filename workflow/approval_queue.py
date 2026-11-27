from __future__ import annotations


def approved_roles(task):
    return {
        item.get("approver_role")
        for item in task.get("approvals", [])
        if item.get("decision") == "APPROVED"
    }


def task_dependencies_complete(case, task):
    required = list(task.get("depends_on_task_ids") or [])
    if not required:
        return True

    by_id = {
        item.get("task_id"): item
        for item in case.get("tasks", [])
    }
    return all(
        by_id.get(task_id, {}).get("status") == "COMPLETED"
        for task_id in required
    )


def role_has_decided(task, role):
    return any(
        item.get("approver_role") == role
        for item in task.get("approvals", [])
    )


def remaining_approval_roles(task):
    if not task.get("requires_approval"):
        return []
    if task.get("status") in {"APPROVED", "REJECTED", "COMPLETED"}:
        return []

    roles = list(task.get("approval_roles") or [])
    if task.get("approval_mode") == "ALL_ROLES":
        done = approved_roles(task)
        return [role for role in roles if role not in done]

    # ANY_ONE: a single decision completes the gate. Until then every listed
    # authority is eligible, but the number of decisions still required is 1.
    return roles


def approvals_left(task):
    if not task.get("requires_approval"):
        return 0
    if task.get("status") in {"APPROVED", "REJECTED", "COMPLETED"}:
        return 0
    if task.get("approval_mode") == "ALL_ROLES":
        return len(remaining_approval_roles(task))
    return 1


def approval_progress(task):
    required = (
        len(task.get("approval_roles") or [])
        if task.get("approval_mode") == "ALL_ROLES"
        else 1 if task.get("requires_approval") else 0
    )
    left = approvals_left(task)
    completed = max(required - left, 0)
    return {
        "required": required,
        "completed": completed,
        "left": left,
        "status": task.get("status"),
    }


def approval_tasks_for_role(cases, role, username=None):
    rows = []
    for case in cases.values():
        for task in case.get("tasks", []):
            if (
                task.get("status") == "WAITING_FOR_APPROVAL"
                and task_dependencies_complete(case, task)
                and role in remaining_approval_roles(task)
                and (
                    not task.get("approval_usernames")
                    or username is None
                    or username in task.get("approval_usernames", [])
                )
                and not role_has_decided(task, role)
            ):
                rows.append((case, task))
    return rows


def work_tasks_for_role(cases, role):
    rows = []
    for case in cases.values():
        for task in case.get("tasks", []):
            if (
                task.get("assigned_to") == role
                and task.get("status") in {"PENDING", "APPROVED"}
            ):
                rows.append((case, task))
    return rows


def approval_statistics(cases):
    protected = []
    for case in cases.values():
        for task in case.get("tasks", []):
            if task.get("requires_approval"):
                protected.append(task)

    left = sum(approvals_left(task) for task in protected)
    approved_decisions = sum(
        1
        for task in protected
        for item in task.get("approvals", [])
        if item.get("decision") == "APPROVED"
    )
    rejected_actions = sum(task.get("status") == "REJECTED" for task in protected)
    waiting_tasks = sum(task.get("status") == "WAITING_FOR_APPROVAL" for task in protected)

    return {
        "protected_tasks": len(protected),
        "approval_decisions_left": left,
        "approved_decisions": approved_decisions,
        "rejected_actions": rejected_actions,
        "waiting_tasks": waiting_tasks,
        "all_routing_complete": bool(protected) and left == 0,
        "all_approved": bool(protected) and left == 0 and rejected_actions == 0,
    }
