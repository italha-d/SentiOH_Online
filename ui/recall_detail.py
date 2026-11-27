from .common import get_context

def render(st):
    ctx = get_context(st)
    ids = [r["recall_id"] for r in ctx.data["recalls"]]
    default = st.session_state.get("selected_recall_id",ids[0])
    rid = st.selectbox("Recall",ids,index=ids.index(default) if default in ids else 0)
    st.session_state["selected_recall_id"] = rid
    r = next(x for x in ctx.data["recalls"] if x["recall_id"] == rid)
    st.title("Recall Detail")
    st.subheader("Recall-side evidence")
    st.json({k:r.get(k) for k in [
        "recall_id","authority","product_name","brand","pack_sizes","batch_codes",
        "use_by","best_before","hazard","published_date","source_url"
    ]})
    if not r.get("is_public_source_verified"):
        st.warning("Demo placeholder: this recall has not been manually verified against a real FSAI source.")
