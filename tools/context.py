from dataclasses import dataclass
from typing import Any


@dataclass
class ToolContext:
    data: dict
    cases: dict
    case_store: Any = None

    def save_case(self, case):
        if self.case_store is not None:
            self.case_store.save_case(case)

    def save_cases(self):
        if self.case_store is not None:
            self.case_store.save_cases(self.cases)

    def mutate_case(self, case_id, mutator):
        if self.case_store is None:
            case = self.cases[case_id]
            result = mutator(case)
            return result if isinstance(result, dict) else case
        updated = self.case_store.mutate_case(case_id, mutator)
        self.cases[case_id] = updated
        return updated


    def archive_case_for_audit(
        self,
        case_id,
        *,
        actor="SYSTEM",
        actor_role=None,
        reason="Reset / deleted from the active Live Demo while retained for audit.",
    ):
        """Soft-delete a case from the active demo while preserving its audit record.

        The case remains in SQLite and in ``cases``. A reset marker is appended
        so the UI can hide it from the active workflow and show it separately as
        a retained Reset / Deleted audit record.
        """
        from workflow.audit import add_event, now_iso

        def _archive(case):
            reset_time = now_iso()
            previous_state = case.get("state")
            previous_exposure = (case.get("exposure") or {}).get("status")
            record = {
                "reset_time": reset_time,
                "reset_by": actor,
                "reset_by_role": actor_role,
                "reason": reason,
                "previous_state": previous_state,
                "previous_exposure_status": previous_exposure,
            }
            case["demo_record_status"] = "RESET_DELETED_RETAINED_FOR_AUDIT"
            case["demo_archived"] = True
            case["demo_reset"] = record
            case.setdefault("demo_reset_history", []).append(record)
            case["updated_time"] = reset_time
            add_event(
                case,
                "LIVE_DEMO_RESET_ARCHIVED",
                actor,
                {
                    **record,
                    "record_status": case["demo_record_status"],
                    "retained_for_audit": True,
                },
            )
            # A CLOSED case may already have a portable export. Invalidate the
            # metadata so CaseStore regenerates it with this reset event included.
            if previous_state == "CLOSED":
                case.pop("audit_export", None)
            return case

        return self.mutate_case(case_id, _archive)

    def clear_cases(self):
        self.cases.clear()
        if self.case_store is not None:
            self.case_store.clear()
