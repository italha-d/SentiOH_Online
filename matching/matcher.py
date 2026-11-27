from __future__ import annotations
from .normalise import (
    norm_text, norm_brand, norm_batch, norm_pack, norm_identifier,
    recall_identifiers,
)
from .similarity import similarity
from .trace import inventory_records, dispatch_records, total_quantity

VALID_STATES = {
    "CONFIRMED", "POSSIBLE", "NOT_AFFECTED", "INSUFFICIENT_EVIDENCE"
}


def _date_matches_scope(company_date, recall_scope):
    """
    Match an exact company date to an FSAI date scope.

    FSAI sometimes publishes only month/year (e.g. 2027-05). A month scope
    matches any company YYYY-MM-DD date in that month. Exact YYYY-MM-DD scope
    remains exact. Free-text date wording is kept outside the machine date
    arrays by the FSAI adapter.
    """
    company_date = str(company_date or "").strip()
    recall_scope = str(recall_scope or "").strip()

    if not company_date or not recall_scope:
        return False

    if recall_scope == company_date:
        return True

    if len(recall_scope) == 7 and recall_scope[4] == "-":
        return company_date.startswith(recall_scope + "-")

    return False


def _any_date_scope_match(company_dates, recall_dates):
    return any(
        _date_matches_scope(company_date, recall_scope)
        for company_date in company_dates
        for recall_scope in recall_dates
    )


def _product_identifier(product):
    return norm_identifier(product.get("barcode"))


def search_catalogue(recall, products, limit=5, threshold=60.0):
    qname = norm_text(recall.get("product_name"))
    qbrand = norm_brand(recall.get("brand"))
    qpacks = {norm_pack(x) for x in recall.get("pack_sizes", []) if x}
    source_ids = recall_identifiers(recall)

    candidates = []
    for product in products:
        product_id = _product_identifier(product)
        identifier_match = bool(source_ids and product_id and product_id in source_ids)
        score = similarity(qname, norm_text(product.get("product_name")))
        brand_match = (not qbrand) or qbrand == norm_brand(product.get("brand"))
        pack_match = (not qpacks) or norm_pack(product.get("pack_size")) in qpacks

        if identifier_match or score >= threshold:
            candidates.append({
                "sku": product.get("sku"),
                "barcode": product.get("barcode"),
                "product_name": product.get("product_name"),
                "brand": product.get("brand"),
                "pack_size": product.get("pack_size"),
                "similarity": round(score, 1),
                "identifier_match": identifier_match,
                "brand_match": brand_match,
                "pack_size_match": pack_match,
                "candidate_basis": "EXACT_SOURCE_IDENTIFIER" if identifier_match else "FUZZY_PRODUCT_CANDIDATE",
            })

    candidates.sort(
        key=lambda x: (
            x["identifier_match"],
            x["brand_match"],
            x["pack_size_match"],
            x["similarity"],
        ),
        reverse=True,
    )
    return candidates[:limit]


def resolve_exposure(recall, product, batches, inventory, dispatches, fuzzy_threshold=76.0):
    score = similarity(
        norm_text(recall.get("product_name")),
        norm_text(product.get("product_name")),
    )
    fuzzy_name_match = score >= fuzzy_threshold

    source_ids = recall_identifiers(recall)
    product_id = _product_identifier(product)
    identifier_match = bool(source_ids and product_id and product_id in source_ids)
    identifier_mismatch = bool(source_ids and product_id and product_id not in source_ids)
    identifier_missing = bool(source_ids and not product_id)

    recall_brand = norm_brand(recall.get("brand"))
    brand_match = (not recall_brand) or recall_brand == norm_brand(product.get("brand"))
    recall_packs = {norm_pack(x) for x in recall.get("pack_sizes", []) if x}
    pack_match = (not recall_packs) or norm_pack(product.get("pack_size")) in recall_packs

    identity_method = (
        "EXACT_SOURCE_IDENTIFIER"
        if identifier_match
        else "NAME_BRAND_PACK"
        if fuzzy_name_match
        else "UNRESOLVED"
    )

    base = {
        "recall_id": recall.get("recall_id"),
        "sku": product.get("sku"),
        "barcode": product.get("barcode"),
        "product_name": product.get("product_name"),
        "product_name_similarity": round(score, 1),
        "product_name_match": fuzzy_name_match,
        "product_identifier_match": identifier_match if source_ids else None,
        "product_identity_method": identity_method,
        "brand_match": brand_match,
        "pack_size_match": pack_match,
        "batch_match": None,
        "date_match": None,
        "stock": 0,
        "dispatched": 0,
        "matched_batches": [],
        "source_evidence": {
            "authority": recall.get("authority"),
            "source_url": recall.get("source_url"),
            "published_date": recall.get("published_date"),
            "source_verified": recall.get("is_public_source_verified", False),
            "source_identifiers": sorted(source_ids),
            "recall_batch_codes": list(recall.get("batch_codes") or []),
            "recall_use_by": list(recall.get("use_by") or []),
            "recall_best_before": list(recall.get("best_before") or []),
        },
    }

    if identifier_mismatch:
        return {
            **base,
            "status": "NOT_AFFECTED",
            "reason_code": "PRODUCT_IDENTIFIER_MISMATCH",
            "reason": "The recall provides a product identifier and the company product identifier is different.",
        }

    if identifier_missing and fuzzy_name_match and brand_match and pack_match:
        return {
            **base,
            "status": "POSSIBLE",
            "reason_code": "PRODUCT_IDENTIFIER_MISSING",
            "reason": "The recall provides a decisive product identifier, but the company product record does not contain it.",
        }

    product_identity_established = identifier_match or fuzzy_name_match
    if not product_identity_established:
        return {
            **base,
            "status": "INSUFFICIENT_EVIDENCE",
            "reason_code": "PRODUCT_IDENTITY_UNCLEAR",
            "reason": "Product identity cannot be established safely from the available structured evidence.",
        }

    # If an exact source identifier matches but other structured attributes
    # conflict, treat it as evidence conflict rather than silently overriding.
    if identifier_match and (not brand_match or not pack_match):
        return {
            **base,
            "status": "POSSIBLE",
            "reason_code": "PRODUCT_EVIDENCE_CONFLICT",
            "reason": "The product identifier matches, but brand or pack evidence conflicts and requires human review.",
        }

    if not brand_match or not pack_match:
        return {
            **base,
            "status": "NOT_AFFECTED",
            "reason_code": "PRODUCT_ATTRIBUTES_MISMATCH",
            "reason": "Product family is similar, but brand or pack-size evidence excludes exposure.",
        }

    product_batches = [
        b for b in batches if b.get("sku") == product.get("sku")
    ]
    recall_batches = {
        norm_batch(x) for x in recall.get("batch_codes", []) if x
    }
    recall_dates = {
        x
        for x in (
            list(recall.get("use_by") or [])
            + list(recall.get("best_before") or [])
        )
        if x
    }

    if recall_batches:
        known_company_batches = {
            norm_batch(b.get("batch_code"))
            for b in product_batches
            if b.get("batch_code")
        }
        if not known_company_batches:
            inv = inventory_records(inventory, product.get("sku"))
            disp = dispatch_records(dispatches, product.get("sku"))
            return {
                **base,
                "status": "POSSIBLE",
                "stock": total_quantity(inv),
                "dispatched": total_quantity(disp),
                "reason_code": "LOT_INFORMATION_MISSING",
                "reason": "Product identity matches, but the company record lacks the decisive lot information.",
            }

        matched = sorted(recall_batches & known_company_batches)
        if not matched:
            return {
                **base,
                "status": "NOT_AFFECTED",
                "batch_match": False,
                "reason_code": "LOT_MISMATCH",
                "reason": "Company lots are explicitly outside the affected recall lot scope.",
            }

        matched_rows = [
            b for b in product_batches
            if norm_batch(b.get("batch_code")) in set(matched)
        ]

        confirmed_batches = list(matched)
        date_match = None
        unresolved_date_batches = []

        if recall_dates:
            confirmed_batches = []
            rows_with_dates = 0
            for row in matched_rows:
                company_dates = {
                    x for x in [row.get("use_by"), row.get("best_before")] if x
                }
                batch_code = norm_batch(row.get("batch_code"))
                if not company_dates:
                    unresolved_date_batches.append(batch_code)
                    continue
                rows_with_dates += 1
                if _any_date_scope_match(company_dates, recall_dates):
                    confirmed_batches.append(batch_code)

            if not confirmed_batches:
                if rows_with_dates == 0:
                    inv = inventory_records(
                        inventory, product.get("sku"), batch_codes=matched
                    )
                    disp = dispatch_records(
                        dispatches, product.get("sku"), batch_codes=matched
                    )
                    return {
                        **base,
                        "status": "POSSIBLE",
                        "batch_match": True,
                        "date_match": None,
                        "batch": matched[0],
                        "matched_batches": matched,
                        "stock": total_quantity(inv),
                        "dispatched": total_quantity(disp),
                        "reason_code": "DATE_INFORMATION_MISSING",
                        "reason": "Affected lot identity matches, but the company date needed to resolve the recall is missing.",
                    }
                return {
                    **base,
                    "status": "NOT_AFFECTED",
                    "batch_match": True,
                    "date_match": False,
                    "matched_batches": matched,
                    "reason_code": "DATE_OUTSIDE_SCOPE",
                    "reason": "The lot matches, but company date evidence is outside the recall date scope.",
                }
            date_match = True

        inv = inventory_records(
            inventory, product.get("sku"), batch_codes=confirmed_batches
        )
        disp = dispatch_records(
            dispatches, product.get("sku"), batch_codes=confirmed_batches
        )

        return {
            **base,
            "status": "CONFIRMED",
            "batch_match": True,
            "date_match": date_match,
            "batch": confirmed_batches[0],
            "matched_batches": confirmed_batches,
            "unresolved_date_batches": unresolved_date_batches,
            "stock": total_quantity(inv),
            "dispatched": total_quantity(disp),
            "inventory_records": inv,
            "dispatch_records": disp,
            "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
            "reason": "Product identity and one or more affected lots are supported by recall and company records.",
        }

    # No recall lot. Date can narrow scope but cannot independently confirm.
    if recall_dates:
        known_dates = set()
        for b in product_batches:
            known_dates.update(
                x for x in [b.get("use_by"), b.get("best_before")] if x
            )
        if known_dates and not _any_date_scope_match(known_dates, recall_dates):
            return {
                **base,
                "status": "NOT_AFFECTED",
                "date_match": False,
                "reason_code": "DATE_OUTSIDE_SCOPE",
                "reason": "Product identity matches, but company dates are outside the recall date scope.",
            }
        inv = inventory_records(inventory, product.get("sku"))
        disp = dispatch_records(dispatches, product.get("sku"))
        return {
            **base,
            "status": "POSSIBLE",
            "date_match": (
                _any_date_scope_match(known_dates, recall_dates)
                if known_dates
                else None
            ),
            "stock": total_quantity(inv),
            "dispatched": total_quantity(disp),
            "reason_code": "LOT_SCOPE_NOT_SPECIFIED",
            "reason": "Product identity is relevant, but the recall does not specify a decisive lot. Human evidence gathering is required before confirmation.",
        }

    inv = inventory_records(inventory, product.get("sku"))
    disp = dispatch_records(dispatches, product.get("sku"))
    return {
        **base,
        "status": "POSSIBLE",
        "stock": total_quantity(inv),
        "dispatched": total_quantity(disp),
        "reason_code": "DECISIVE_CONSTRAINT_MISSING",
        "reason": "Product identity matches, but decisive recall constraints are missing.",
    }
