from .common import get_context
from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner, OpenAICompatibleJSONPlanner
from matching.matcher import search_catalogue, resolve_exposure

def _planner_from_env(st):
    import os
    mode = os.getenv("SENTIOH_PLANNER","llm").strip().lower()
    if mode == "llm":
        try:
            return OpenAICompatibleJSONPlanner()
        except Exception as e:
            st.warning(f"Online LLM planner configuration is incomplete; using offline bounded planner. {e}")
    return RulePlanner()

def _event_rows(state):
    rows = []
    for e in state.events:
        rows.append({
            "step":e.step,
            "time":e.time,
            "event":e.event_type,
            "summary":e.summary,
            "tool":e.tool or ""
        })
    return rows

def _evidence_rows(state):
    ex = state.exposure or {}
    return [
        {"dimension":"Product identity","status":"Complete" if ex.get("product_name_match") else "Missing/uncertain"},
        {"dimension":"Brand","status":"Complete" if ex.get("brand_match") else "Mismatch/unknown"},
        {"dimension":"Pack size","status":"Complete" if ex.get("pack_size_match") else "Mismatch/unknown"},
        {"dimension":"Batch/lot","status":"Complete" if ex.get("batch_match") is True else ("Missing" if ex.get("batch_match") is None else "Mismatch")},
        {"dimension":"Date scope","status":"Complete" if ex.get("date_match") is True else ("Not decisive/unknown" if ex.get("date_match") is None else "Mismatch")},
        {"dimension":"Inventory","status":"Complete" if state.inventory is not None else "Not retrieved"},
        {"dimension":"Dispatch trace","status":"Complete" if state.dispatches is not None else "Not retrieved"},
        {"dimension":"Supplier trace","status":"Complete" if state.purchase_history is not None else "Not retrieved"},
    ]

def _render_graph(st,state):
    if not state.exposure:
        return
    ex = state.exposure
    recall = state.recall or {}
    batch = ex.get("batch") or "UNRESOLVED"
    dot = ["digraph G {","rankdir=LR;","node [shape=box, style=rounded];"]
    dot += [
        f'recall [label="{recall.get("authority","Recall")}\\n{recall.get("product_name","")}"];',
        f'product [label="{ex.get("sku","")}\\n{ex.get("product_name","")}"];',
        f'batch [label="Lot/Batch\\n{batch}"];',
        f'stock [label="Remaining stock\\n{(state.inventory or {}).get("total_quantity",ex.get("stock",0))} units"];',
        f'dispatch [label="Dispatched\\n{(state.dispatches or {}).get("total_dispatched",ex.get("dispatched",0))} units"];',
        "recall -> product;","product -> batch;","batch -> stock;","batch -> dispatch;"
    ]
    for i,row in enumerate((state.dispatches or {}).get("records",[])):
        label = str(row.get("customer","Customer")).replace('"',"'")
        dot += [f'cust{i} [label="{label}\\n{row.get("quantity",0)} units"];',f'dispatch -> cust{i};']
    dot.append("}")
    st.graphviz_chart("\n".join(dot),use_container_width=True)

def render(st):
    ctx = get_context(st)
    ids = [r["recall_id"] for r in ctx.data["recalls"]]
    default = st.session_state.get("selected_recall_id",ids[0])
    rid = st.selectbox("Recall to investigate",ids,index=ids.index(default) if default in ids else 0)
    st.session_state["selected_recall_id"] = rid
    st.title("Agent Investigation")

    planner = _planner_from_env(st)
    st.caption(f"Planner: {planner.name}. Deterministic exposure resolution and approval policy remain outside the planner.")

    c1,c2 = st.columns(2)
    run_clicked = c1.button("Run end-to-end investigation",type="primary")
    step_clicked = c2.button("Run one agent step")

    key = f"investigation_{rid}"
    if run_clicked:
        agent = SentiOHAgent(ctx,planner)
        state = agent.run(rid)
        st.session_state[key] = state
        if state.case_id:
            st.session_state["active_case_id"] = state.case_id

    if step_clicked:
        state = st.session_state.get(key)
        if state is None or state.status != "ACTIVE":
            from agent.state import InvestigationState
            state = InvestigationState(recall_id=rid)
            state.log("START","Investigation started.")
        agent = SentiOHAgent(ctx,planner)
        agent.step(state)
        st.session_state[key] = state
        if state.case_id:
            st.session_state["active_case_id"] = state.case_id

    state = st.session_state.get(key)
    if not state:
        st.info("Start the investigation to watch the bounded agent choose tools, collect evidence and stop at the human approval boundary.")
        return

    a,b,c,d = st.columns(4)
    a.metric("Investigation",state.investigation_id)
    b.metric("Status",state.status)
    c.metric("Agent steps",state.step)
    d.metric("Exposure",(state.exposure or {}).get("status","Pending"))

    st.subheader("Investigation timeline")
    st.dataframe(_event_rows(state),use_container_width=True)

    if state.exposure:
        st.subheader("Deterministic exposure result")
        st.write(f"**{state.exposure['status']}**: {state.exposure['reason']}")
        st.code(state.exposure["reason_code"])
        if state.missing_evidence:
            st.warning("Missing evidence: " + "; ".join(state.missing_evidence))

    st.subheader("Evidence completeness")
    st.dataframe(_evidence_rows(state),use_container_width=True,hide_index=True)

    if state.inventory or state.dispatches:
        x,y,z = st.columns(3)
        x.metric("Remaining stock",(state.inventory or {}).get("total_quantity",0))
        y.metric("Dispatched",(state.dispatches or {}).get("total_dispatched",0))
        z.metric("Response case",state.case_id or "Not created")

    st.subheader("Exposure graph")
    _render_graph(st,state)

    with st.expander("Raw agent state"):
        st.json(state.as_dict())
