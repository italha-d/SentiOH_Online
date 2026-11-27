from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from agent.orchestrator import SentiOHAgent
from agent.planner import OllamaToolPlanner, RulePlanner
from agent.state import InvestigationState
from ingestion.load_data import load_bundle
from tools.context import ToolContext
from workflow.llm_enrichment import apply_task_narratives
from workflow.tasks import create_tasks
from workflow.versioning import register_recall_version
from workflow.workflow import open_case


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_llm_task_narrative_changes_only_explanatory_fields():
    exposure = {
        "recall_id": "R-ENRICH",
        "sku": "SKU001",
        "status": "CONFIRMED",
        "batch": "B1",
        "matched_batches": ["B1"],
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
        "stock": 41,
        "dispatched": 27,
    }
    case = open_case(exposure)
    protected = next(
        task for task in case["tasks"]
        if task["requires_approval"]
    )

    immutable_before = {
        key: deepcopy(protected.get(key))
        for key in [
            "title",
            "priority",
            "assigned_to",
            "requires_approval",
            "approval_roles",
            "approval_mode",
            "completion_evidence",
            "completion_criteria",
            "action_boundary",
            "status",
        ]
    }

    count = apply_task_narratives(
        case,
        [{
            "task_id": protected["task_id"],
            "why_generated": (
                "Lot B1 is confirmed in scope and 41 units remain in "
                "structured inventory, so containment preparation is required."
            ),
            "suggested_steps": [
                "Review SKU001 and lot B1 evidence.",
                "Verify the affected stock location and quantity.",
                "Request the required manager approval before containment.",
            ],
        }],
        "llama3.2:latest",
    )

    assert count == 1
    assert protected["narrative_source"] == "llm"
    assert protected["narrative_model"] == "llama3.2:latest"
    assert "41 units" in protected["why_generated"]
    assert protected["template_why_generated"]
    assert protected["template_suggested_steps"]

    immutable_after = {
        key: protected.get(key)
        for key in immutable_before
    }
    assert immutable_after == immutable_before


def test_ollama_generates_structured_task_narratives(monkeypatch):
    exposure = {
        "recall_id": "R-TASKS",
        "sku": "SKU001",
        "status": "CONFIRMED",
        "batch": "B1",
        "matched_batches": ["B1"],
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
        "stock": 41,
        "dispatched": 27,
    }
    tasks = create_tasks(exposure)
    state = InvestigationState(recall_id="R-TASKS")
    state.exposure = exposure
    state.inventory = {"total_quantity": 41}
    state.dispatches = {"total_dispatched": 27}

    generated = {
        "tasks": [
            {
                "task_id": task["task_id"],
                "why_generated": (
                    f"Case-specific rationale for {task['title']} "
                    "using the confirmed structured evidence."
                ),
                "suggested_steps": [
                    "Review the structured case evidence.",
                    "Perform the assigned internal verification.",
                ],
            }
            for task in tasks
        ]
    }

    def fake_post(url, json, timeout):
        assert json["model"] == "llama3.2:latest"
        assert json["format"]["required"] == ["tasks"]
        return FakeResponse({
            "message": {
                "content": __import__("json").dumps(generated)
            }
        })

    monkeypatch.setattr(
        "agent.planner.requests.post",
        fake_post,
    )

    planner = OllamaToolPlanner(
        model="llama3.2:latest"
    )
    result = planner.generate_task_narratives(
        state,
        tasks,
    )

    assert len(result) == len(tasks)
    assert result[0]["task_id"] == tasks[0]["task_id"]
    assert result[0]["suggested_steps"]


def test_ollama_generates_possible_evidence_gap_reasoning(monkeypatch):
    state = InvestigationState(recall_id="R-GAP")
    state.exposure = {
        "recall_id": "R-GAP",
        "sku": "SKU005",
        "status": "POSSIBLE",
        "reason_code": "LOT_SCOPE_NOT_SPECIFIED",
        "stock": 60,
        "dispatched": 15,
    }
    state.missing_evidence = [
        "Decisive recall lot/scope evidence"
    ]
    state.inventory = {"total_quantity": 60}
    state.dispatches = {"total_dispatched": 15}

    payload = {
        "summary": (
            "Product evidence is relevant but the recall does not provide "
            "a decisive lot scope."
        ),
        "decisive_missing_evidence": [
            "Authoritative affected lot/batch scope"
        ],
        "priority_evidence": "Affected lot/batch scope",
        "why_this_evidence_first": (
            "Lot scope is the missing constraint needed for deterministic "
            "confirmation or exclusion."
        ),
        "recommended_evidence_action": (
            "Verify the physical lot and obtain the authoritative lot scope "
            "for deterministic re-analysis."
        ),
        "confidence_note": (
            "This is evidence-prioritisation only; exposure remains POSSIBLE."
        ),
    }

    def fake_post(url, json, timeout):
        return FakeResponse({
            "message": {
                "content": __import__("json").dumps(payload)
            }
        })

    monkeypatch.setattr(
        "agent.planner.requests.post",
        fake_post,
    )

    planner = OllamaToolPlanner(
        model="llama3.2:latest"
    )
    analysis = planner.analyse_evidence_gap(state)

    assert analysis["priority_evidence"] == "Affected lot/batch scope"
    assert "POSSIBLE" in analysis["confidence_note"]


def test_recall_revision_uses_differential_reanalysis_without_catalogue_search():
    data = load_bundle(ROOT / "demo_data")
    ctx = ToolContext(data=data, cases={})
    agent = SentiOHAgent(ctx, RulePlanner())

    first = agent.run("FSAI_DEMO_001")
    case_id = first.case_id

    update = json.loads(
        (ROOT / "demo_data" / "recall_updates.json")
        .read_text(encoding="utf-8")
    )[0]
    recall = next(
        item for item in data["recalls"]
        if item["recall_id"] == update["recall_id"]
    )
    for key, value in update["patch"].items():
        recall[key] = value

    assert register_recall_version(
        ctx.cases[case_id],
        recall,
    ) is True

    second = agent.run("FSAI_DEMO_001")
    tools = [
        event.tool
        for event in second.events
        if event.tool
    ]

    assert second.reanalysis_context["mode"] == "DIFFERENTIAL"
    assert second.reanalysis_context["reused_sku"] == "SKU001"
    assert "product_identity" in second.reused_evidence
    assert "search_catalogue" not in tools
    assert "get_recall" in tools
    assert "get_batches" in tools
    assert "resolve_exposure" in tools
    assert "get_inventory" in tools
    assert "get_dispatches" in tools
    assert "get_purchase_history" in tools

    updated_case = ctx.cases[case_id]
    assert updated_case["analysis_revision"] == 2
    assert updated_case["exposure"]["matched_batches"] == [
        "SS16726",
        "SS16727",
    ]


def test_recall_change_summary_records_changed_fields():
    exposure = {
        "recall_id": "R-DIFF",
        "sku": "SKU1",
        "status": "CONFIRMED",
        "batch": "A",
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
    }
    case = open_case(exposure)

    first = {
        "product_name": "Product",
        "brand": "Brand",
        "pack_sizes": ["100g"],
        "batch_codes": ["A"],
        "use_by": ["2026-01-01"],
        "best_before": [],
        "hazard": "Hazard",
        "gtins": [],
        "barcodes": [],
    }
    second = deepcopy(first)
    second["batch_codes"] = ["A", "B"]

    assert register_recall_version(case, first) is False
    assert register_recall_version(case, second) is True

    assert case["recall_change_summary"]["changed_fields"] == [
        "batch_codes"
    ]
    assert case["recall_change_summary"]["before"]["batch_codes"] == ["A"]
    assert case["recall_change_summary"]["after"]["batch_codes"] == ["A", "B"]
