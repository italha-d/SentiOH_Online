from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .audit import add_event, now_iso


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_DIR = ROOT / "audit_exports"
AUDIT_SCHEMA_VERSION = "1.0"


def audit_export_filename(case):
    return f"{case['case_id']}_audit.json"


def audit_checksum_filename(case):
    return f"{case['case_id']}_audit.sha256"


def build_audit_package(case):
    return {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "exported_at": now_iso(),
        "case": {
            "case_id": case.get("case_id"),
            "recall_id": case.get("recall_id"),
            "state": case.get("state"),
            "created_time": case.get("created_time"),
            "updated_time": case.get("updated_time"),
            "analysis_revision": case.get("analysis_revision", 1),
            "last_analysis_time": case.get("last_analysis_time"),
            "demo_profile": case.get("demo_profile"),
            "demo_only": bool(case.get("demo_only")),
            "demo_record_status": case.get("demo_record_status"),
            "demo_archived": bool(case.get("demo_archived")),
        },
        "source_recall": case.get("source_recall"),
        "exposure": case.get("exposure"),
        "resolution": case.get("resolution"),
        "closure": case.get("closure"),
        "precompleted_demo_evidence": case.get("demo_precompleted_evidence") or [],
        "demo_full_workflow_reference": case.get("demo_full_workflow_reference"),
        "demo_reset": case.get("demo_reset"),
        "demo_reset_history": case.get("demo_reset_history") or [],
        "tasks": case.get("tasks") or [],
        "reviews": case.get("reviews") or [],
        "task_history": case.get("task_history") or [],
        "review_history": case.get("review_history") or [],
        "recall_versioning": {
            "recall_version": case.get("recall_version"),
            "recall_snapshot": case.get("recall_snapshot"),
            "previous_recall_snapshot": case.get("previous_recall_snapshot"),
            "recall_change_summary": case.get("recall_change_summary"),
        },
        "local_llm_reasoning": {
            "recommendation": case.get("llm_recommendation"),
            "evidence_gap_analysis": case.get("evidence_gap_analysis"),
        },
        "audit_timeline": case.get("audit_timeline") or [],
    }


def audit_export_bytes(case):
    return (
        json.dumps(
            build_audit_package(case),
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n"
    ).encode("utf-8")



def audit_download_bytes(case):
    """
    Return the exact persisted audit export when available.

    This keeps the dashboard download byte-for-byte identical to the JSON file
    whose SHA-256 sidecar is stored under audit_exports/. If the case has not
    yet been persisted with an export, fall back to an in-memory package.
    """
    metadata = case.get("audit_export") or {}
    raw_path = metadata.get("storage_path")
    if raw_path:
        path = Path(raw_path)
        if path.exists():
            return path.read_bytes()

    return audit_export_bytes(case)

def export_case_audit(case, output_dir=None, actor="SYSTEM"):
    if case.get("state") != "CLOSED":
        raise ValueError("A portable final audit export is created only for CLOSED cases.")

    output_dir = Path(output_dir or DEFAULT_AUDIT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / audit_export_filename(case)
    checksum_path = output_dir / audit_checksum_filename(case)
    generated_time = now_iso()

    add_event(
        case,
        "AUDIT_EXPORT_GENERATED",
        actor,
        {
            "filename": json_path.name,
            "generated_time": generated_time,
        },
    )

    payload = audit_export_bytes(case)
    digest = hashlib.sha256(payload).hexdigest()

    tmp_path = json_path.with_suffix(".json.tmp")
    tmp_path.write_bytes(payload)
    tmp_path.replace(json_path)
    checksum_path.write_text(
        f"{digest}  {json_path.name}\n",
        encoding="utf-8",
    )

    case["audit_export"] = {
        "filename": json_path.name,
        "checksum_filename": checksum_path.name,
        "generated_time": generated_time,
        "sha256": digest,
        "storage_path": str(json_path),
        "checksum_path": str(checksum_path),
    }
    return case["audit_export"]


def ensure_audit_export(case, output_dir=None):
    if case.get("state") != "CLOSED":
        return None

    metadata = case.get("audit_export") or {}
    raw_path = metadata.get("storage_path")
    if metadata and raw_path and Path(raw_path).exists():
        return metadata

    return export_case_audit(
        case,
        output_dir=output_dir,
        actor="SYSTEM",
    )
