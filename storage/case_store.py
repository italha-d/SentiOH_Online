from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
from workflow.audit_export import ensure_audit_export, DEFAULT_AUDIT_DIR

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "runtime" / "sentioh_cases.db"


class CaseStore:
    def __init__(self, path=None, audit_dir=None):
        configured_db = os.getenv("SENTIOH_DB_PATH")
        self.path = Path(path or configured_db or DEFAULT_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if audit_dir is not None:
            self.audit_dir = Path(audit_dir)
        elif os.getenv("SENTIOH_AUDIT_DIR"):
            self.audit_dir = Path(os.environ["SENTIOH_AUDIT_DIR"])
        elif configured_db and path is None:
            self.audit_dir = self.path.parent / "audit_exports"
        elif path is None:
            self.audit_dir = DEFAULT_AUDIT_DIR
        else:
            self.audit_dir = self.path.parent / "audit_exports"

        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init_db()

    def _prepare_case_for_persistence(self, case):
        if case.get("state") == "CLOSED":
            ensure_audit_export(
                case,
                output_dir=self.audit_dir,
            )
        return case

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _init_db(self):
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    recall_id TEXT,
                    updated_time TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def load_cases(self):
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT case_id, payload FROM cases ORDER BY updated_time DESC"
            ).fetchall()
        return {
            case_id: json.loads(payload)
            for case_id, payload in rows
        }

    def save_case(self, case):
        case = self._prepare_case_for_persistence(case)
        payload = json.dumps(case, sort_keys=True, default=str)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cases(case_id, recall_id, updated_time, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    recall_id=excluded.recall_id,
                    updated_time=excluded.updated_time,
                    payload=excluded.payload
                """,
                (
                    case["case_id"],
                    case.get("recall_id"),
                    case.get("updated_time") or case.get("created_time") or "",
                    payload,
                ),
            )
            conn.commit()

    def save_cases(self, cases):
        for case in cases.values():
            self.save_case(case)

    def mutate_case(self, case_id, mutator):
        """
        Atomically reload and mutate one case under a SQLite write lock.

        This prevents a dual-approval decision from being lost if two
        authenticated users act from different browser sessions.
        """
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT payload FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise KeyError(f"Case not found: {case_id}")

            case = json.loads(row[0])
            result = mutator(case)
            case_to_save = result if isinstance(result, dict) else case
            case_to_save = self._prepare_case_for_persistence(case_to_save)
            payload = json.dumps(case_to_save, sort_keys=True, default=str)
            conn.execute(
                """
                UPDATE cases
                SET recall_id = ?, updated_time = ?, payload = ?
                WHERE case_id = ?
                """,
                (
                    case_to_save.get("recall_id"),
                    case_to_save.get("updated_time")
                    or case_to_save.get("created_time")
                    or "",
                    payload,
                    case_id,
                ),
            )
            conn.commit()
            return case_to_save

    def clear(self):
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM cases")
            conn.commit()

        # "Reset shared demo" is intentionally destructive. Remove portable
        # audit artefacts created by the demo as well so a fresh demonstration
        # does not leave stale closed-case files behind.
        if self.audit_dir.exists():
            for pattern in ("CASE-*_audit.json", "CASE-*_audit.sha256"):
                for path in self.audit_dir.glob(pattern):
                    path.unlink(missing_ok=True)
