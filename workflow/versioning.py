import hashlib
import json

from .audit import add_event
from .states import transition_case


TRACKED_RECALL_FIELDS = [
    "product_name",
    "brand",
    "pack_sizes",
    "batch_codes",
    "use_by",
    "best_before",
    "hazard",
    "gtins",
    "barcodes",
]


def recall_snapshot(recall):
    return {
        key: recall.get(key)
        for key in TRACKED_RECALL_FIELDS
    }


def fingerprint(recall):
    return hashlib.sha256(
        json.dumps(
            recall_snapshot(recall),
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()[:16]


def recall_diff(previous, current):
    previous = previous or {}
    current = current or {}
    changed_fields = [
        field
        for field in TRACKED_RECALL_FIELDS
        if previous.get(field) != current.get(field)
    ]
    return {
        "changed_fields": changed_fields,
        "before": {
            field: previous.get(field)
            for field in changed_fields
        },
        "after": {
            field: current.get(field)
            for field in changed_fields
        },
    }


def register_recall_version(case, recall):
    fp = fingerprint(recall)
    current_snapshot = recall_snapshot(recall)

    if case.get("recall_version") is None:
        case["recall_version"] = fp
        case["recall_snapshot"] = current_snapshot
        case["recall_change_summary"] = None
        add_event(
            case,
            "RECALL_VERSION_REGISTERED",
            "SYSTEM",
            {"fingerprint": fp},
        )
        return False

    if case["recall_version"] != fp:
        old_fp = case["recall_version"]
        previous_snapshot = case.get("recall_snapshot") or {}
        change_summary = recall_diff(
            previous_snapshot,
            current_snapshot,
        )

        case["previous_recall_snapshot"] = previous_snapshot
        case["recall_snapshot"] = current_snapshot
        case["recall_change_summary"] = change_summary
        case["recall_version"] = fp
        case["needs_reanalysis"] = True

        if case.get("state") != "ANALYSING":
            transition_case(
                case,
                "ANALYSING",
                "SYSTEM",
                {
                    "reason": "Recall evidence changed",
                    "changed_fields": change_summary["changed_fields"],
                },
            )

        add_event(
            case,
            "RECALL_UPDATED_REANALYSIS_REQUIRED",
            "SYSTEM",
            {
                "old_fingerprint": old_fp,
                "new_fingerprint": fp,
                "changed_fields": change_summary["changed_fields"],
                "before": change_summary["before"],
                "after": change_summary["after"],
            },
        )
        return True

    # Upgrade older persisted cases that have a fingerprint but not a snapshot.
    case.setdefault("recall_snapshot", current_snapshot)
    return False
