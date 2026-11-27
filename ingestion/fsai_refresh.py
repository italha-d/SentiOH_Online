from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from .fsai_adapter import (
    merge_snapshots,
    normalise_rows,
    read_csv_rows,
)


def _fingerprint(record):
    material = {
        "product_name": record.get("product_name"),
        "brand": record.get("brand"),
        "pack_sizes": record.get("pack_sizes") or [],
        "batch_codes": record.get("batch_codes") or [],
        "use_by": record.get("use_by") or [],
        "best_before": record.get("best_before") or [],
        "hazard": record.get("hazard"),
        "published_date": record.get("published_date"),
        "source_url": record.get("source_url"),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, default=str).encode()
    ).hexdigest()


def _review_key(row):
    return (
        str(row.get("Recall ID") or "").strip(),
        str(row.get("Product Name") or "").strip(),
        str(row.get("Pack Size") or "").strip(),
        str(row.get("Batch Code") or "").strip(),
        str(row.get("Source URL") or "").strip(),
    )


def _load_review_map(path):
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return {
        _review_key(row): str(row.get("Review Reason") or "").strip()
        for row in rows
    }


def refresh_fsai_snapshot(
    project_root,
    from_date=None,
    to_date=None,
    max_pages=10,
    delay=0.5,
    show_browser=False,
):
    """
    Run the corrected FSAI scraper, normalise its result, and merge it into the
    bundled regulatory snapshot.

    This is application-controlled ingestion, not an autonomous agent tool.
    """
    project_root = Path(project_root)
    scraper = (
        project_root
        / "integrations"
        / "fsai_scraper"
        / "fsai_recall_scraper.py"
    )
    regulatory_dir = project_root / "regulatory_data"
    snapshot_path = regulatory_dir / "fsai_recalls.json"
    review_path = regulatory_dir / "fsai_needs_review.json"
    metadata_path = regulatory_dir / "fsai_ingestion_metadata.json"

    if not scraper.exists():
        raise FileNotFoundError(
            f"Corrected FSAI scraper not found: {scraper}"
        )

    to_date = to_date or date.today().isoformat()

    with tempfile.TemporaryDirectory(prefix="sentioh_fsai_") as tmp:
        output_csv = Path(tmp) / "fsai_live.csv"

        cmd = [
            sys.executable,
            str(scraper),
            "--to-date",
            str(to_date),
            "--max-pages",
            str(int(max_pages)),
            "--delay",
            str(float(delay)),
            "--output",
            str(output_csv),
        ]
        if from_date:
            cmd.extend(["--from-date", str(from_date)])
        if show_browser:
            cmd.append("--show-browser")

        run = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if run.returncode != 0:
            raise RuntimeError(
                "FSAI scraper failed.\n"
                + (run.stderr or run.stdout or "No scraper output.")
            )

        rows = read_csv_rows(output_csv)
        review_map = _load_review_map(
            output_csv.with_name(
                output_csv.stem + "_needs_review.csv"
            )
        )

        # The live scraper writes the legacy schema. Attach explicit quality
        # status before normalisation.
        for row in rows:
            key = _review_key(row)
            if key in review_map:
                row["Data Quality"] = "REVIEW_REQUIRED"
                row["Review Reason"] = review_map[key]
            else:
                row["Data Quality"] = "SOURCE_CAPTURED"
                row["Review Reason"] = ""
            row.setdefault("Alert Version", "Base")
            row.setdefault("Expiry Date", "")
            row.setdefault("Country of Origin", "")

        incoming_primary, incoming_review = normalise_rows(rows)

    existing = (
        json.loads(snapshot_path.read_text(encoding="utf-8"))
        if snapshot_path.exists()
        else []
    )
    existing_review = (
        json.loads(review_path.read_text(encoding="utf-8"))
        if review_path.exists()
        else []
    )

    before = {
        item["recall_id"]: _fingerprint(item)
        for item in existing
    }

    merged = merge_snapshots(
        existing,
        incoming_primary,
    )
    merged_review = merge_snapshots(
        existing_review,
        incoming_review,
    )

    after = {
        item["recall_id"]: _fingerprint(item)
        for item in merged
    }

    new_ids = sorted(set(after) - set(before))
    changed_ids = sorted(
        rid
        for rid in set(after) & set(before)
        if after[rid] != before[rid]
    )

    regulatory_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    review_path.write_text(
        json.dumps(merged_review, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    metadata = {
        "last_live_refresh": date.today().isoformat(),
        "refresh_from_date": str(from_date) if from_date else None,
        "refresh_to_date": str(to_date),
        "scraper_rows": len(rows),
        "incoming_primary": len(incoming_primary),
        "incoming_review_required": len(incoming_review),
        "primary_product_scope_recalls": len(merged),
        "review_required_product_scope_recalls": len(merged_review),
        "new_recall_ids": new_ids,
        "changed_recall_ids": changed_ids,
        "scraper_stdout_tail": (run.stdout or "")[-4000:],
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    return metadata
