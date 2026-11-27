from __future__ import annotations

import uuid

from matching.matcher import resolve_exposure
from .audit import add_event, now_iso
from .roles import (
    WAREHOUSE_MANAGER,
    STORE_SITE_MANAGER,
    RECALL_INCIDENT_MANAGER,
)
from .states import transition_case


QUICK_CLOSE_PROFILE = "QUICK_CLOSE_TWO_APPROVALS"


DEMO_SITE_APPROVERS = {
    "DUB": {
        "username": "site.manager",
        "display_name": "Dublin Site Manager",
        "role": STORE_SITE_MANAGER,
    },
    "GAL": {
        "username": "warehouse.manager",
        "display_name": "Galway Warehouse Manager",
        "role": WAREHOUSE_MANAGER,
    },
    "COR": {
        "username": "cork.manager",
        "display_name": "Cork Site Manager",
        "role": STORE_SITE_MANAGER,
    },
}


def _containment_owner_for_exposure(ctx, exposure):
    """Resolve the first demo approval from the actual affected stock location.

    The Live Demo deliberately keeps one containment approval. For the prepared
    scenarios the affected stock is at a single site, so that approval is routed
    to the manager responsible for that site. If a future fixture spans multiple
    sites, the generic Warehouse Manager remains the safe fallback until the
    demo is expanded to one approval per location.
    """
    sku = exposure.get("sku")
    matched_batches = {str(x) for x in (exposure.get("matched_batches") or [])}
    records = []
    for row in ctx.data.get("inventory", []):
        if row.get("sku") != sku:
            continue
        if matched_batches and str(row.get("batch_code")) not in matched_batches:
            continue
        try:
            quantity = float(row.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0
        if quantity <= 0:
            continue
        records.append(row)

    site_codes = []
    for row in records:
        code = row.get("site_code") or row.get("site")
        if code and code not in site_codes:
            site_codes.append(code)

    if len(site_codes) == 1 and site_codes[0] in DEMO_SITE_APPROVERS:
        owner = dict(DEMO_SITE_APPROVERS[site_codes[0]])
        owner["site_code"] = site_codes[0]
        owner["site_name"] = records[0].get("site") or site_codes[0]
        return owner

    return {
        "username": "warehouse.manager",
        "display_name": "Galway Warehouse Manager",
        "role": WAREHOUSE_MANAGER,
        "site_code": site_codes[0] if len(site_codes) == 1 else None,
        "site_name": records[0].get("site") if len(records) == 1 else None,
    }


def _approval_only_task(
    title,
    role,
    evidence,
    description,
    why_generated,
    *,
    assigned_username=None,
    assigned_display_name=None,
    affected_site_code=None,
    affected_site_name=None,
):
    return {
        "task_id": "T-" + uuid.uuid4().hex[:6].upper(),
        "title": title,
        "description": description,
        "why_generated": why_generated,
        "suggested_steps": [
            "Review the structured evidence attached to this decision.",
            "Record an approval comment if the evidence is sufficient.",
            "Approve only if the stated control has been verified.",
        ],
        "template_why_generated": why_generated,
        "template_suggested_steps": [
            "Review the structured evidence attached to this decision.",
            "Record an approval comment if the evidence is sufficient.",
            "Approve only if the stated control has been verified.",
        ],
        "narrative_source": "deterministic-template",
        "narrative_model": None,
        "narrative_generated_time": None,
        "priority": "HIGH",
        "assigned_to": role,
        "assigned_username": assigned_username,
        "assigned_display_name": assigned_display_name,
        "affected_site_code": affected_site_code,
        "affected_site_name": affected_site_name,
        "approval_usernames": [assigned_username] if assigned_username else [],
        "status": "WAITING_FOR_APPROVAL",
        "requires_approval": True,
        "approval_roles": [role],
        "approval_mode": "ANY_ONE",
        "approvals": [],
        "approval": None,
        "approval_only": True,
        "created_time": now_iso(),
        "completion_time": None,
        "evidence": evidence,
        "completion_evidence": [
            "Authenticated human approval",
            "Decision comment",
            "Timestamped audit event",
        ],
        "completion_criteria": (
            "The authorised role records the approval decision. Because this is "
            "an approval-only governance task, the task completes with that decision."
        ),
        "action_boundary": (
            "Quick-close demo governance decision only. It does not execute a "
            "physical or external action automatically."
        ),
    }


def create_quick_close_demo_case(ctx):
    """
    Create a deliberately streamlined closure demonstration.

    The regulatory basis is the genuine bundled FSAI 2026.38 showcase and the
    internal company evidence is the existing synthetic SKU398 scenario.

    To keep the live demonstration short, operational containment/traceability
    evidence is marked as pre-completed demo evidence and exactly two approval
    decisions remain:
      1) Warehouse Manager
      2) Recall / Incident Manager

    After the second approval the case becomes RESOLVED automatically. The
    Recall / Incident Manager can then close it and download the final audit.
    """
    source_recall = next(
        (
            recall
            for recall in ctx.data.get("real_recalls", [])
            if recall.get("official_recall_id") == "2026.38"
        ),
        None,
    )
    product = next(
        (
            item
            for item in ctx.data.get("products", [])
            if item.get("sku") == "SKU398"
        ),
        None,
    )

    if source_recall is None or product is None:
        raise ValueError(
            "The quick-close demo requires bundled FSAI 2026.38 and synthetic SKU398."
        )

    resolved = resolve_exposure(
        source_recall,
        product,
        ctx.data.get("batches", []),
        ctx.data.get("inventory", []),
        ctx.data.get("dispatches", []),
    )

    if resolved.get("status") != "CONFIRMED":
        raise ValueError(
            "The quick-close demo source scenario is no longer CONFIRMED."
        )

    suffix = uuid.uuid4().hex[:6].upper()
    demo_recall_id = f"QUICK_CLOSE_FSAI_2026_38_{suffix}"
    case_id = f"CASE-QUICK-{suffix}"

    exposure = dict(resolved)
    exposure["source_recall_id"] = source_recall.get("recall_id")
    exposure["official_recall_id"] = source_recall.get("official_recall_id")
    exposure["recall_id"] = demo_recall_id
    exposure["demo_only"] = True

    evidence = {
        "official_fsai_alert": source_recall.get("official_recall_id"),
        "source_recall_id": source_recall.get("recall_id"),
        "product": source_recall.get("product_name"),
        "sku": resolved.get("sku"),
        "matched_batches": resolved.get("matched_batches") or [],
        "stock": resolved.get("stock", 0),
        "dispatched": resolved.get("dispatched", 0),
        "reason_code": resolved.get("reason_code"),
    }

    case = {
        "case_id": case_id,
        "recall_id": demo_recall_id,
        "state": "DETECTED",
        "created_time": now_iso(),
        "updated_time": now_iso(),
        "last_analysis_time": now_iso(),
        "analysis_revision": 1,
        "exposure": exposure,
        "tasks": [],
        "reviews": [],
        "audit_timeline": [],
        "task_history": [],
        "review_history": [],
        "recall_version": None,
        "needs_reanalysis": False,
        "demo_only": True,
        "demo_profile": QUICK_CLOSE_PROFILE,
        "source_recall": {
            "recall_id": source_recall.get("recall_id"),
            "official_recall_id": source_recall.get("official_recall_id"),
            "authority": source_recall.get("authority"),
            "product_name": source_recall.get("product_name"),
            "pack_sizes": source_recall.get("pack_sizes") or [],
            "batch_codes": source_recall.get("batch_codes") or [],
            "use_by": source_recall.get("use_by") or [],
            "best_before": source_recall.get("best_before") or [],
            "hazard": source_recall.get("hazard"),
            "source_url": source_recall.get("source_url"),
            "published_date": source_recall.get("published_date"),
        },
        "demo_precompleted_evidence": [
            {
                "activity": "Affected stock containment evidence recorded",
                "status": "PRECOMPLETED_FOR_DEMO",
                "note": (
                    "The quick-close fixture assumes the physical containment "
                    "work has already been recorded so the live demo can focus "
                    "on governed approvals and final closure."
                ),
            },
            {
                "activity": "Downstream trace evidence recorded",
                "status": "PRECOMPLETED_FOR_DEMO",
                "note": (
                    "Traceability evidence is preloaded from the synthetic "
                    "company sandbox for the closure demonstration."
                ),
            },
        ],
    }

    add_event(
        case,
        "CASE_CREATED",
        "SYSTEM",
        {
            "state": "DETECTED",
            "exposure_status": "CONFIRMED",
            "demo_profile": QUICK_CLOSE_PROFILE,
        },
    )
    transition_case(case, "ANALYSING", "SYSTEM")
    transition_case(case, "CONFIRMED", "SYSTEM")
    transition_case(
        case,
        "RESPONDING",
        "SYSTEM",
        {
            "reason": (
                "Quick-close demo starts with operational evidence pre-completed "
                "and exactly two governance approvals outstanding."
            )
        },
    )

    containment_owner = _containment_owner_for_exposure(ctx, exposure)

    first_task = _approval_only_task(
        "Confirm and complete affected stock containment",
        containment_owner["role"],
        evidence,
        (
            "Review the pre-recorded containment evidence for the confirmed "
            "affected lot and authorise it for the case record."
        ),
        (
            "Created so the quick demo shows an authenticated site-level "
            "approval by the manager responsible for the affected stock location "
            "before the case can progress."
        ),
        assigned_username=containment_owner["username"],
        assigned_display_name=containment_owner["display_name"],
        affected_site_code=containment_owner.get("site_code"),
        affected_site_name=containment_owner.get("site_name"),
    )
    second_task = _approval_only_task(
        "Review evidence and close the recall case",
        RECALL_INCIDENT_MANAGER,
        evidence,
        (
            "Review the confirmed exposure, traceability and containment "
            "evidence and authorise the completed response package."
        ),
        (
            "Created as the second and final quick-demo approval before the "
            "case can move to RESOLVED."
        ),
    )
    first_task["demo_approval_ordinal"] = 1
    second_task["demo_approval_ordinal"] = 2
    second_task["depends_on_task_ids"] = [first_task["task_id"]]
    case["tasks"] = [first_task, second_task]

    add_event(
        case,
        "QUICK_CLOSE_DEMO_EVIDENCE_PRELOADED",
        "SYSTEM",
        {
            "count": len(case["demo_precompleted_evidence"]),
            "demo_only": True,
        },
    )
    add_event(
        case,
        "TASKS_CREATED",
        "SYSTEM",
        {
            "count": 2,
            "approval_decisions_required": 2,
            "roles": [
                containment_owner["role"],
                RECALL_INCIDENT_MANAGER,
            ],
            "containment_owner": containment_owner,
            "demo_only": True,
        },
    )
    add_event(
        case,
        "REVIEWS_CREATED",
        "SYSTEM",
        {
            "count": 0,
            "reason": "Quick-close demo is intentionally streamlined.",
            "demo_only": True,
        },
    )

    ctx.cases[case_id] = case
    ctx.save_case(case)
    return case


def streamline_existing_confirmed_case_for_demo(ctx, case_id, source_recall=None):
    """
    Replace the normal CONFIRMED response workload with a deliberately
    streamlined two-approval demo profile.

    The investigation and deterministic exposure result are untouched. Only
    the downstream human-response workload is shortened for pitch/demo use.
    The original full task/review definitions are preserved in the case as a
    reference and the audit explicitly records that demo streamlining occurred.
    """
    case = ctx.cases.get(case_id)
    if not case:
        raise ValueError(f"Case not found: {case_id}")

    exposure = case.get("exposure") or {}
    if exposure.get("status") != "CONFIRMED":
        return case

    if case.get("demo_profile") == QUICK_CLOSE_PROFILE:
        return case

    original_tasks = case.get("tasks") or []
    original_reviews = case.get("reviews") or []

    case["demo_only"] = True
    case["demo_profile"] = QUICK_CLOSE_PROFILE
    case["demo_full_workflow_reference"] = {
        "task_count": len(original_tasks),
        "review_count": len(original_reviews),
        "tasks": [
            {
                "title": task.get("title"),
                "assigned_to": task.get("assigned_to"),
                "requires_approval": bool(task.get("requires_approval")),
                "approval_roles": task.get("approval_roles") or [],
            }
            for task in original_tasks
        ],
        "reviews": [
            {
                "title": review.get("title"),
                "assigned_role": review.get("assigned_role"),
            }
            for review in original_reviews
        ],
        "note": (
            "This is the normal full response workload that the prototype "
            "would use outside Demo mode. Demo mode shortens only the live "
            "human-action sequence."
        ),
    }

    if source_recall:
        case["source_recall"] = {
            "recall_id": source_recall.get("recall_id"),
            "official_recall_id": source_recall.get("official_recall_id"),
            "authority": source_recall.get("authority"),
            "product_name": source_recall.get("product_name"),
            "pack_sizes": source_recall.get("pack_sizes") or [],
            "batch_codes": source_recall.get("batch_codes") or [],
            "use_by": source_recall.get("use_by") or [],
            "best_before": source_recall.get("best_before") or [],
            "hazard": source_recall.get("hazard"),
            "source_url": source_recall.get("source_url"),
            "published_date": source_recall.get("published_date"),
        }

    evidence = {
        "official_fsai_alert": (source_recall or {}).get("official_recall_id")
            or exposure.get("official_recall_id"),
        "source_recall_id": (source_recall or {}).get("recall_id")
            or exposure.get("source_recall_id"),
        "product": (source_recall or {}).get("product_name")
            or exposure.get("product_name"),
        "sku": exposure.get("sku"),
        "matched_batches": exposure.get("matched_batches") or [],
        "stock": exposure.get("stock", 0),
        "dispatched": exposure.get("dispatched", 0),
        "reason_code": exposure.get("reason_code"),
    }

    containment_owner = _containment_owner_for_exposure(ctx, exposure)
    evidence["affected_site_code"] = containment_owner.get("site_code")
    evidence["affected_site_name"] = containment_owner.get("site_name")
    evidence["containment_owner"] = containment_owner.get("display_name")

    first = _approval_only_task(
        "Confirm and complete affected stock containment",
        containment_owner["role"],
        evidence,
        (
            "Review the traced warehouse evidence, confirm the remaining affected "
            "stock is contained, and record completion of the warehouse task."
        ),
        (
            "Created after the agent confirms exposure so the manager responsible "
            "for the affected stock location, rather than the LLM, owns the "
            "physical containment decision."
        ),
        assigned_username=containment_owner["username"],
        assigned_display_name=containment_owner["display_name"],
        affected_site_code=containment_owner.get("site_code"),
        affected_site_name=containment_owner.get("site_name"),
    )
    second = _approval_only_task(
        "Review evidence and close the recall case",
        RECALL_INCIDENT_MANAGER,
        evidence,
        (
            "Review the confirmed exposure, traceability evidence and local site "
            "manager decision, then authorise final closure of the demo case."
        ),
        (
            "Created only after the local containment manager task is completed. This is "
            "the second and final authorised decision in the Live Demo."
        ),
    )
    first["demo_approval_ordinal"] = 1
    second["demo_approval_ordinal"] = 2
    second["depends_on_task_ids"] = [first["task_id"]]

    case["tasks"] = [first, second]
    case["reviews"] = []
    case["demo_precompleted_evidence"] = [
        {
            "activity": "Full operational response workload represented as pre-completed demo evidence",
            "status": "PRECOMPLETED_FOR_DEMO",
            "note": (
                "The normal operational tasks remain documented in "
                "demo_full_workflow_reference. Demo mode keeps only two "
                "human governance approvals active so closure can be shown "
                "quickly during the pitch."
            ),
        }
    ]

    # A full agent investigation may leave the case in CONFIRMED or
    # RESPONDING. The streamlined response starts at RESPONDING.
    if case.get("state") == "CONFIRMED":
        transition_case(
            case,
            "RESPONDING",
            "SYSTEM",
            {"reason": "Demo-mode two-approval response profile activated"},
        )

    add_event(
        case,
        "DEMO_RESPONSE_WORKFLOW_STREAMLINED",
        "SYSTEM",
        {
            "demo_profile": QUICK_CLOSE_PROFILE,
            "original_task_count": len(original_tasks),
            "original_review_count": len(original_reviews),
            "active_task_count": 2,
            "active_review_count": 0,
            "containment_owner": containment_owner,
            "approval_sequence": [
                containment_owner["role"],
                RECALL_INCIDENT_MANAGER,
            ],
            "investigation_and_exposure_unchanged": True,
        },
    )

    ctx.save_case(case)
    return case



def request_demo_corrective_action(case, final_task_id, actor, actor_role, reason):
    """Request further site action when final evidence is not sufficient.

    The Incident Manager does not close or reject the recall. Instead, a new
    corrective-action task is routed back to the manager currently responsible
    for the affected site. The final closure approval remains blocked until the
    site manager submits revised evidence. All prior submissions remain in the
    case and audit trail.
    """
    if actor_role != RECALL_INCIDENT_MANAGER:
        raise PermissionError("Only the Recall / Incident Manager can request further action.")
    if not str(reason or "").strip():
        raise ValueError("A reason for requesting further action is required.")

    final_task = next((item for item in case.get("tasks", []) if item.get("task_id") == final_task_id), None)
    if not final_task:
        raise ValueError("Final review task not found.")
    if final_task.get("title") != "Review evidence and close the recall case":
        raise ValueError("Corrective action can only be requested from the final demo review.")
    if final_task.get("status") != "WAITING_FOR_APPROVAL":
        raise ValueError("The final review is not currently awaiting an Incident Manager decision.")

    first_task = next(
        (item for item in case.get("tasks", []) if item.get("title") == "Confirm and complete affected stock containment"),
        None,
    )
    if not first_task or first_task.get("status") != "COMPLETED":
        raise ValueError("The site containment task must be completed before further evidence can be requested.")

    round_no = int(final_task.get("corrective_rounds") or 0) + 1
    corrective_id = "T-" + uuid.uuid4().hex[:6].upper()
    corrective = {
        "task_id": corrective_id,
        "title": f"Provide corrective evidence for final review · round {round_no}",
        "description": (
            "The Recall / Incident Manager did not accept the evidence package for case closure. "
            "Review the stated gap, take the required corrective action, and submit revised evidence."
        ),
        "why_generated": str(reason).strip(),
        "priority": "HIGH",
        "assigned_to": first_task.get("assigned_to"),
        "assigned_username": first_task.get("assigned_username"),
        "assigned_display_name": first_task.get("assigned_display_name"),
        "affected_site_code": first_task.get("affected_site_code"),
        "affected_site_name": first_task.get("affected_site_name"),
        "status": "PENDING",
        "requires_approval": False,
        "approval_roles": [],
        "approval_usernames": [],
        "approval_mode": "ANY_ONE",
        "approvals": [],
        "approval": None,
        "approval_only": False,
        "demo_corrective_action": True,
        "corrective_round": round_no,
        "corrective_for_task_id": final_task_id,
        "requested_by": actor,
        "requested_by_role": actor_role,
        "request_reason": str(reason).strip(),
        "created_time": now_iso(),
        "completion_time": None,
        "corrective_submission": None,
        "completion_evidence": [
            "Revised/corrective evidence note from the responsible site manager",
            "Authenticated submitter",
            "Timestamped audit event",
        ],
        "completion_criteria": (
            "The responsible site manager records the corrective action taken and submits revised evidence."
        ),
        "action_boundary": (
            "Human corrective-action task. SentiOH routes and records the request but does not execute the physical action."
        ),
    }
    case.setdefault("tasks", []).append(corrective)

    final_task.setdefault("final_review_history", []).append({
        "time": now_iso(),
        "round": round_no,
        "decision": "FURTHER_ACTION_REQUESTED",
        "decided_by": actor,
        "decided_by_role": actor_role,
        "reason": str(reason).strip(),
        "corrective_task_id": corrective_id,
    })
    final_task["corrective_rounds"] = round_no
    final_task["status"] = "WAITING_FOR_CORRECTIVE_ACTION"
    final_task["approval"] = None
    deps = list(final_task.get("depends_on_task_ids") or [])
    if corrective_id not in deps:
        deps.append(corrective_id)
    final_task["depends_on_task_ids"] = deps

    add_event(case, "FINAL_EVIDENCE_FURTHER_ACTION_REQUESTED", actor, {
        "final_task_id": final_task_id,
        "corrective_task_id": corrective_id,
        "corrective_round": round_no,
        "reason": str(reason).strip(),
        "assigned_username": corrective.get("assigned_username"),
        "assigned_role": corrective.get("assigned_to"),
        "affected_site_code": corrective.get("affected_site_code"),
        "case_remains_open": True,
    })
    return corrective


def submit_demo_corrective_evidence(case, corrective_task_id, actor, actor_role, actor_username, evidence_note):
    """Complete a corrective-action round and return final review to Incident Manager."""
    if not str(evidence_note or "").strip():
        raise ValueError("A corrective evidence note is required.")
    task = next((item for item in case.get("tasks", []) if item.get("task_id") == corrective_task_id), None)
    if not task or not task.get("demo_corrective_action"):
        raise ValueError("Corrective-action task not found.")
    if task.get("status") != "PENDING":
        raise ValueError("This corrective-action task is not awaiting evidence.")
    if actor_role != task.get("assigned_to"):
        raise PermissionError("Only the manager assigned to the affected site can submit this corrective evidence.")
    if task.get("assigned_username") and actor_username != task.get("assigned_username"):
        raise PermissionError("This corrective action is assigned to a different site-manager account.")

    submitted = {
        "submitted_by": actor,
        "submitted_by_role": actor_role,
        "submitted_by_username": actor_username,
        "evidence_note": str(evidence_note).strip(),
        "time": now_iso(),
    }
    task["corrective_submission"] = submitted
    task["status"] = "COMPLETED"
    task["completion_time"] = submitted["time"]

    final_id = task.get("corrective_for_task_id")
    final_task = next((item for item in case.get("tasks", []) if item.get("task_id") == final_id), None)
    if not final_task:
        raise ValueError("Linked final review task not found.")
    final_task["status"] = "WAITING_FOR_APPROVAL"
    final_task.setdefault("final_review_history", []).append({
        "time": submitted["time"],
        "round": task.get("corrective_round"),
        "decision": "CORRECTIVE_EVIDENCE_SUBMITTED",
        "submitted_by": actor,
        "submitted_by_role": actor_role,
        "corrective_task_id": corrective_task_id,
        "evidence_note": str(evidence_note).strip(),
    })

    add_event(case, "CORRECTIVE_EVIDENCE_SUBMITTED", actor, {
        "corrective_task_id": corrective_task_id,
        "final_task_id": final_id,
        "corrective_round": task.get("corrective_round"),
        "submitted_by_role": actor_role,
        "submitted_by_username": actor_username,
        "final_review_reopened": True,
    })
    return case

def reassign_rejected_demo_containment(case, task_id, actor, actor_role, target_site_code=None):
    """Re-issue a rejected Live Demo containment approval under Incident Manager control.

    The rejection remains in ``approvals`` and the audit trail. The same task id is
    deliberately retained so the final approval dependency remains valid, while
    the active assignee can be changed to the manager responsible for the selected
    site. This is a governance action only and does not alter exposure truth.
    """
    if actor_role != RECALL_INCIDENT_MANAGER:
        raise PermissionError("Only the Recall / Incident Manager can re-assign a rejected demo containment task.")

    task = next((item for item in case.get("tasks", []) if item.get("task_id") == task_id), None)
    if not task:
        raise ValueError("Containment task not found.")
    if task.get("status") != "REJECTED":
        raise ValueError("Only a rejected containment task can be re-assigned.")

    affected_site_code = task.get("affected_site_code")
    site_code = target_site_code or affected_site_code
    if affected_site_code and site_code != affected_site_code:
        raise PermissionError(
            "A rejected containment task can only be re-issued to the manager "
            "responsible for the affected stock location."
        )
    owner = DEMO_SITE_APPROVERS.get(site_code)
    if not owner:
        raise ValueError(f"No authorised demo site manager is configured for site '{site_code}'.")

    previous = {
        "assigned_username": task.get("assigned_username"),
        "assigned_display_name": task.get("assigned_display_name"),
        "assigned_to": task.get("assigned_to"),
        "affected_site_code": task.get("affected_site_code"),
        "affected_site_name": task.get("affected_site_name"),
        "rejection": task.get("approval"),
    }
    task.setdefault("reassignment_history", []).append({
        "time": now_iso(),
        "reassigned_by": actor,
        "reassigned_by_role": actor_role,
        "previous": previous,
        "new_site_code": site_code,
        "new_assigned_username": owner["username"],
        "new_assigned_display_name": owner["display_name"],
    })
    task["assigned_to"] = owner["role"]
    task["assigned_username"] = owner["username"]
    task["assigned_display_name"] = owner["display_name"]
    task["approval_roles"] = [owner["role"]]
    task["approval_usernames"] = [owner["username"]]
    task["affected_site_code"] = site_code
    # Preserve the original human-readable site when reissuing to the same site.
    if site_code != previous.get("affected_site_code"):
        task["affected_site_name"] = site_code
    task["status"] = "WAITING_FOR_APPROVAL"
    task["approval"] = None
    task["completion_time"] = None
    task["reissued_after_rejection"] = True
    task["reissue_count"] = int(task.get("reissue_count") or 0) + 1

    # Complete the rejection escalation review as part of the explicit re-assignment.
    for review in case.get("reviews", []):
        if (
            review.get("review_type") == "REJECTED_ACTION_REVIEW"
            and review.get("evidence", {}).get("task_id") == task_id
            and review.get("status") == "WAITING_FOR_REVIEW"
        ):
            review["status"] = "REVIEWED"
            review["reviewed_time"] = now_iso()
            review["reviewed_by"] = actor
            review["reviewed_by_role"] = actor_role
            review["comment"] = (
                f"Escalation reviewed and containment task re-assigned to {owner['display_name']}."
            )

    add_event(case, "REJECTED_TASK_REASSIGNED", actor, {
        "task_id": task_id,
        "actor_role": actor_role,
        "target_site_code": site_code,
        "assigned_username": owner["username"],
        "assigned_display_name": owner["display_name"],
        "reissue_count": task["reissue_count"],
        "exposure_status_unchanged": case.get("exposure", {}).get("status"),
    })
    return case
