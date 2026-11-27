from matching.matcher import resolve_exposure as _resolve

def resolve_exposure(ctx, recall_id, sku):
    recall = next((r for r in ctx.data["recalls"] if r["recall_id"] == recall_id), None)
    product = next((p for p in ctx.data["products"] if p["sku"] == sku), None)
    if not recall or not product:
        return {"ok":False,"error":"RECALL_OR_PRODUCT_NOT_FOUND"}
    result = _resolve(recall,product,ctx.data["batches"],ctx.data["inventory"],ctx.data["dispatches"])
    return {"ok":True,"exposure":result}
