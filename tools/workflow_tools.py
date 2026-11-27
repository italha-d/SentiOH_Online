from __future__ import annotations
import json

from workflow.workflow import open_case
from workflow.tasks import create_tasks
from workflow.audit import add_event, now_iso
from workflow.states import transition_case
from workflow.versioning import register_recall_version
from workflow.reviews import create_reviews


def _exposure_signature(exposure):
    material = {
        "recall_id": exposure.get("recall_id"),
        "sku": exposure.get("sku"),
        "product_name": exposure.get("product_name"),
        "status": exposure.get("status"),
        "batch": exposure.get("batch"),
        "matched_batches": exposure.get("matched_batches") or [],
        "reason_code": exposure.get("reason_code"),
        "product_identifier_match": exposure.get("product_identifier_match"),
        "product_name_match": exposure.get("product_name_match"),
        "brand_match": exposure.get("brand_match"),
        "pack_size_match": exposure.get("pack_size_match"),
        "batch_match": exposure.get("batch_match"),
        "date_match": exposure.get("date_match"),
        "stock": exposure.get("stock"),
        "dispatched": exposure.get("dispatched"),
    }
    return json.dumps(material, sort_keys=True, default=str)


def _find_case_for_recall(ctx, recall_id):
    return next(
        (
            case for case in ctx.cases.values()
            if case.get("recall_id") == recall_id
            and not case.get("demo_archived")
        ),
        None,
    )


def _current_recall(ctx, recall_id):
    return next(
        (
            recall for recall in ctx.data["recalls"]
            if recall.get("recall_id") == recall_id
        ),
        None,
    )


def _set_target_after_analysis(case, exposure, actor="SYSTEM"):
    target = (
        "CONFIRMED"
        if exposure.get("status") == "CONFIRMED"
        else "REVIEW_REQUIRED"
    )
    if case.get("state") != "ANALYSING":
        transition_case(case, "ANALYSING", actor)
    transition_case(case, target, actor)


def open_response_case(ctx, exposure):
    recall_id = exposure.get("recall_id")
    if not recall_id:
        return {"ok": False, "error": "RECALL_ID_MISSING"}

    recall = _current_recall(ctx, recall_id)
    existing = _find_case_for_recall(ctx, recall_id)

    if existing is None:
        case = open_case(exposure)
        case["last_analysis_time"] = now_iso()
        case["analysis_revision"] = 1
        case["task_history"] = []
        if recall:
            register_recall_version(case, recall)
        ctx.cases[case["case_id"]] = case
        ctx.save_case(case)
        return {
            "ok": True,
            "case_id": case["case_id"],
            "case": case,
            "case_action": "CREATED",
            "case_changed": True,
        }

    if recall:
        register_recall_version(existing, recall)

    old_signature = _exposure_signature(existing.get("exposure", {}))
    new_signature = _exposure_signature(exposure)

    # Unchanged exposure and no outstanding recall reanalysis means a true
    # idempotent re-run. Preserve task state and audit history exactly.
    if old_signature == new_signature and not existing.get("needs_reanalysis"):
        return {
            "ok": True,
            "case_id": existing["case_id"],
            "case": existing,
            "case_action": "REUSED_UNCHANGED",
            "case_changed": False,
        }

    previous_exposure = dict(existing.get("exposure", {}))
    existing.setdefault("task_history", []).append({
        "archived_time": now_iso(),
        "reason": "Exposure evidence or recall version changed during re-analysis.",
        "tasks": list(existing.get("tasks", [])),
    })
    existing.setdefault("review_history", []).append({
        "archived_time": now_iso(),
        "reason": "Exposure evidence or recall version changed during re-analysis.",
        "reviews": list(existing.get("reviews", [])),
    })

    existing["exposure"] = dict(exposure)
    existing["tasks"] = create_tasks(exposure)
    existing["reviews"] = create_reviews(exposure, include_revision_review=True)
    existing["updated_time"] = now_iso()
    existing["last_analysis_time"] = now_iso()
    existing["analysis_revision"] = int(existing.get("analysis_revision", 1)) + 1
    existing["needs_reanalysis"] = False

    _set_target_after_analysis(existing, exposure)

    add_event(
        existing,
        "CASE_REANALYSED_UPDATED",
        "SYSTEM",
        {
            "previous_status": previous_exposure.get("status"),
            "new_status": exposure.get("status"),
            "previous_reason_code": previous_exposure.get("reason_code"),
            "new_reason_code": exposure.get("reason_code"),
            "analysis_revision": existing["analysis_revision"],
            "reviews_created": len(existing.get("reviews", [])),
        },
    )

    ctx.save_case(existing)
    return {
        "ok": True,
        "case_id": existing["case_id"],
        "case": existing,
        "case_action": "UPDATED",
        "case_changed": True,
    }


def request_human_approval(ctx, case_id):
    case = ctx.cases.get(case_id)
    if not case:
        return {"ok": False, "error": "CASE_NOT_FOUND"}

    waiting = [
        t for t in case["tasks"]
        if t.get("status") == "WAITING_FOR_APPROVAL"
    ]

    if waiting and case.get("state") == "CONFIRMED":
        transition_case(
            case,
            "RESPONDING",
            "SYSTEM",
            {"reason": "Response tasks opened at human approval boundary"},
        )
        ctx.save_case(case)

    return {
        "ok": True,
        "case_id": case_id,
        "status": "AWAITING_HUMAN_APPROVAL" if waiting else "NO_APPROVAL_REQUIRED",
        "waiting_tasks": [
            {
                "task_id": t["task_id"],
                "title": t["title"],
                "assigned_to": t.get("assigned_to"),
                "approval_roles": t.get("approval_roles") or [],
                "approval_mode": t.get("approval_mode"),
            }
            for t in waiting
        ],
    }
