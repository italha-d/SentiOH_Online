from __future__ import annotations

import json
from pathlib import Path

from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner
from ingestion.load_data import load_bundle, validate_fsai_snapshot
from matching.matcher import resolve_exposure
from tools.context import ToolContext


ROOT = Path(__file__).resolve().parents[1]


def test_real_fsai_is_primary_and_synthetic_recalls_are_fallback():
    data = load_bundle(ROOT / "demo_data")

    assert len(data["real_recalls"]) == 181
    assert len(data["synthetic_recalls"]) == 3
    assert len(data["recalls"]) == 184

    assert all(
        item["source_type"] == "official_fsai_snapshot"
        for item in data["real_recalls"]
    )
    assert all(
        item["source_url"].startswith("https://www.fsai.ie/")
        for item in data["real_recalls"]
    )


def test_fsai_snapshot_is_valid_and_review_rows_are_separate():
    result = validate_fsai_snapshot(ROOT / "regulatory_data")
    assert result["ok"] is True
    assert result["counts"]["primary_product_scope_recalls"] == 181
    assert result["counts"]["review_required_product_scope_recalls"] == 3
    assert result["counts"]["official_alert_ids"] >= 50


def test_fsai_update_2026_38_is_consolidated_into_one_product_scope():
    data = load_bundle(ROOT / "demo_data")
    rows = [
        item
        for item in data["real_recalls"]
        if item.get("official_recall_id") == "2026.38"
    ]

    assert len(rows) == 1
    recall = rows[0]
    assert recall["product_name"] == "K O'Connell Fishmongers Smoked Salmon Slices"
    assert recall["batch_codes"] == ["SS16726"]
    assert set(recall["use_by"]) == {"2026-07-16", "2026-07-17"}
    assert set(recall["alert_versions"]) == {"Base", "Update 1"}
    assert len(recall["source_history"]) == 2


def test_real_fsai_showcase_outcomes():
    data = load_bundle(ROOT / "demo_data")
    scenarios = json.loads(
        (ROOT / "demo_data" / "real_fsai_showcase_scenarios.json")
        .read_text(encoding="utf-8")
    )

    for item in scenarios:
        recall = next(
            r for r in data["real_recalls"]
            if r["recall_id"] == item["recall_id"]
        )
        product = next(
            p for p in data["products"]
            if p["sku"] == item["sku"]
        )
        result = resolve_exposure(
            recall,
            product,
            data["batches"],
            data["inventory"],
            data["dispatches"],
        )

        assert result["status"] == item["expected_status"]
        assert result["reason_code"] == item["expected_reason_code"]


def test_real_confirmed_and_possible_recall_run_end_to_end():
    data = load_bundle(ROOT / "demo_data")
    scenarios = json.loads(
        (ROOT / "demo_data" / "real_fsai_showcase_scenarios.json")
        .read_text(encoding="utf-8")
    )

    counts = {
        status: sum(
            item["expected_status"] == status
            for item in scenarios
        )
        for status in ["CONFIRMED", "POSSIBLE", "NOT_AFFECTED"]
    }
    assert counts == {
        "CONFIRMED": 3,
        "POSSIBLE": 3,
        "NOT_AFFECTED": 3,
    }

    actionable = [
        item
        for item in scenarios
        if item["expected_status"] in {"CONFIRMED", "POSSIBLE"}
    ]
    assert len(actionable) == 6

    for item in actionable:
        ctx = ToolContext(data=data, cases={})
        state = SentiOHAgent(ctx, RulePlanner()).run(item["recall_id"])

        assert state.exposure["status"] == item["expected_status"]
        assert state.case_id in ctx.cases
        assert state.stop_reason != "MAX_AGENT_STEPS_REACHED"

        if item["expected_status"] == "CONFIRMED":
            assert state.status == "AWAITING_HUMAN_APPROVAL"
            assert state.stop_reason == "HUMAN_APPROVAL_REQUIRED"


def test_dashboard_defaults_to_full_feature_official_fsai_source():
    source = (
        ROOT / "ui" / "single_dashboard.py"
    ).read_text(encoding="utf-8")

    assert 'FULL_FEATURE_MODE = "Official FSAI (Full Feature Prototype)"' in source
    assert 'st.tabs(["Live Demo", "Official FSAI"])' in source
    assert 'st.session_state["recall_source_mode"] = "Official FSAI"' in source
    assert "Refresh official FSAI recalls" in source
    assert "Open official FSAI notice" in source
    assert "Official FSAI regulatory input" in source


def test_month_scope_matching_is_supported():
    from matching.matcher import _date_matches_scope

    assert _date_matches_scope("2027-05-15", "2027-05") is True
    assert _date_matches_scope("2027-06-01", "2027-05") is False
    assert _date_matches_scope("2027-05-15", "2027-05-15") is True


def test_all_official_fsai_recalls_terminate_without_step_cap():
    data = load_bundle(ROOT / "demo_data")

    for recall in data["real_recalls"]:
        ctx = ToolContext(data=data, cases={})
        state = SentiOHAgent(ctx, RulePlanner()).run(recall["recall_id"])

        assert state.status != "ERROR"
        assert state.stop_reason != "MAX_AGENT_STEPS_REACHED"


def test_non_matching_real_recall_gets_clean_no_exposure_conclusion():
    data = load_bundle(ROOT / "demo_data")
    showcase_ids = {
        item["recall_id"]
        for item in json.loads(
            (ROOT / "demo_data" / "real_fsai_showcase_scenarios.json")
            .read_text(encoding="utf-8")
        )
    }

    clean_state = None
    for recall in data["real_recalls"]:
        if recall["recall_id"] in showcase_ids:
            continue

        ctx = ToolContext(data=data, cases={})
        state = SentiOHAgent(ctx, RulePlanner()).run(recall["recall_id"])

        if state.investigation_conclusion == "NO_ORGANISATIONAL_EXPOSURE_IDENTIFIED":
            clean_state = state
            break

    assert clean_state is not None
    assert clean_state.status == "COMPLETE"
    assert clean_state.stop_reason in {
        "NO_PLAUSIBLE_CATALOGUE_CANDIDATE",
        "CANDIDATE_SEARCH_EXHAUSTED",
    }


def test_emergency_step_cap_is_16():
    from agent.policies import MAX_AGENT_STEPS

    assert MAX_AGENT_STEPS == 16
