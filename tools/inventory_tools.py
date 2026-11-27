from matching.trace import inventory_records, total_quantity


def get_inventory(ctx, sku, batch_code=None, batch_codes=None):
    rows = inventory_records(
        ctx.data["inventory"], sku, batch_code=batch_code, batch_codes=batch_codes
    )
    return {
        "ok": True,
        "sku": sku,
        "batch_code": batch_code,
        "batch_codes": batch_codes or [],
        "total_quantity": total_quantity(rows),
        "records": rows,
    }
