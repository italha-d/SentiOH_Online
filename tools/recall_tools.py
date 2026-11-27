def get_recall(ctx, recall_id):
    recall = next((r for r in ctx.data["recalls"] if r.get("recall_id") == recall_id), None)
    if not recall:
        return {"ok":False,"error":"RECALL_NOT_FOUND","recall_id":recall_id}
    return {"ok":True,"recall":dict(recall)}
