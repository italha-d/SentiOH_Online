from __future__ import annotations

import json
from pathlib import Path

from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner
from ingestion.load_data import load_bundle, validate_bundle
from matching.matcher import search_catalogue
from tools.context import ToolContext

ROOT = Path(__file__).resolve().parents[1]


def test_recall_bundle_has_no_broken_placeholder_urls():
    recalls = json.loads(
        (ROOT / "demo_data" / "recalls.json").read_text(encoding="utf-8")
    )
    for recall in recalls:
        url = str(recall.get("source_url") or "")
        assert "example.invalid" not in url
        assert recall["is_public_source_verified"] is False


def test_catalogue_ranking_puts_expected_demo_products_first():
    data = load_bundle(ROOT / "demo_data")

    r1 = next(r for r in data["recalls"] if r["recall_id"] == "FSAI_DEMO_001")
    r3 = next(r for r in data["recalls"] if r["recall_id"] == "FSAI_DEMO_003")

    c1 = search_catalogue(r1, data["products"], limit=5)
    c3 = search_catalogue(r3, data["products"], limit=5)

    assert c1[0]["sku"] == "SKU001"
    assert c3[0]["sku"] == "SKU008"


def test_all_bundled_recalls_resolve_to_locked_demo_expectations():
    data = load_bundle(ROOT / "demo_data")
    expected = json.loads(
        (ROOT / "demo_data" / "recall_demo_expectations.json")
        .read_text(encoding="utf-8")
    )

    for item in expected:
        ctx = ToolContext(data=data, cases={})
        state = SentiOHAgent(ctx, RulePlanner()).run(item["recall_id"])
        exposure = state.exposure

        assert exposure["sku"] == item["expected_sku"]
        assert exposure["status"] == item["expected_status"]
        assert exposure["reason_code"] == item["expected_reason_code"]
        assert exposure["stock"] == item["expected_stock"]
        assert exposure["dispatched"] == item["expected_dispatched"]


def test_recall_validator_accepts_synthetic_null_urls_but_rejects_broken_placeholders(tmp_path):
    data_dir = tmp_path / "demo_data"
    data_dir.mkdir()

    # Copy the actual demo data files.
    for source in (ROOT / "demo_data").iterdir():
        if source.is_file():
            (data_dir / source.name).write_bytes(source.read_bytes())

    result = validate_bundle(data_dir)
    assert result["ok"] is True

    recalls_path = data_dir / "recalls.json"
    recalls = json.loads(recalls_path.read_text(encoding="utf-8"))
    recalls[0]["source_url"] = "https://example.invalid/broken-demo-link"
    recalls_path.write_text(json.dumps(recalls), encoding="utf-8")

    broken = validate_bundle(data_dir)
    assert broken["ok"] is False
    assert any("example.invalid" in issue for issue in broken["issues"])
