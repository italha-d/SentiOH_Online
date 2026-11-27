import uuid
from .audit import now_iso, add_event
from .tasks import create_tasks
from .states import transition_case
from .reviews import create_reviews


def open_case(exposure):
    if exposure.get("status") not in {"CONFIRMED", "POSSIBLE"}:
        raise ValueError("Only CONFIRMED or POSSIBLE exposures can open a response case.")

    case = {
        "case_id": "CASE-" + uuid.uuid4().hex[:8].upper(),
        "recall_id": exposure.get("recall_id"),
        "state": "DETECTED",
        "created_time": now_iso(),
        "updated_time": now_iso(),
        "exposure": dict(exposure),
        "tasks": [],
        "reviews": [],
        "audit_timeline": [],
        "recall_version": None,
        "needs_reanalysis": False,
    }
    add_event(
        case,
        "CASE_CREATED",
        "SYSTEM",
        {"state": "DETECTED", "exposure_status": exposure["status"]},
    )

    transition_case(case, "ANALYSING", "SYSTEM")
    target = "CONFIRMED" if exposure["status"] == "CONFIRMED" else "REVIEW_REQUIRED"
    transition_case(case, target, "SYSTEM")

    case["tasks"] = create_tasks(exposure)
    case["reviews"] = create_reviews(exposure)
    add_event(case, "TASKS_CREATED", "SYSTEM", {"count": len(case["tasks"])})
    add_event(case, "REVIEWS_CREATED", "SYSTEM", {"count": len(case["reviews"])})
    return case
