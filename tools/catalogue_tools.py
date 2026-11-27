from matching.matcher import search_catalogue as _search

def search_catalogue(ctx, recall_id, limit=5):
    recall = next(r for r in ctx.data["recalls"] if r["recall_id"] == recall_id)
    return {"ok":True,"candidates":_search(recall,ctx.data["products"],limit=limit)}

def get_batches(ctx, sku):
    rows = [dict(x) for x in ctx.data["batches"] if x.get("sku") == sku]
    return {"ok":True,"sku":sku,"batches":rows}
