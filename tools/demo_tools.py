from __future__ import annotations

from .catalogue_tools import search_catalogue, get_batches
from .exposure_tools import resolve_exposure
from .inventory_tools import get_inventory
from .dispatch_tools import get_dispatches
from .supplier_tools import get_purchase_history


def resolve_company_exposure(ctx, recall_id, limit=5):
    """Resolve a recall against company product/lot evidence in one agent tool.

    The LLM autonomously selects this high-level tool. The tool then executes the
    same deterministic catalogue, batch and exposure functions used by the full
    prototype. Candidate traversal follows deterministic catalogue rank.
    """
    subtools = []
    catalogue = search_catalogue(ctx, recall_id=recall_id, limit=limit)
    subtools.append({
        "tool": "search_catalogue",
        "arguments": {"recall_id": recall_id, "limit": limit},
        "observation": catalogue,
    })
    if not catalogue.get("ok"):
        return {"ok": False, "error": catalogue.get("error", "CATALOGUE_ERROR"), "subtools": subtools}

    candidates = catalogue.get("candidates") or []
    if not candidates:
        return {
            "ok": True,
            "candidates": [],
            "active_sku": None,
            "batches": [],
            "exposure": None,
            "investigated_skus": [],
            "subtools": subtools,
        }

    investigated = []
    last = None
    for candidate in candidates:
        sku = candidate.get("sku")
        if not sku:
            continue
        batch_obs = get_batches(ctx, sku=sku)
        subtools.append({
            "tool": "get_batches",
            "arguments": {"sku": sku},
            "observation": batch_obs,
        })
        if not batch_obs.get("ok"):
            return {"ok": False, "error": batch_obs.get("error", "BATCH_ERROR"), "subtools": subtools}

        exposure_obs = resolve_exposure(ctx, recall_id=recall_id, sku=sku)
        subtools.append({
            "tool": "resolve_exposure",
            "arguments": {"recall_id": recall_id, "sku": sku},
            "observation": exposure_obs,
        })
        if not exposure_obs.get("ok"):
            return {"ok": False, "error": exposure_obs.get("error", "EXPOSURE_ERROR"), "subtools": subtools}

        investigated.append(sku)
        last = {
            "active_sku": sku,
            "batches": batch_obs.get("batches") or [],
            "exposure": exposure_obs.get("exposure"),
        }
        status = (last.get("exposure") or {}).get("status")
        if status in {"CONFIRMED", "POSSIBLE"}:
            break

    return {
        "ok": True,
        "candidates": candidates,
        "active_sku": (last or {}).get("active_sku"),
        "batches": (last or {}).get("batches") or [],
        "exposure": (last or {}).get("exposure"),
        "investigated_skus": investigated,
        "subtools": subtools,
    }


def trace_internal_evidence(ctx, sku, batch_codes):
    """Collect stock, dispatch and purchase evidence in one agent-selected tool."""
    subtools = []
    inventory = get_inventory(ctx, sku=sku, batch_codes=batch_codes)
    subtools.append({
        "tool": "get_inventory",
        "arguments": {"sku": sku, "batch_codes": batch_codes},
        "observation": inventory,
    })
    if not inventory.get("ok"):
        return {"ok": False, "error": inventory.get("error", "INVENTORY_ERROR"), "subtools": subtools}

    dispatches = get_dispatches(ctx, sku=sku, batch_codes=batch_codes)
    subtools.append({
        "tool": "get_dispatches",
        "arguments": {"sku": sku, "batch_codes": batch_codes},
        "observation": dispatches,
    })
    if not dispatches.get("ok"):
        return {"ok": False, "error": dispatches.get("error", "DISPATCH_ERROR"), "subtools": subtools}

    purchases = get_purchase_history(ctx, sku=sku, batch_codes=batch_codes)
    subtools.append({
        "tool": "get_purchase_history",
        "arguments": {"sku": sku, "batch_codes": batch_codes},
        "observation": purchases,
    })
    if not purchases.get("ok"):
        return {"ok": False, "error": purchases.get("error", "PURCHASE_ERROR"), "subtools": subtools}

    return {
        "ok": True,
        "inventory": inventory,
        "dispatches": dispatches,
        "purchase_history": purchases,
        "subtools": subtools,
    }
