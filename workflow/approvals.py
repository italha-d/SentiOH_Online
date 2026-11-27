from .audit import add_event, now_iso
from .states import transition_case, maybe_resolve_case
from .reviews import add_rejection_followup_review
from .approval_queue import task_dependencies_complete


def _get_task(case, task_id):
    return next(x for x in case["tasks"] if x["task_id"] == task_id)


def _authorised(task, approver_role, approver_username=None):
    if approver_role not in set(task.get("approval_roles") or []):
        return False
    allowed_users = set(task.get("approval_usernames") or [])
    if allowed_users:
        return approver_username in allowed_users
    return True


def _approval_complete(task):
    roles = set(task.get("approval_roles") or [])
    approved_roles = {
        item.get("approver_role")
        for item in task.get("approvals", [])
        if item.get("decision") == "APPROVED"
    }
    if task.get("approval_mode") == "ALL_ROLES":
        return bool(roles) and roles.issubset(approved_roles)
    return bool(approved_roles & roles)


def approve_task(case, task_id, approver, comment="", approver_role=None, approver_username=None):
    task = _get_task(case, task_id)
    if not task["requires_approval"]:
        raise ValueError("Task does not require approval.")
    if not approver_role:
        raise PermissionError("An approver role must be supplied.")
    if not _authorised(task, approver_role, approver_username):
        allowed = task.get("approval_usernames") or []
        if allowed:
            raise PermissionError(
                f"This approval is assigned to authorised account(s): {', '.join(allowed)}."
            )
        raise PermissionError(
            f"Role '{approver_role}' is not authorised to approve this task."
        )
    if not task_dependencies_complete(case, task):
        raise PermissionError(
            "This approval is not active yet because its prerequisite demo approval has not been completed."
        )
    if task.get("status") == "REJECTED":
        raise PermissionError("A rejected task cannot be approved without reopening it.")

    existing = next(
        (
            item for item in task.get("approvals", [])
            if item.get("approver_role") == approver_role
            and item.get("decision") == "APPROVED"
        ),
        None,
    )
    if existing:
        raise ValueError(f"{approver_role} has already approved this task.")

    decision = {
        "decision": "APPROVED",
        "approver": approver,
        "approver_role": approver_role,
        "approver_username": approver_username,
        "comment": comment,
        "time": now_iso(),
    }
    task.setdefault("approvals", []).append(decision)
    add_event(
        case,
        "TASK_APPROVAL_RECORDED",
        approver,
        {
            "task_id": task_id,
            "approver_role": approver_role,
            "approval_mode": task.get("approval_mode"),
            "comment": comment,
        },
    )

    if _approval_complete(task):
        task["approval"] = {
            "decision": "APPROVED",
            "approver": approver,
            "approver_role": approver_role,
            "comment": comment,
            "time": decision["time"],
        }
        add_event(
            case,
            "TASK_APPROVED",
            approver,
            {
                "task_id": task_id,
                "approver_role": approver_role,
                "approval_mode": task.get("approval_mode"),
                "approval_only": bool(task.get("approval_only")),
            },
        )

        if task.get("approval_only"):
            task["status"] = "COMPLETED"
            task["completion_time"] = now_iso()
            add_event(
                case,
                "TASK_COMPLETED",
                approver,
                {
                    "task_id": task_id,
                    "completion_mode": "APPROVAL_ONLY",
                    "approver_role": approver_role,
                },
            )
            maybe_resolve_case(case, approver)
        else:
            task["status"] = "APPROVED"
    else:
        task["status"] = "WAITING_FOR_APPROVAL"

    return case


def reject_task(case, task_id, approver, comment="", approver_role=None, approver_username=None):
    task = _get_task(case, task_id)
    if not task["requires_approval"]:
        raise ValueError("Task does not require approval.")
    if not approver_role:
        raise PermissionError("An approver role must be supplied.")
    if not _authorised(task, approver_role, approver_username):
        allowed = task.get("approval_usernames") or []
        if allowed:
            raise PermissionError(
                f"This approval is assigned to authorised account(s): {', '.join(allowed)}."
            )
        raise PermissionError(
            f"Role '{approver_role}' is not authorised to reject this task."
        )
    if not task_dependencies_complete(case, task):
        raise PermissionError(
            "This approval is not active yet because its prerequisite demo approval has not been completed."
        )
    if not str(comment or "").strip():
        raise ValueError("A rejection reason is required for the audit trail.")

    decision = {
        "decision": "REJECTED",
        "approver": approver,
        "approver_role": approver_role,
        "approver_username": approver_username,
        "comment": comment,
        "time": now_iso(),
    }
    task.setdefault("approvals", []).append(decision)
    task["approval"] = decision
    task["status"] = "REJECTED"
    add_event(
        case,
        "TASK_REJECTED",
        approver,
        {
            "task_id": task_id,
            "approver_role": approver_role,
            "comment": comment,
            "exposure_status_unchanged": case.get("exposure", {}).get("status"),
        },
    )
    add_rejection_followup_review(case, task, decision)
    return case


def complete_task(case, task_id, actor, actor_role=None):
    task = _get_task(case, task_id)
    if actor_role is not None and actor_role != task.get("assigned_to"):
        raise PermissionError(
            f"Role '{actor_role}' is not authorised to complete this task; "
            f"it is assigned to '{task.get('assigned_to')}'."
        )
    if task["requires_approval"] and task["status"] != "APPROVED":
        raise PermissionError(
            "All required human approvals must be recorded before this task can be completed."
        )
    if task["status"] == "REJECTED":
        raise PermissionError("A rejected task cannot be completed.")

    task["status"] = "COMPLETED"
    task["completion_time"] = now_iso()
    add_event(
        case,
        "TASK_COMPLETED",
        actor,
        {"task_id": task_id, "actor_role": actor_role},
    )

    maybe_resolve_case(case, actor)
    return case
