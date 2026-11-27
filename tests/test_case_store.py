from storage.case_store import CaseStore


def test_case_store_shares_case_state_between_instances(tmp_path):
    db = tmp_path / "cases.db"
    first = CaseStore(db)
    second = CaseStore(db)

    case = {
        "case_id": "CASE-DB1",
        "recall_id": "R1",
        "state": "RESPONDING",
        "updated_time": "2026-09-04T12:00:00+00:00",
        "tasks": [],
    }
    first.save_case(case)

    loaded = second.load_cases()
    assert loaded["CASE-DB1"]["state"] == "RESPONDING"

    loaded["CASE-DB1"]["state"] = "RESOLVED"
    second.save_case(loaded["CASE-DB1"])

    assert first.load_cases()["CASE-DB1"]["state"] == "RESOLVED"


def test_case_store_clear_removes_shared_cases(tmp_path):
    store = CaseStore(tmp_path / "cases.db")
    store.save_case({
        "case_id": "CASE-X",
        "recall_id": "R1",
        "state": "RESPONDING",
        "tasks": [],
    })
    assert store.load_cases()
    store.clear()
    assert store.load_cases() == {}


def test_case_store_uses_configured_render_paths(tmp_path, monkeypatch):
    db_path = tmp_path / "render-cases.db"
    audit_path = tmp_path / "render-audit"
    monkeypatch.setenv("SENTIOH_DB_PATH", str(db_path))
    monkeypatch.setenv("SENTIOH_AUDIT_DIR", str(audit_path))

    store = CaseStore()

    assert store.path == db_path
    assert store.audit_dir == audit_path
    assert db_path.exists()
    assert audit_path.is_dir()


from workflow.workflow import open_case
from workflow.approvals import approve_task
from workflow.roles import QUALITY_FOOD_SAFETY_MANAGER, RECALL_INCIDENT_MANAGER


def test_atomic_mutations_preserve_dual_approvals(tmp_path):
    store = CaseStore(tmp_path / "cases.db")
    case = open_case({
        "recall_id": "R-DUAL",
        "sku": "SKU1",
        "product_name": "Demo",
        "status": "CONFIRMED",
        "batch": "LOT1",
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
        "stock": 2,
        "dispatched": 1,
    })
    store.save_case(case)
    task_id = next(
        task["task_id"]
        for task in case["tasks"]
        if task["title"] == "Prepare customer communication draft"
    )

    def quality(latest):
        approve_task(
            latest, task_id, "Food Safety Lead", "Checked",
            approver_role=QUALITY_FOOD_SAFETY_MANAGER,
        )
        return latest

    def incident(latest):
        approve_task(
            latest, task_id, "Incident Lead", "Checked",
            approver_role=RECALL_INCIDENT_MANAGER,
        )
        return latest

    store.mutate_case(case["case_id"], quality)
    store.mutate_case(case["case_id"], incident)

    final = store.load_cases()[case["case_id"]]
    task = next(t for t in final["tasks"] if t["task_id"] == task_id)
    assert task["status"] == "APPROVED"
    assert {
        item["approver_role"] for item in task["approvals"]
        if item["decision"] == "APPROVED"
    } == {QUALITY_FOOD_SAFETY_MANAGER, RECALL_INCIDENT_MANAGER}
