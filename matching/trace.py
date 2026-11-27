from .normalise import norm_batch


def _qty(v):
    try:
        return int(float(v))
    except Exception:
        return 0


def _batch_allowed(row_batch, batch_code=None, batch_codes=None):
    if batch_codes:
        allowed = {norm_batch(x) for x in batch_codes if x is not None}
        return norm_batch(row_batch) in allowed
    if batch_code is not None:
        return norm_batch(row_batch) == norm_batch(batch_code)
    return True


def inventory_records(inventory, sku, batch_code=None, batch_codes=None):
    out = []
    for row in inventory:
        if row.get("sku") != sku:
            continue
        if not _batch_allowed(row.get("batch_code"), batch_code, batch_codes):
            continue
        out.append(dict(row))
    return out


def dispatch_records(dispatches, sku, batch_code=None, batch_codes=None):
    out = []
    for row in dispatches:
        if row.get("sku") != sku:
            continue
        if not _batch_allowed(row.get("batch_code"), batch_code, batch_codes):
            continue
        out.append(dict(row))
    return out


def total_quantity(rows):
    return sum(_qty(r.get("quantity")) for r in rows)
