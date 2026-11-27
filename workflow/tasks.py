from __future__ import annotations
import uuid
from .audit import now_iso
from .roles import (
    WAREHOUSE_OPERATOR,
    WAREHOUSE_MANAGER,
    STORE_SITE_MANAGER,
    LOGISTICS_OPERATOR,
    LOGISTICS_MANAGER,
    QUALITY_FOOD_SAFETY_MANAGER,
    PROCUREMENT_TEAM,
    PROCUREMENT_MANAGER,
    COMMUNICATIONS_TEAM,
    RECALL_INCIDENT_MANAGER,
)


def _task(
    title,
    priority,
    role,
    requires_approval=False,
    approval_roles=None,
    approval_mode="ANY_ONE",
    evidence=None,
    description="",
    why_generated="",
    suggested_steps=None,
    completion_evidence=None,
    completion_criteria="",
    action_boundary="",
):
    approval_roles = list(approval_roles or [])
    if requires_approval and not approval_roles:
        raise ValueError(f"Protected task '{title}' must define approval roles.")
    if approval_mode not in {"ANY_ONE", "ALL_ROLES"}:
        raise ValueError("approval_mode must be ANY_ONE or ALL_ROLES")

    return {
        "task_id": "T-" + uuid.uuid4().hex[:6].upper(),
        "title": title,
        "description": description,
        # These two fields are what the dashboard displays. They begin as
        # deterministic fallbacks and may later be replaced by LLM text.
        "why_generated": why_generated,
        "suggested_steps": list(suggested_steps or []),

        # Preserve the controlled template permanently for audit/fallback.
        "template_why_generated": why_generated,
        "template_suggested_steps": list(suggested_steps or []),
        "narrative_source": "deterministic-template",
        "narrative_model": None,
        "narrative_generated_time": None,

        "priority": priority,
        "assigned_to": role,
        "status": "WAITING_FOR_APPROVAL" if requires_approval else "PENDING",
        "requires_approval": requires_approval,
        "approval_roles": approval_roles,
        "approval_mode": approval_mode if requires_approval else None,
        "approvals": [],
        "approval": None,  # final decision summary kept for compatibility
        "created_time": now_iso(),
        "completion_time": None,
        "evidence": evidence or {},
        "completion_evidence": completion_evidence or [],
        "completion_criteria": completion_criteria,
        "action_boundary": action_boundary,
    }


def create_tasks(exposure):
    evidence = {
        "recall_id": exposure.get("recall_id"),
        "sku": exposure.get("sku"),
        "batch": exposure.get("batch"),
        "reason_code": exposure.get("reason_code"),
        "stock": exposure.get("stock", 0),
        "dispatched": exposure.get("dispatched", 0),
    }

    if exposure.get("status") == "CONFIRMED":
        return [
            _task(
                "Hold remaining stock",
                "HIGH",
                WAREHOUSE_OPERATOR,
                True,
                [WAREHOUSE_MANAGER, STORE_SITE_MANAGER],
                "ANY_ONE",
                evidence,
                "Contain the remaining affected lot so it cannot be unintentionally released while the response is active.",
                "Generated because the deterministic resolver confirmed exposure and structured inventory shows affected stock remains in the organisation.",
                [
                    "Review the affected SKU, lot and site evidence.",
                    "Confirm the physical stock location.",
                    "Request approval from the responsible Warehouse Manager or Store / Site Manager.",
                    "After approval, execute and record the containment action.",
                ],
                ["Stock-hold reference", "Affected quantity checked", "Authorised human decision"],
                "The affected stock is verified, an authorised containment decision is recorded and supporting evidence is attached.",
                "Protected containment action. SentiOH can recommend and prepare it, but a Warehouse Manager or Store / Site Manager must authorise it.",
            ),
            _task(
                "Verify physical quantity",
                "HIGH",
                WAREHOUSE_OPERATOR,
                False,
                evidence=evidence,
                description="Check whether the physical quantity of the affected lot agrees with the structured inventory record.",
                why_generated="Generated because remaining stock is present and the response needs a verified operational quantity.",
                suggested_steps=[
                    "Locate the identified lot at the listed site.",
                    "Count or verify the physical quantity.",
                    "Compare the physical quantity with the system quantity.",
                    "Record any discrepancy.",
                ],
                completion_evidence=["Verified physical quantity", "Site checked", "Discrepancy note if applicable"],
                completion_criteria="A physical quantity has been recorded and compared with the system inventory quantity.",
                action_boundary="Evidence-gathering task. No autonomous external action is performed.",
            ),
            _task(
                "Trace downstream distribution",
                "HIGH",
                LOGISTICS_OPERATOR,
                False,
                evidence=evidence,
                description="Identify all recorded downstream dispatches associated with the confirmed affected lot.",
                why_generated="Generated because units from the affected lot may already have left the organisation.",
                suggested_steps=[
                    "Review dispatch records for the affected SKU and lot.",
                    "Confirm recipients and quantities.",
                    "Check for incomplete dispatch records.",
                    "Attach the trace summary to the case.",
                ],
                completion_evidence=["Customer/dispatch list", "Dispatched quantity total", "Traceability summary"],
                completion_criteria="All available downstream dispatch records for the affected lot are reviewed and documented.",
                action_boundary="Traceability task only. SentiOH does not contact customers.",
            ),
            _task(
                "Pause further dispatch of affected lot",
                "HIGH",
                LOGISTICS_OPERATOR,
                True,
                [LOGISTICS_MANAGER, WAREHOUSE_MANAGER],
                "ANY_ONE",
                evidence,
                "Prepare a temporary pause on further outbound movement of the confirmed affected lot.",
                "Generated because confirmed affected stock remains and further distribution would increase downstream exposure.",
                [
                    "Confirm the affected SKU and lot.",
                    "Check whether any open shipment contains the lot.",
                    "Request authorisation from the Logistics Manager or Warehouse Manager.",
                    "Record the authorised shipment restriction.",
                ],
                ["Shipment-hold reference", "Open-shipment check", "Authorised human decision"],
                "Outbound movement is either formally paused by an authorised manager or a rejection reason is recorded.",
                "Protected logistics action. SentiOH cannot stop shipments autonomously.",
            ),
            _task(
                "Prepare supplier communication draft",
                "MEDIUM",
                PROCUREMENT_TEAM,
                True,
                [PROCUREMENT_MANAGER],
                "ANY_ONE",
                evidence,
                "Prepare supplier follow-up based on purchase history and recall evidence.",
                "Generated because supplier and purchase-order evidence can clarify scope, supplied quantities and additional affected lots.",
                [
                    "Review the relevant supplier and purchase-order records.",
                    "Prepare a concise information request or notification draft.",
                    "Submit it to the Procurement Manager for approval before any external communication.",
                ],
                ["Supplier record reviewed", "Draft communication", "Procurement Manager decision"],
                "The supplier draft is prepared and an authorised decision is recorded. No message is sent autonomously.",
                "Protected supplier communication. SentiOH may draft but cannot send; the Procurement Manager is the approval authority.",
            ),
            _task(
                "Prepare customer communication draft",
                "MEDIUM",
                COMMUNICATIONS_TEAM,
                True,
                [QUALITY_FOOD_SAFETY_MANAGER, RECALL_INCIDENT_MANAGER],
                "ALL_ROLES",
                evidence,
                "Prepare a draft communication for potentially affected downstream recipients without sending it.",
                "Generated because the trace indicates affected units were dispatched downstream.",
                [
                    "Use only verified recall and dispatch evidence.",
                    "State the affected product and lot clearly.",
                    "Avoid unsupported claims or invented regulatory instructions.",
                    "Obtain both Quality & Food Safety Manager and Recall / Incident Manager approval.",
                ],
                ["Draft communication", "Evidence references", "Quality approval", "Incident Manager approval"],
                "A grounded draft is approved by both required authorities and remains unsent by the agent.",
                "High-consequence external communication. SentiOH cannot send it. Dual human approval is required.",
            ),
            _task(
                "Record completion evidence",
                "MEDIUM",
                QUALITY_FOOD_SAFETY_MANAGER,
                False,
                evidence=evidence,
                description="Consolidate operational evidence generated during containment, verification and traceability work.",
                why_generated="Generated to preserve an auditable case history and make later review reproducible.",
                suggested_steps=[
                    "Check that each completed task has evidence attached.",
                    "Record missing evidence or unresolved discrepancies.",
                    "Confirm the audit timeline reflects material actions.",
                ],
                completion_evidence=["Task evidence references", "Case audit events", "Outstanding issue note if applicable"],
                completion_criteria="Material response actions and supporting evidence are represented in the case record.",
                action_boundary="Documentation task. It cannot replace human verification of operational actions.",
            ),
        ]

    if exposure.get("status") == "POSSIBLE":
        return [
            _task(
                "Verify physical batch or lot",
                "HIGH",
                WAREHOUSE_OPERATOR,
                False,
                evidence=evidence,
                description="Obtain the missing lot information needed to determine whether potentially relevant stock is actually in recall scope.",
                why_generated="Generated because product identity appears relevant but decisive lot evidence is missing or incomplete.",
                suggested_steps=[
                    "Locate the potentially relevant product.",
                    "Read the physical batch or lot marking.",
                    "Record the value exactly as shown.",
                    "Submit the evidence for re-analysis.",
                ],
                completion_evidence=["Observed lot/batch value", "Site and product checked", "Evidence capture or operator note"],
                completion_criteria="A reliable lot or batch value is available for deterministic re-analysis.",
                action_boundary="Evidence-gathering task. SentiOH does not infer a missing lot.",
            ),
            _task(
                "Check use-by/best-before evidence",
                "HIGH",
                QUALITY_FOOD_SAFETY_MANAGER,
                False,
                evidence=evidence,
                description="Verify date information that may narrow or exclude the potential exposure.",
                why_generated="Generated because date evidence may be relevant to the recall scope and cannot be guessed when missing.",
                suggested_steps=[
                    "Review the product record and physical date marking.",
                    "Record the date exactly.",
                    "Compare only through the deterministic resolver.",
                ],
                completion_evidence=["Verified use-by/best-before date", "Source of date evidence"],
                completion_criteria="The decisive date field is available for deterministic re-analysis.",
                action_boundary="Evidence-gathering task. SentiOH cannot infer missing date values.",
            ),
            _task(
                "Request missing supplier documentation",
                "MEDIUM",
                PROCUREMENT_TEAM,
                False,
                evidence=evidence,
                description="Prepare an internal request to obtain missing traceability documentation from the supplier.",
                why_generated="Generated because supplier-side records may resolve missing evidence preventing a confirmed or excluded result.",
                suggested_steps=[
                    "Identify the relevant supplier and purchase order.",
                    "List the specific missing fields required.",
                    "Prepare the request for human handling.",
                ],
                completion_evidence=["Supplier and purchase-order reference", "List of requested missing evidence"],
                completion_criteria="The missing evidence requirement is clearly documented and ready for human follow-up.",
                action_boundary="The prototype prepares the evidence request but does not autonomously send it.",
            ),
        ]

    return []
