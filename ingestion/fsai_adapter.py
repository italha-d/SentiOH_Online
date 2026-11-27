from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


OFFICIAL_FSAI_PREFIX = "https://www.fsai.ie/"
REVIEW_STATUS = "REVIEW_REQUIRED"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip(" ;")


def _split(value):
    value = _clean(value)
    if not value:
        return []
    return [
        _clean(part)
        for part in re.split(r"\s*;\s*", value)
        if _clean(part)
    ]


def _date_scope(value):
    """
    Return machine-comparable date scope plus free-text scope.

    SentiOH supports YYYY-MM-DD exact dates and YYYY-MM month scopes.
    Other regulator wording such as "ALL" or "up to and including..." is
    preserved as source text rather than converted into a false precise date.
    """
    value = _clean(value)
    if not value:
        return None, None

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value, None
    if re.fullmatch(r"\d{4}-\d{2}", value):
        return value, None

    return None, value


def _stable_recall_id(official_id, product, brand, pack_key):
    basis = "|".join([
        _clean(official_id).lower(),
        _clean(product).lower(),
        _clean(brand).lower(),
        _clean(pack_key).lower(),
    ])
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:10].upper()
    official = re.sub(r"[^0-9A-Za-z]+", "_", _clean(official_id)).strip("_")
    return f"FSAI_{official}_{digest}"


def _quality_status(labels):
    labels = {_clean(label) for label in labels if _clean(label)}
    if any(label == REVIEW_STATUS for label in labels):
        return REVIEW_STATUS
    if any(label.startswith("VERIFIED_FSAI") for label in labels):
        return "VERIFIED"
    return "SOURCE_CAPTURED"


def _latest_source(history):
    if not history:
        return {}
    return sorted(
        history,
        key=lambda item: (
            item.get("published_date") or "",
            item.get("alert_version") or "",
        ),
    )[-1]


def read_csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def normalise_rows(rows: Iterable[dict]):
    """
    Convert FSAI scraper/corrected rows into one stable SentiOH recall item per
    official alert + product + pack scope.

    Multiple batches/dates and later updates for the same product scope are
    consolidated. This prevents an update from erasing the original affected
    date/lot scope while retaining full source history.
    """
    groups = defaultdict(list)

    for row in rows:
        official_id = _clean(row.get("Recall ID"))
        product = _clean(row.get("Product Name"))
        brand = _clean(row.get("Brand"))
        pack = _clean(row.get("Pack Size"))

        if not official_id or not product:
            continue

        # The corrected parser should already remove these, but keep a final
        # ingestion guardrail around common Alert Summary labels.
        if product.lower().rstrip(":") in {
            "batch code",
            "country of origin",
            "product identification",
            "message",
            "pack size",
        }:
            continue

        key = (
            official_id,
            product,
            brand,
            pack,
        )
        groups[key].append(dict(row))

    primary = []
    review = []

    for (official_id, product, brand, pack_key), items in groups.items():
        packs = []
        batches = []
        use_by = []
        best_before = []
        date_scope_text = []
        countries = []
        hazards = []
        image_urls = []
        quality_labels = []
        review_reasons = []
        source_history = []

        for item in items:
            packs.extend(_split(item.get("Pack Size")))
            batches.extend(_split(item.get("Batch Code")))

            for raw in _split(item.get("Use By")):
                machine, text = _date_scope(raw)
                if machine:
                    use_by.append(machine)
                elif text:
                    date_scope_text.append(f"Use By: {text}")

            for raw in (
                _split(item.get("Best Before"))
                + _split(item.get("Expiry Date"))
            ):
                machine, text = _date_scope(raw)
                if machine:
                    best_before.append(machine)
                elif text:
                    date_scope_text.append(f"Best Before / Expiry: {text}")

            country = _clean(item.get("Country of Origin"))
            if country:
                countries.append(country)

            hazard = _clean(item.get("Hazard"))
            if hazard:
                hazards.append(hazard)

            image = _clean(item.get("Image URL"))
            if image:
                image_urls.append(image)

            quality = _clean(item.get("Data Quality")) or "SOURCE_CAPTURED"
            quality_labels.append(quality)

            reason = _clean(item.get("Review Reason"))
            if reason:
                review_reasons.append(reason)

            url = _clean(item.get("Source URL"))
            published = _clean(item.get("Published Date"))
            version = _clean(item.get("Alert Version")) or "Base"

            if url:
                source_history.append({
                    "alert_version": version,
                    "published_date": published,
                    "source_url": url,
                    "image_url": image or None,
                    "quality": quality,
                })

        def unique(values):
            seen = set()
            out = []
            for value in values:
                if value and value not in seen:
                    seen.add(value)
                    out.append(value)
            return out

        packs = unique(packs)
        batches = unique(batches)
        use_by = unique(use_by)
        best_before = unique(best_before)
        date_scope_text = unique(date_scope_text)
        countries = unique(countries)
        hazards = unique(hazards)
        image_urls = unique(image_urls)
        quality_labels = unique(quality_labels)
        review_reasons = unique(review_reasons)

        source_history = [
            dict(t)
            for t in {
                (
                    item.get("alert_version"),
                    item.get("published_date"),
                    item.get("source_url"),
                    item.get("image_url"),
                    item.get("quality"),
                ): item
                for item in source_history
            }.values()
        ]
        source_history.sort(
            key=lambda item: (
                item.get("published_date") or "",
                item.get("alert_version") or "",
            )
        )
        latest = _latest_source(source_history)
        status = _quality_status(quality_labels)

        source_url = latest.get("source_url")
        official_source = bool(
            source_url
            and source_url.lower().startswith(OFFICIAL_FSAI_PREFIX)
        )

        record = {
            "recall_id": _stable_recall_id(
                official_id,
                product,
                brand,
                pack_key,
            ),
            "official_recall_id": official_id,
            "authority": "Food Safety Authority of Ireland (FSAI)",
            "alert_versions": unique(
                item.get("alert_version") or "Base"
                for item in source_history
            ),
            "product_name": product,
            "brand": brand or None,
            "pack_sizes": packs,
            "batch_codes": batches,
            "use_by": use_by,
            "best_before": best_before,
            "date_scope_text": date_scope_text,
            "hazard": hazards[0] if hazards else None,
            "hazard_history": hazards,
            "country_of_origin": countries,
            "source_url": source_url,
            "published_date": latest.get("published_date"),
            "source_history": source_history,
            "image_url": latest.get("image_url") or (image_urls[0] if image_urls else None),
            "image_urls": image_urls,
            "source_type": "official_fsai_snapshot",
            "ingestion_status": status,
            "data_quality_labels": quality_labels,
            "review_reason": " | ".join(review_reasons) if review_reasons else None,
            "is_public_source_verified": bool(official_source and status != REVIEW_STATUS),
            "manufacturer": None,
            "gtins": [],
            "barcodes": [],
            "source_note": (
                "Regulatory recall evidence captured from the official FSAI food-alert source. "
                "Missing public fields remain empty rather than being inferred."
            ),
        }

        if status == REVIEW_STATUS:
            review.append(record)
        else:
            primary.append(record)

    primary.sort(
        key=lambda item: (
            item.get("published_date") or "",
            item.get("official_recall_id") or "",
            item.get("product_name") or "",
        ),
        reverse=True,
    )
    review.sort(
        key=lambda item: (
            item.get("published_date") or "",
            item.get("official_recall_id") or "",
        ),
        reverse=True,
    )
    return primary, review


def merge_snapshots(existing, incoming):
    """
    Merge live refresh results into a previously validated snapshot.

    The stable product-scope recall_id is the merge key. Existing source
    history and lot/date scope are retained and extended, which supports FSAI
    update notices and SentiOH differential case re-analysis.
    """
    merged = {item["recall_id"]: dict(item) for item in existing}

    for new in incoming:
        rid = new["recall_id"]
        old = merged.get(rid)
        if old is None:
            merged[rid] = dict(new)
            continue

        for field in [
            "pack_sizes",
            "batch_codes",
            "use_by",
            "best_before",
            "date_scope_text",
            "alert_versions",
            "hazard_history",
            "country_of_origin",
            "image_urls",
            "data_quality_labels",
        ]:
            values = []
            for source in [old.get(field) or [], new.get(field) or []]:
                for value in source:
                    if value and value not in values:
                        values.append(value)
            old[field] = values

        history = []
        seen = set()
        for item in (old.get("source_history") or []) + (new.get("source_history") or []):
            key = (
                item.get("alert_version"),
                item.get("published_date"),
                item.get("source_url"),
            )
            if key not in seen:
                seen.add(key)
                history.append(item)
        history.sort(
            key=lambda item: (
                item.get("published_date") or "",
                item.get("alert_version") or "",
            )
        )
        old["source_history"] = history

        latest = _latest_source(history)
        if latest:
            old["source_url"] = latest.get("source_url")
            old["published_date"] = latest.get("published_date")
            old["image_url"] = latest.get("image_url") or old.get("image_url")

        old["ingestion_status"] = (
            "VERIFIED"
            if "VERIFIED" in {old.get("ingestion_status"), new.get("ingestion_status")}
            else new.get("ingestion_status") or old.get("ingestion_status")
        )
        old["is_public_source_verified"] = bool(
            old.get("source_url")
            and str(old.get("source_url")).lower().startswith(OFFICIAL_FSAI_PREFIX)
        )
        merged[rid] = old

    result = list(merged.values())
    result.sort(
        key=lambda item: (
            item.get("published_date") or "",
            item.get("official_recall_id") or "",
            item.get("product_name") or "",
        ),
        reverse=True,
    )
    return result


def build_snapshot(
    csv_path,
    output_json,
    review_json=None,
    metadata_json=None,
    merge_existing=False,
):
    csv_path = Path(csv_path)
    output_json = Path(output_json)
    rows = read_csv_rows(csv_path)
    primary, review = normalise_rows(rows)

    if merge_existing and output_json.exists():
        existing = json.loads(output_json.read_text(encoding="utf-8"))
        primary = merge_snapshots(existing, primary)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(primary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if review_json:
        review_json = Path(review_json)
        review_json.write_text(
            json.dumps(review, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if metadata_json:
        metadata_json = Path(metadata_json)
        metadata = {
            "generated_at": _now(),
            "input_csv": csv_path.name,
            "input_rows": len(rows),
            "primary_product_scope_recalls": len(primary),
            "review_required_product_scope_recalls": len(review),
            "official_authority": "Food Safety Authority of Ireland (FSAI)",
            "missing_field_policy": "Preserve missing public values as null/empty; never infer them.",
        }
        metadata_json.write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "primary": primary,
        "review": review,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--output", default="regulatory_data/fsai_recalls.json")
    parser.add_argument(
        "--review-output",
        default="regulatory_data/fsai_needs_review.json",
    )
    parser.add_argument(
        "--metadata-output",
        default="regulatory_data/fsai_ingestion_metadata.json",
    )
    parser.add_argument("--merge-existing", action="store_true")
    args = parser.parse_args()

    result = build_snapshot(
        args.csv_path,
        args.output,
        args.review_output,
        args.metadata_output,
        merge_existing=args.merge_existing,
    )
    print(
        f"Primary: {len(result['primary'])} | "
        f"Review required: {len(result['review'])}"
    )
