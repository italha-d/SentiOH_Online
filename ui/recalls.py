from .common import get_context

def render(st):
    ctx = get_context(st)
    recalls = ctx.data["recalls"]
    st.title("Recall Inbox")
    st.dataframe([{
        "recall_id":r["recall_id"],"authority":r["authority"],
        "published":r["published_date"],"product":r["product_name"],
        "brand":r["brand"],"hazard":r["hazard"]
    } for r in recalls],use_container_width=True)
    ids = [r["recall_id"] for r in recalls]
    rid = st.selectbox("Select recall",ids)
    st.session_state["selected_recall_id"] = rid
