from matching.normalise import norm_batch


def _batch_allowed(row_batch, batch_code=None, batch_codes=None):
    if batch_codes:
        allowed = {norm_batch(x) for x in batch_codes if x is not None}
        return norm_batch(row_batch) in allowed
    if batch_code is not None:
        return norm_batch(row_batch) == norm_batch(batch_code)
    return True


def get_purchase_history(ctx, sku, batch_code=None, batch_codes=None):
    rows = []
    for po in ctx.data["purchase_orders"]:
        if po.get("sku") != sku:
            continue
        if not _batch_allowed(po.get("batch_code"), batch_code, batch_codes):
            continue
        row = dict(po)
        sup = next(
            (
                s for s in ctx.data["suppliers"]
                if s.get("supplier_id") == po.get("supplier_id")
            ),
            None,
        )
        row["supplier_name"] = sup.get("supplier_name") if sup else None
        row["supplier_country"] = sup.get("country") if sup else None
        rows.append(row)

    return {
        "ok": True,
        "sku": sku,
        "batch_code": batch_code,
        "batch_codes": batch_codes or [],
        "records": rows,
    }
