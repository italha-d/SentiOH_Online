import pytest
from workflow.workflow import open_case
from workflow.states import transition_case, close_case

def test_confirmed_case_uses_full_lifecycle_states():
    case = open_case({
        "recall_id": "R1",
        "sku": "SKU1",
        "status": "CONFIRMED",
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
        "stock": 1,
        "dispatched": 0,
    })
    assert case["state"] == "CONFIRMED"
    states = [
        e["details"].get("to")
        for e in case["audit_timeline"]
        if e["action"] == "CASE_STATE_CHANGED"
    ]
    assert "ANALYSING" in states
    assert "CONFIRMED" in states

def test_invalid_transition_is_blocked():
    case = open_case({
        "recall_id": "R1",
        "sku": "SKU1",
        "status": "CONFIRMED",
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
    })
    with pytest.raises(ValueError):
        transition_case(case, "CLOSED")

def test_resolved_case_can_close():
    case = open_case({
        "recall_id": "R1",
        "sku": "SKU1",
        "status": "CONFIRMED",
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
    })
    transition_case(case, "RESPONDING")
    transition_case(case, "RESOLVED")
    close_case(case, "Incident Lead", "Reviewed", actor_role="Recall / Incident Manager")
    assert case["state"] == "CLOSED"
