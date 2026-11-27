from __future__ import annotations

import csv
import json
from pathlib import Path

from ingestion import fsai_refresh


class FakeRun:
    returncode = 0
    stdout = "Saved 1 rows"
    stderr = ""


def test_live_refresh_merges_new_official_record_without_network(tmp_path, monkeypatch):
    project = tmp_path
    scraper_dir = project / "integrations" / "fsai_scraper"
    regulatory = project / "regulatory_data"
    scraper_dir.mkdir(parents=True)
    regulatory.mkdir()

    # The refresh service only requires the scraper path to exist because the
    # subprocess is mocked in this regression test.
    (scraper_dir / "fsai_recall_scraper.py").write_text("# mocked\n")

    existing = [{
        "recall_id": "FSAI_2026_01_EXISTING",
        "official_recall_id": "2026.01",
        "authority": "Food Safety Authority of Ireland (FSAI)",
        "product_name": "Existing Product",
        "brand": None,
        "pack_sizes": ["100g"],
        "batch_codes": ["OLD"],
        "use_by": [],
        "best_before": [],
        "date_scope_text": [],
        "hazard": "Hazard",
        "hazard_history": ["Hazard"],
        "country_of_origin": [],
        "source_url": "https://www.fsai.ie/existing",
        "published_date": "2026-01-01",
        "source_history": [{
            "alert_version": "Base",
            "published_date": "2026-01-01",
            "source_url": "https://www.fsai.ie/existing",
            "image_url": None,
            "quality": "VERIFIED_FSAI",
        }],
        "image_url": None,
        "image_urls": [],
        "source_type": "official_fsai_snapshot",
        "ingestion_status": "VERIFIED",
        "data_quality_labels": ["VERIFIED_FSAI"],
        "review_reason": None,
        "is_public_source_verified": True,
        "manufacturer": None,
        "gtins": [],
        "barcodes": [],
        "source_note": "test",
        "alert_versions": ["Base"],
    }]
    (regulatory / "fsai_recalls.json").write_text(json.dumps(existing))
    (regulatory / "fsai_needs_review.json").write_text("[]")

    def fake_run(cmd, cwd, capture_output, text, timeout):
        output_index = cmd.index("--output") + 1
        output = Path(cmd[output_index])
        with output.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "Recall ID", "Product Name", "Brand", "Pack Size",
                    "Batch Code", "Use By", "Best Before", "Hazard",
                    "Published Date", "Source URL", "Image URL",
                ],
            )
            writer.writeheader()
            writer.writerow({
                "Recall ID": "2026.99",
                "Product Name": "New Official Product",
                "Brand": "",
                "Pack Size": "200g",
                "Batch Code": "LOT99",
                "Use By": "2026-12-01",
                "Best Before": "",
                "Hazard": "Salmonella",
                "Published Date": "2026-09-09",
                "Source URL": "https://www.fsai.ie/new-alert",
                "Image URL": "",
            })
        review = output.with_name(output.stem + "_needs_review.csv")
        with review.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "Recall ID", "Product Name", "Brand", "Pack Size",
                "Batch Code", "Use By", "Best Before", "Hazard",
                "Published Date", "Source URL", "Image URL", "Review Reason",
            ])
        return FakeRun()

    monkeypatch.setattr(fsai_refresh.subprocess, "run", fake_run)

    result = fsai_refresh.refresh_fsai_snapshot(
        project,
        from_date="2026-09-01",
        to_date="2026-09-09",
        max_pages=2,
        delay=0,
    )

    merged = json.loads(
        (regulatory / "fsai_recalls.json").read_text(encoding="utf-8")
    )

    assert len(merged) == 2
    assert len(result["new_recall_ids"]) == 1
    new = next(
        item for item in merged
        if item["official_recall_id"] == "2026.99"
    )
    assert new["product_name"] == "New Official Product"
    assert new["batch_codes"] == ["LOT99"]
    assert new["is_public_source_verified"] is True
