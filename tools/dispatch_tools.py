from matching.trace import dispatch_records, total_quantity


def get_dispatches(ctx, sku, batch_code=None, batch_codes=None):
    rows = dispatch_records(
        ctx.data["dispatches"], sku, batch_code=batch_code, batch_codes=batch_codes
    )
    return {
        "ok": True,
        "sku": sku,
        "batch_code": batch_code,
        "batch_codes": batch_codes or [],
        "total_dispatched": total_quantity(rows),
        "records": rows,
    }
