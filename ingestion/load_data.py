from __future__ import annotations
import csv
import json
import re
from pathlib import Path

REQUIRED_CSV = {
    "products.csv": ["sku", "barcode", "product_name", "brand", "pack_size", "supplier_id"],
    "suppliers.csv": ["supplier_id", "supplier_name", "country"],
    "batches.csv": ["batch_id", "sku", "batch_code", "use_by", "best_before"],
    "inventory.csv": ["site_code", "site", "sku", "batch_code", "quantity"],
    "purchase_orders.csv": ["po", "supplier_id", "sku", "batch_code", "quantity", "date"],
    "dispatches.csv": ["dispatch_id", "customer", "sku", "batch_code", "quantity", "date"],
    "sites.csv": ["site_code", "site_name", "location"],
}

CRITICAL_NONEMPTY = {
    "products.csv": ["sku", "product_name", "supplier_id"],
    "suppliers.csv": ["supplier_id", "supplier_name"],
    "batches.csv": ["batch_id", "sku"],
    "inventory.csv": ["site_code", "sku", "quantity"],
    "purchase_orders.csv": ["po", "supplier_id", "sku", "quantity"],
    "dispatches.csv": ["dispatch_id", "customer", "sku", "quantity"],
    "sites.csv": ["site_code", "site_name"],
}

RECALL_REQUIRED_FIELDS = [
    "recall_id", "authority", "product_name", "brand", "pack_sizes",
    "batch_codes", "use_by", "best_before", "hazard", "source_url",
    "published_date", "is_public_source_verified",
]


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_bundle(data_dir):
    """
    Load the synthetic company sandbox plus regulatory recall inputs.

    Real FSAI product-scope recalls are the primary regulatory source when the
    bundled regulatory snapshot exists. Synthetic recalls remain available as
    fallback/test fixtures and are included in the combined `recalls` lookup so
    existing deterministic regression tests and demo scenarios still work.
    """
    data_dir = Path(data_dir)
    synthetic_recalls = load_json(data_dir / "recalls.json")

    regulatory_path = data_dir.parent / "regulatory_data" / "fsai_recalls.json"
    review_path = data_dir.parent / "regulatory_data" / "fsai_needs_review.json"

    real_recalls = (
        load_json(regulatory_path)
        if regulatory_path.exists()
        else []
    )
    fsai_review = (
        load_json(review_path)
        if review_path.exists()
        else []
    )

    bundle = {
        "real_recalls": real_recalls,
        "synthetic_recalls": synthetic_recalls,
        "fsai_review": fsai_review,
        "recalls": synthetic_recalls + real_recalls,
    }

    for filename in REQUIRED_CSV:
        bundle[filename[:-4]] = load_csv(data_dir / filename)

    return bundle


def _is_missing(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return len(value) == 0
    return False

def _looks_like_iso_date(value):
    if not value:
        return True
    if not isinstance(value, str):
        return False
    parts = value.split("-")
    return (
        len(parts) == 3
        and len(parts[0]) == 4
        and len(parts[1]) == 2
        and len(parts[2]) == 2
        and all(part.isdigit() for part in parts)
    )


def _is_placeholder_url(value):
    value = str(value or "").strip().lower()
    return (
        value.startswith("https://example.invalid")
        or value.startswith("http://example.invalid")
    )


def validate_bundle(data_dir):
    data_dir = Path(data_dir)
    issues = []
    warnings = []
    missing_values = {}
    recalls = load_json(data_dir / "recalls.json")
    counts = {"recalls": len(recalls)}

    recall_missing = {field: 0 for field in RECALL_REQUIRED_FIELDS}
    seen_recall_ids = set()

    for idx, recall in enumerate(recalls):
        rid = recall.get("recall_id") or f"record-{idx}"
        missing_fields = [
            f for f in RECALL_REQUIRED_FIELDS
            if f not in recall
        ]
        if missing_fields:
            issues.append(
                f"recalls.json record {idx}: missing fields {missing_fields}"
            )

        for field in RECALL_REQUIRED_FIELDS:
            if _is_missing(recall.get(field)):
                recall_missing[field] += 1

        if rid in seen_recall_ids:
            issues.append(f"recalls.json: duplicate recall_id '{rid}'")
        seen_recall_ids.add(rid)

        for field in ["pack_sizes", "batch_codes", "use_by", "best_before"]:
            value = recall.get(field)
            if value is not None and not isinstance(value, list):
                issues.append(
                    f"{rid}: '{field}' must be a list, not {type(value).__name__}"
                )

        for field in ["gtins", "barcodes"]:
            value = recall.get(field, [])
            if value is not None and not isinstance(value, list):
                issues.append(
                    f"{rid}: '{field}' must be a list when supplied"
                )

        date_values = (
            list(recall.get("use_by") or [])
            + list(recall.get("best_before") or [])
        )
        for date_value in date_values:
            if not _looks_like_iso_date(date_value):
                issues.append(
                    f"{rid}: invalid recall date '{date_value}', expected YYYY-MM-DD"
                )

        published = recall.get("published_date")
        if published and not _looks_like_iso_date(published):
            issues.append(
                f"{rid}: invalid published_date '{published}', expected YYYY-MM-DD"
            )

        source_url = recall.get("source_url")
        if _is_placeholder_url(source_url):
            issues.append(
                f"{rid}: placeholder example.invalid URL must not be presented as a recall source"
            )

        if recall.get("is_public_source_verified", False):
            if not source_url:
                issues.append(
                    f"{rid}: verified public recall requires source_url"
                )
            if not published:
                issues.append(
                    f"{rid}: verified public recall requires published_date"
                )
        else:
            warnings.append(
                f"{rid}: recall is a synthetic/unverified fixture."
            )

    missing_values["recalls.json"] = recall_missing

    for filename, required in REQUIRED_CSV.items():
        rows = load_csv(data_dir / filename)
        counts[filename] = len(rows)
        cols = list(rows[0].keys()) if rows else []
        missing_cols = [c for c in required if c not in cols]
        if missing_cols:
            issues.append(f"{filename}: missing columns {missing_cols}")
            continue

        field_missing = {
            col: sum(_is_missing(row.get(col)) for row in rows)
            for col in required
        }
        missing_values[filename] = field_missing

        for col in CRITICAL_NONEMPTY.get(filename, []):
            count = field_missing.get(col, 0)
            if count:
                issues.append(f"{filename}: {count} rows have missing critical value '{col}'")

    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "counts": counts,
        "missing_values": missing_values,
    }


def _looks_like_date_scope(value):
    if not value:
        return True
    if not isinstance(value, str):
        return False
    return bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        or re.fullmatch(r"\d{4}-\d{2}", value)
    )


def validate_fsai_snapshot(regulatory_dir):
    regulatory_dir = Path(regulatory_dir)
    path = regulatory_dir / "fsai_recalls.json"
    review_path = regulatory_dir / "fsai_needs_review.json"

    issues = []
    warnings = []
    recalls = load_json(path) if path.exists() else []
    review = load_json(review_path) if review_path.exists() else []

    if not recalls:
        issues.append("No primary FSAI recall records were loaded.")

    seen = set()
    official_ids = set()

    for idx, recall in enumerate(recalls):
        rid = recall.get("recall_id")
        if not rid:
            issues.append(f"FSAI record {idx}: missing recall_id")
            continue

        if rid in seen:
            issues.append(f"FSAI snapshot: duplicate recall_id '{rid}'")
        seen.add(rid)

        official = recall.get("official_recall_id")
        if not official:
            issues.append(f"{rid}: missing official_recall_id")
        else:
            official_ids.add(official)

        if not recall.get("product_name"):
            issues.append(f"{rid}: missing product_name")

        if recall.get("authority") != "Food Safety Authority of Ireland (FSAI)":
            warnings.append(f"{rid}: unexpected authority label")

        source_url = str(recall.get("source_url") or "")
        if not source_url.startswith("https://www.fsai.ie/"):
            issues.append(f"{rid}: source_url is not an official FSAI URL")

        if not recall.get("is_public_source_verified"):
            issues.append(f"{rid}: primary FSAI record is not source-verified")

        if recall.get("ingestion_status") == "REVIEW_REQUIRED":
            issues.append(
                f"{rid}: REVIEW_REQUIRED record must not be in primary recall store"
            )

        for field in ["pack_sizes", "batch_codes", "use_by", "best_before"]:
            if not isinstance(recall.get(field), list):
                issues.append(f"{rid}: {field} must be a list")

        for field in ["use_by", "best_before"]:
            for value in recall.get(field) or []:
                if not _looks_like_date_scope(value):
                    issues.append(
                        f"{rid}: invalid machine date scope '{value}' in {field}"
                    )

        published = recall.get("published_date")
        if published and not _looks_like_iso_date(published):
            issues.append(
                f"{rid}: invalid published_date '{published}'"
            )

    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "counts": {
            "primary_product_scope_recalls": len(recalls),
            "review_required_product_scope_recalls": len(review),
            "official_alert_ids": len(official_ids),
        },
    }


if __name__ == "__main__":
    import argparse
    import pprint

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="demo_data")
    args = parser.parse_args()
    pprint.pp(validate_bundle(args.data_dir))
