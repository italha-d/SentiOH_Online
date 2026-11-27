from __future__ import annotations
from .audit import add_event, now_iso
from .roles import CASE_CLOSURE_ROLES

CASE_STATES = {
    "DETECTED",
    "ANALYSING",
    "REVIEW_REQUIRED",
    "CONFIRMED",
    "RESPONDING",
    "RESOLVED",
    "CLOSED",
}

ALLOWED_TRANSITIONS = {
    "DETECTED": {"ANALYSING", "CLOSED"},
    "ANALYSING": {"REVIEW_REQUIRED", "CONFIRMED", "CLOSED"},
    "REVIEW_REQUIRED": {"ANALYSING", "CONFIRMED", "RESOLVED", "CLOSED"},
    "CONFIRMED": {"RESPONDING", "ANALYSING"},
    "RESPONDING": {"RESOLVED", "ANALYSING"},
    "RESOLVED": {"CLOSED", "ANALYSING"},
    "CLOSED": {"ANALYSING"},
}


def transition_case(case, new_state, actor="SYSTEM", details=None):
    old_state = case.get("state")
    if new_state not in CASE_STATES:
        raise ValueError(f"Unknown case state: {new_state}")
    if old_state == new_state:
        return case
    if old_state not in CASE_STATES:
        raise ValueError(f"Unknown current case state: {old_state}")
    if new_state not in ALLOWED_TRANSITIONS.get(old_state, set()):
        raise ValueError(f"Invalid case transition: {old_state} -> {new_state}")

    case["state"] = new_state
    case["updated_time"] = now_iso()
    add_event(
        case,
        "CASE_STATE_CHANGED",
        actor,
        {"from": old_state, "to": new_state, **(details or {})},
    )
    return case



def maybe_resolve_case(case, actor="SYSTEM"):
    """
    Resolve a response case when every task is complete and every required
    human review has been acknowledged.

    CONFIRMED cases complete the normal response workflow.

    POSSIBLE cases remain classified as POSSIBLE. Completing their
    evidence-gathering cycle resolves the case workflow without pretending
    that the deterministic exposure classification changed. New evidence or a
    later recall update can still reopen the case for re-analysis.
    """
    if case.get("state") not in {
        "REVIEW_REQUIRED",
        "CONFIRMED",
        "RESPONDING",
    }:
        return False

    tasks = case.get("tasks", [])
    reviews = case.get("reviews", [])

    tasks_complete = bool(tasks) and all(
        task.get("status") == "COMPLETED" for task in tasks
    )
    reviews_complete = all(
        review.get("status") == "REVIEWED" for review in reviews
    )

    if not (tasks_complete and reviews_complete):
        return False

    exposure_status = (case.get("exposure") or {}).get("status")

    if case.get("state") == "REVIEW_REQUIRED":
        case["resolution"] = {
            "resolution_type": "POSSIBLE_EVIDENCE_CYCLE_COMPLETE",
            "exposure_status": exposure_status,
            "resolved_time": now_iso(),
            "note": (
                "All assigned evidence-gathering tasks and required reviews "
                "were completed. Exposure remains POSSIBLE unless new evidence "
                "supports deterministic re-analysis."
            ),
            "reanalysis_if_new_evidence": True,
        }
        transition_case(
            case,
            "RESOLVED",
            actor,
            {
                "reason": (
                    "POSSIBLE evidence-gathering cycle and required human "
                    "reviews completed; exposure classification remains POSSIBLE"
                ),
                "exposure_status_unchanged": exposure_status,
            },
        )
        return True

    if case.get("state") == "CONFIRMED":
        transition_case(case, "RESPONDING", actor)

    case["resolution"] = {
        "resolution_type": "CONFIRMED_RESPONSE_COMPLETE",
        "exposure_status": exposure_status,
        "resolved_time": now_iso(),
        "note": (
            "All operational response tasks and required human reviews "
            "were completed."
        ),
        "reanalysis_if_new_evidence": True,
    }
    transition_case(
        case,
        "RESOLVED",
        actor,
        {"reason": "All operational tasks and required human reviews completed"},
    )
    return True


def close_case(case, actor="", comment="", actor_role=None):
    if case.get("state") != "RESOLVED":
        raise ValueError("Only a RESOLVED case can be closed.")
    if actor_role not in CASE_CLOSURE_ROLES:
        raise PermissionError(
            "Case closure requires a Recall / Incident Manager or Senior Responsible Manager."
        )

    closed_time = now_iso()
    case["closure"] = {
        "closed_by": actor or actor_role,
        "closed_by_role": actor_role,
        "closed_time": closed_time,
        "comment": comment,
        "final_exposure_status": (case.get("exposure") or {}).get("status"),
    }

    return transition_case(
        case,
        "CLOSED",
        actor or actor_role,
        {
            "comment": comment,
            "actor_role": actor_role,
            "closed_time": closed_time,
            "final_exposure_status": (case.get("exposure") or {}).get("status"),
        },
    )
