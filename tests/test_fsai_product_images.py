from __future__ import annotations

import json
from pathlib import Path

from ui.single_dashboard import _recall_image_urls


ROOT = Path(__file__).resolve().parents[1]


def test_official_fsai_snapshot_contains_product_images():
    recalls = json.loads(
        (ROOT / "regulatory_data" / "fsai_recalls.json")
        .read_text(encoding="utf-8")
    )

    with_images = [
        recall
        for recall in recalls
        if recall.get("image_url")
    ]

    assert with_images
    assert len(with_images) / len(recalls) >= 0.95
    assert all(
        str(recall["image_url"]).startswith("https://www.fsai.ie/")
        for recall in with_images
    )


def test_recall_image_selector_prefers_primary_and_deduplicates():
    recall = {
        "image_url": "https://www.fsai.ie/primary.png",
        "image_urls": [
            "https://www.fsai.ie/primary.png",
            "https://www.fsai.ie/second.png",
        ],
        "source_history": [
            {
                "image_url": "https://www.fsai.ie/old.png"
            }
        ],
    }

    assert _recall_image_urls(recall) == [
        "https://www.fsai.ie/primary.png",
        "https://www.fsai.ie/second.png",
        "https://www.fsai.ie/old.png",
    ]


def test_dashboard_displays_official_product_image_and_fallback_text():
    source = (
        ROOT / "ui" / "single_dashboard.py"
    ).read_text(encoding="utf-8")

    assert "Recalled product image" in source
    assert "Official FSAI product image" in source
    assert "Image source: official FSAI recall notice" in source
    assert "Open original image" in source
    assert "No product image was provided in the source recall notice." in source
    assert "st.image(" in source


def test_dashboard_labels_three_showcases_per_outcome():
    source = (
        ROOT / "ui" / "single_dashboard.py"
    ).read_text(encoding="utf-8")

    assert "showcase_position" in source
    assert "NO_ORGANISATIONAL_EXPOSURE_IDENTIFIED" in source
    assert "Investigation complete: no organisational exposure was identified" in source
