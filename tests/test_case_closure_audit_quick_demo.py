from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ingestion.load_data import load_bundle
from storage.case_store import CaseStore
from tools.context import ToolContext
from workflow.approvals import approve_task
from workflow.audit_export import audit_download_bytes
from workflow.quick_demo import (
    QUICK_CLOSE_PROFILE,
    create_quick_close_demo_case,
)
from workflow.roles import (
    RECALL_INCIDENT_MANAGER,
    STORE_SITE_MANAGER,
    WAREHOUSE_MANAGER,
)
from workflow.states import close_case
from workflow.workflow import open_case
from workflow.approvals import complete_task
from workflow.reviews import mark_reviewed


ROOT = Path(__file__).resolve().parents[1]


def test_possible_case_can_resolve_without_changing_exposure_classification():
    case = open_case({
        "recall_id": "FSAI_POSSIBLE_RESOLUTION_TEST",
        "sku": "SKU-POSSIBLE",
        "product_name": "Possible Product",
        "status": "POSSIBLE",
        "batch": None,
        "matched_batches": [],
        "reason_code": "LOT_INFORMATION_MISSING",
        "stock": 10,
        "dispatched": 2,
    })

    for task in list(case["tasks"]):
        complete_task(
            case,
            task["task_id"],
            actor=f"Operator for {task['assigned_to']}",
        )

    assert case["state"] == "REVIEW_REQUIRED"

    for review in list(case["reviews"]):
        mark_reviewed(
            case,
            review["review_id"],
            reviewer="Quality reviewer",
            reviewer_role=review["assigned_role"],
            comment="Evidence cycle reviewed.",
        )

    assert case["state"] == "RESOLVED"
    assert case["exposure"]["status"] == "POSSIBLE"
    assert case["resolution"]["resolution_type"] == "POSSIBLE_EVIDENCE_CYCLE_COMPLETE"
    assert case["resolution"]["reanalysis_if_new_evidence"] is True


def test_quick_close_demo_has_exactly_two_approval_tasks_and_genuine_fsai_source(tmp_path):
    data = load_bundle(ROOT / "demo_data")
    store = CaseStore(
        path=tmp_path / "cases.db",
        audit_dir=tmp_path / "audit_exports",
    )
    ctx = ToolContext(
        data=data,
        cases={},
        case_store=store,
    )

    case = create_quick_close_demo_case(ctx)

    assert case["demo_only"] is True
    assert case["demo_profile"] == QUICK_CLOSE_PROFILE
    assert case["source_recall"]["official_recall_id"] == "2026.38"
    assert str(case["source_recall"]["source_url"]).startswith("https://www.fsai.ie/")
    assert case["exposure"]["status"] == "CONFIRMED"
    assert case["state"] == "RESPONDING"
    assert len(case["tasks"]) == 2
    assert len(case["reviews"]) == 0
    assert all(task["requires_approval"] for task in case["tasks"])
    assert all(task["approval_only"] for task in case["tasks"])
    assert {
        role
        for task in case["tasks"]
        for role in task["approval_roles"]
    } == {
        STORE_SITE_MANAGER,
        RECALL_INCIDENT_MANAGER,
    }


def test_quick_close_demo_resolves_after_two_role_approvals(tmp_path):
    data = load_bundle(ROOT / "demo_data")
    store = CaseStore(
        path=tmp_path / "cases.db",
        audit_dir=tmp_path / "audit_exports",
    )
    ctx = ToolContext(
        data=data,
        cases={},
        case_store=store,
    )
    case = create_quick_close_demo_case(ctx)

    warehouse_task = next(
        task
        for task in case["tasks"]
        if STORE_SITE_MANAGER in task["approval_roles"]
    )
    assert warehouse_task["assigned_username"] == "site.manager"
    assert warehouse_task["affected_site_code"] == "DUB"
    incident_task = next(
        task
        for task in case["tasks"]
        if RECALL_INCIDENT_MANAGER in task["approval_roles"]
    )

    def first_approval(latest):
        approve_task(
            latest,
            warehouse_task["task_id"],
            "Dublin Site Manager",
            "Containment evidence approved.",
            approver_role=STORE_SITE_MANAGER,
            approver_username="site.manager",
        )
        return latest

    case = ctx.mutate_case(case["case_id"], first_approval)
    assert case["state"] == "RESPONDING"
    assert next(
        task
        for task in case["tasks"]
        if task["task_id"] == warehouse_task["task_id"]
    )["status"] == "COMPLETED"

    def second_approval(latest):
        approve_task(
            latest,
            incident_task["task_id"],
            "Incident Manager Demo",
            "Response package approved.",
            approver_role=RECALL_INCIDENT_MANAGER,
        )
        return latest

    case = ctx.mutate_case(case["case_id"], second_approval)

    assert case["state"] == "RESOLVED"
    assert all(task["status"] == "COMPLETED" for task in case["tasks"])
    assert case["resolution"]["resolution_type"] == "CONFIRMED_RESPONSE_COMPLETE"


def test_closing_case_creates_portable_json_audit_and_sha256(tmp_path):
    data = load_bundle(ROOT / "demo_data")
    audit_dir = tmp_path / "audit_exports"
    store = CaseStore(
        path=tmp_path / "cases.db",
        audit_dir=audit_dir,
    )
    ctx = ToolContext(
        data=data,
        cases={},
        case_store=store,
    )
    case = create_quick_close_demo_case(ctx)

    approval_steps = [
        (STORE_SITE_MANAGER, "site.manager", "Dublin Site Manager"),
        (RECALL_INCIDENT_MANAGER, "incident.manager", "Incident Manager Demo"),
    ]
    for role, username, actor in approval_steps:
        current = ctx.cases[case["case_id"]]
        task = next(
            task
            for task in current["tasks"]
            if role in task["approval_roles"]
            and task["status"] == "WAITING_FOR_APPROVAL"
        )

        def approve(latest, task_id=task["task_id"], approval_role=role, username=username, actor=actor):
            approve_task(
                latest,
                task_id,
                actor,
                "Approved for quick closure demonstration.",
                approver_role=approval_role,
                approver_username=username,
            )
            return latest

        ctx.mutate_case(case["case_id"], approve)

    assert ctx.cases[case["case_id"]]["state"] == "RESOLVED"

    def close(latest):
        close_case(
            latest,
            actor="Incident Manager Demo",
            actor_role=RECALL_INCIDENT_MANAGER,
            comment="All demo closure evidence reviewed.",
        )
        return latest

    closed = ctx.mutate_case(case["case_id"], close)

    assert closed["state"] == "CLOSED"
    assert closed["closure"]["closed_by_role"] == RECALL_INCIDENT_MANAGER

    metadata = closed["audit_export"]
    json_path = Path(metadata["storage_path"])
    sha_path = Path(metadata["checksum_path"])

    assert json_path.exists()
    assert sha_path.exists()

    exact_bytes = json_path.read_bytes()
    digest = hashlib.sha256(exact_bytes).hexdigest()

    assert digest == metadata["sha256"]
    assert digest in sha_path.read_text(encoding="utf-8")
    assert audit_download_bytes(closed) == exact_bytes

    package = json.loads(exact_bytes.decode("utf-8"))
    assert package["case"]["case_id"] == closed["case_id"]
    assert package["case"]["state"] == "CLOSED"
    assert package["closure"]["closed_by_role"] == RECALL_INCIDENT_MANAGER
    assert package["exposure"]["status"] == "CONFIRMED"
    assert len(package["tasks"]) == 2
    assert any(
        event["action"] == "AUDIT_EXPORT_GENERATED"
        for event in package["audit_timeline"]
    )


def test_dashboard_has_full_feature_and_live_demo_views_with_closed_audit_controls():
    source = (
        ROOT / "ui" / "single_dashboard.py"
    ).read_text(encoding="utf-8")

    assert 'FULL_FEATURE_MODE = "Official FSAI (Full Feature Prototype)"' in source
    assert 'LIVE_DEMO_MODE = "Live Demo (Prepared FSAI Case)"' in source
    assert '"Synthetic fallback / tests"' not in source
    assert '"All"],' not in source
    assert "DEMO {showcase[item_id]['expected_status']}" in source

    assert '"Run investigation"' in source
    assert "streamline_existing_confirmed_case_for_demo" in source
    assert 'st.tabs(["Live Demo", "Official FSAI"])' in source
    assert "first_user = first_task.get(\"assigned_username\")" in source
    assert "INCIDENT MANAGER FINAL ACTION" in source
    assert "CASE CLOSED ✓" in source
    assert "Download Complete Audit Record" in source
    assert "Closed Case Archive" in source
    assert "audit_exports/" in source

