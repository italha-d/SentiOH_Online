from __future__ import annotations
import uuid

from .audit import add_event, now_iso
from .roles import (
    QUALITY_FOOD_SAFETY_MANAGER,
    RECALL_INCIDENT_MANAGER,
)


def _review(
    title,
    assigned_role,
    priority,
    description,
    evidence=None,
    review_type="EVIDENCE_REVIEW",
):
    return {
        "review_id": "REV-" + uuid.uuid4().hex[:7].upper(),
        "title": title,
        "assigned_role": assigned_role,
        "priority": priority,
        "review_type": review_type,
        "status": "WAITING_FOR_REVIEW",
        "description": description,
        "evidence": evidence or {},
        "created_time": now_iso(),
        "reviewed_time": None,
        "reviewed_by": None,
        "reviewed_by_role": None,
        "comment": None,
    }


def create_reviews(exposure, include_revision_review=False):
    evidence = {
        "recall_id": exposure.get("recall_id"),
        "sku": exposure.get("sku"),
        "batch": exposure.get("batch"),
        "matched_batches": exposure.get("matched_batches") or [],
        "reason_code": exposure.get("reason_code"),
        "stock": exposure.get("stock", 0),
        "dispatched": exposure.get("dispatched", 0),
    }

    reviews = []

    if exposure.get("status") == "CONFIRMED":
        reviews.append(
            _review(
                "Review confirmed exposure finding",
                QUALITY_FOOD_SAFETY_MANAGER,
                "HIGH",
                "A human food-safety reviewer must acknowledge the confirmed exposure result and its evidence before the case can be considered fully reviewed.",
                evidence,
                "EXPOSURE_REVIEW",
            )
        )
        if int(exposure.get("dispatched") or 0) > 0:
            reviews.append(
                _review(
                    "Review downstream distribution trace",
                    RECALL_INCIDENT_MANAGER,
                    "HIGH",
                    "Affected units were dispatched downstream. The incident lead must review the trace before response completion.",
                    evidence,
                    "DISTRIBUTION_REVIEW",
                )
            )

    elif exposure.get("status") == "POSSIBLE":
        reviews.append(
            _review(
                "Review unresolved exposure evidence",
                QUALITY_FOOD_SAFETY_MANAGER,
                "HIGH",
                "The exposure remains POSSIBLE because decisive evidence is missing. A human reviewer must acknowledge the uncertainty and evidence-gathering requirement.",
                evidence,
                "UNCERTAINTY_REVIEW",
            )
        )

    if include_revision_review:
        reviews.insert(
            0,
            _review(
                "Review revised recall scope",
                RECALL_INCIDENT_MANAGER,
                "HIGH",
                "The recall scope changed and SentiOH re-analysed the existing case. The incident manager must review the revised scope and resulting response impact.",
                evidence,
                "RECALL_REVISION_REVIEW",
            ),
        )

    return reviews


def add_rejection_followup_review(case, task, rejection_decision):
    existing = next(
        (
            review
            for review in case.get("reviews", [])
            if review.get("review_type") == "REJECTED_ACTION_REVIEW"
            and review.get("evidence", {}).get("task_id") == task.get("task_id")
            and review.get("status") == "WAITING_FOR_REVIEW"
        ),
        None,
    )
    if existing:
        return existing

    review = _review(
        f"Review rejected action: {task.get('title')}",
        RECALL_INCIDENT_MANAGER,
        "HIGH",
        "An authorised user rejected a proposed protected action. The rejection does not change the exposure result, so the incident manager must review the consequence and decide the next operational path.",
        {
            "task_id": task.get("task_id"),
            "task_title": task.get("title"),
            "rejected_by": rejection_decision.get("approver"),
            "rejected_by_role": rejection_decision.get("approver_role"),
            "rejection_reason": rejection_decision.get("comment"),
            "exposure_status": case.get("exposure", {}).get("status"),
        },
        "REJECTED_ACTION_REVIEW",
    )
    case.setdefault("reviews", []).append(review)
    add_event(
        case,
        "REVIEW_REQUIRED_AFTER_REJECTION",
        "SYSTEM",
        {
            "review_id": review["review_id"],
            "task_id": task.get("task_id"),
            "assigned_role": review["assigned_role"],
        },
    )
    return review


def mark_reviewed(case, review_id, reviewer, reviewer_role, comment=""):
    review = next(
        (
            item for item in case.get("reviews", [])
            if item.get("review_id") == review_id
        ),
        None,
    )
    if not review:
        raise ValueError("Review item not found.")
    if review.get("status") == "REVIEWED":
        raise ValueError("This review item has already been reviewed.")
    if reviewer_role != review.get("assigned_role"):
        raise PermissionError(
            f"Role '{reviewer_role}' is not authorised to mark this item reviewed."
        )

    review["status"] = "REVIEWED"
    review["reviewed_time"] = now_iso()
    review["reviewed_by"] = reviewer
    review["reviewed_by_role"] = reviewer_role
    review["comment"] = comment

    add_event(
        case,
        "REVIEW_MARKED_COMPLETE",
        reviewer,
        {
            "review_id": review_id,
            "review_type": review.get("review_type"),
            "reviewer_role": reviewer_role,
            "comment": comment,
        },
    )

    # Local import avoids a circular import at module load time.
    from .states import maybe_resolve_case
    maybe_resolve_case(case, reviewer)
    return case


def review_items_for_role(cases, role):
    rows = []
    for case in cases.values():
        for review in case.get("reviews", []):
            if (
                review.get("status") == "WAITING_FOR_REVIEW"
                and review.get("assigned_role") == role
            ):
                rows.append((case, review))
    return rows


def review_statistics(cases):
    reviews = [
        review
        for case in cases.values()
        for review in case.get("reviews", [])
    ]
    waiting = [
        review for review in reviews
        if review.get("status") == "WAITING_FOR_REVIEW"
    ]
    reviewed = [
        review for review in reviews
        if review.get("status") == "REVIEWED"
    ]
    return {
        "reviews_total": len(reviews),
        "reviews_left": len(waiting),
        "reviews_completed": len(reviewed),
        "all_reviews_complete": bool(reviews) and not waiting,
    }
