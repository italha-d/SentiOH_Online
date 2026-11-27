from .common import get_context
from matching.matcher import search_catalogue, resolve_exposure

def render(st):
    ctx = get_context(st)
    data = ctx.data
    confirmed = possible = 0
    for recall in data["recalls"]:
        candidates = search_catalogue(recall,data["products"],limit=3)
        for c in candidates:
            p = next(x for x in data["products"] if x["sku"] == c["sku"])
            result = resolve_exposure(recall,p,data["batches"],data["inventory"],data["dispatches"])
            confirmed += result["status"] == "CONFIRMED"
            possible += result["status"] == "POSSIBLE"
    awaiting = sum(
        1 for case in ctx.cases.values()
        for task in case["tasks"] if task["status"] == "WAITING_FOR_APPROVAL"
    )

    st.title("SentiOH")
    st.caption("From food-safety alert to evidence-backed action")
    c1,c2,c3 = st.columns(3)
    c1.metric("Products monitored",len(data["products"]))
    c2.metric("Batch records",len(data["batches"]))
    c3.metric("Active recalls",len(data["recalls"]))
    c4,c5,c6 = st.columns(3)
    c4.metric("Confirmed exposures",confirmed)
    c5.metric("Possible exposures",possible)
    c6.metric("Actions awaiting approval",awaiting)
    st.info("Offline Demo Mode is enabled. The company-side records are sandbox data and the bundled recall records are placeholders, not verified FSAI claims.")
