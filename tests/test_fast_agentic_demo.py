from agent.planner import OllamaToolPlanner, FAST_DEMO_TOOL_DESCRIPTIONS
from agent.orchestrator import SentiOHAgent
from ingestion.load_data import load_bundle
from pathlib import Path
from tools.context import ToolContext
from tools.demo_tools import resolve_company_exposure, trace_internal_evidence


def _ctx(tmp_path):
    data = load_bundle(Path(__file__).resolve().parents[1] / "demo_data")
    # Prepared pitch alias uses genuine source content but a separate demo id.
    source = next(r for r in data["real_recalls"] if r.get("official_recall_id") == "2026.38")
    alias = dict(source)
    alias["recall_id"] = "PITCH_DEMO_FSAI_2026_38"
    data["recalls"].append(alias)
    return ToolContext(data=data, cases={})


def test_fast_demo_planner_exposes_only_high_level_agent_tools():
    planner = OllamaToolPlanner(fast_mode=True)
    assert planner.fast_mode is True
    assert set(FAST_DEMO_TOOL_DESCRIPTIONS) == {
        "get_recall",
        "resolve_company_exposure",
        "trace_internal_evidence",
        "open_response_case",
        "request_human_approval",
    }


def test_composite_tools_preserve_deterministic_subtool_trace(tmp_path):
    ctx = _ctx(tmp_path)
    resolved = resolve_company_exposure(ctx, "PITCH_DEMO_FSAI_2026_38")
    assert resolved["ok"] is True
    assert (resolved["exposure"] or {}).get("status") == "CONFIRMED"
    names = [item["tool"] for item in resolved["subtools"]]
    assert names[0] == "search_catalogue"
    assert "get_batches" in names
    assert "resolve_exposure" in names

    batches = (resolved["exposure"] or {}).get("matched_batches") or []
    traced = trace_internal_evidence(ctx, resolved["active_sku"], batches)
    assert traced["ok"] is True
    assert [item["tool"] for item in traced["subtools"]] == [
        "get_inventory", "get_dispatches", "get_purchase_history"
    ]


def test_recommendation_only_enrichment_mode_is_supported(tmp_path):
    class DummyPlanner:
        def decide(self, state):
            return {"action": "FINISH", "summary": "done", "planner_source": "test"}
        def generate_recommendation(self, state):
            return {"headline": "x", "justification": "y", "recommended_next_step": "z"}

    agent = SentiOHAgent(ToolContext(data={}, cases={}), DummyPlanner(), enrichment_mode="recommendation_only")
    assert agent.enrichment_mode == "recommendation_only"
