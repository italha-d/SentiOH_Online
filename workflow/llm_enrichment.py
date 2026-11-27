from __future__ import annotations

from .audit import add_event, now_iso


def apply_task_narratives(case, narratives, model):
    """
    Apply LLM task rationale/suggested steps without allowing the model
    to change task identity, approval authority, completion criteria, priority,
    assignment, evidence requirements, task state or agent boundary.
    """
    if not case or not isinstance(narratives, list):
        return 0

    by_id = {
        item.get("task_id"): item
        for item in narratives
        if isinstance(item, dict) and item.get("task_id")
    }

    updated = 0
    for task in case.get("tasks", []):
        generated = by_id.get(task.get("task_id"))
        if not generated:
            continue

        rationale = str(generated.get("why_generated") or "").strip()
        steps = [
            str(step).strip()
            for step in (generated.get("suggested_steps") or [])
            if str(step).strip()
        ]

        # Do not replace a safe deterministic fallback with empty/low-value text.
        if not rationale or not steps:
            continue

        task["why_generated"] = rationale
        task["suggested_steps"] = steps[:6]
        task["narrative_source"] = "llm"
        task["narrative_model"] = model
        task["narrative_generated_time"] = now_iso()
        updated += 1

    if updated:
        add_event(
            case,
            "LLM_TASK_NARRATIVES_GENERATED",
            "LLM",
            {
                "model": model,
                "tasks_enriched": updated,
                "governance_fields_changed": False,
            },
        )
    return updated


def store_evidence_gap_analysis(case, analysis, model):
    if not case or not isinstance(analysis, dict):
        return False

    case["evidence_gap_analysis"] = dict(analysis)
    case["evidence_gap_analysis"]["model"] = model
    case["evidence_gap_analysis"]["generated_time"] = now_iso()

    add_event(
        case,
        "LLM_EVIDENCE_GAP_ANALYSIS_GENERATED",
        "LLM",
        {
            "model": model,
            "exposure_status": case.get("exposure", {}).get("status"),
        },
    )
    return True
