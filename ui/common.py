from pathlib import Path
from ingestion.load_data import load_bundle
from tools.context import ToolContext
from storage.case_store import CaseStore

ROOT = Path(__file__).resolve().parents[1]
_STORE = CaseStore()


def _deduplicate_cases_by_recall(cases):
    if not cases:
        return cases

    latest = {}
    for case_id, case in cases.items():
        recall_id = case.get("recall_id") or case_id
        sort_key = case.get("updated_time") or case.get("created_time") or ""
        current = latest.get(recall_id)
        if current is None or sort_key >= current[0]:
            latest[recall_id] = (sort_key, case_id)

    keep = {case_id for _, case_id in latest.values()}
    for case_id in list(cases.keys()):
        if case_id not in keep:
            del cases[case_id]
    return cases


def get_data():
    return load_bundle(ROOT / "demo_data")


def get_context(st):
    # Cases are loaded from a shared SQLite store on every Streamlit rerun so
    # approvals recorded by one authenticated user become visible to others.
    cases = _STORE.load_cases()
    _deduplicate_cases_by_recall(cases)
    st.session_state["cases"] = cases

    if "data" not in st.session_state:
        st.session_state["data"] = get_data()

    return ToolContext(
        data=st.session_state["data"],
        cases=cases,
        case_store=_STORE,
    )
