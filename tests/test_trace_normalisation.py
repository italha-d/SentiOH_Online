from matching.trace import inventory_records, dispatch_records

def test_trace_uses_same_batch_normalisation_as_matcher():
    inventory = [{
        "site_code": "S1", "site": "A", "sku": "SKU1",
        "batch_code": "SS-16726", "quantity": "4"
    }]
    dispatches = [{
        "dispatch_id": "D1", "customer": "C", "sku": "SKU1",
        "batch_code": "SS 16726", "quantity": "2", "date": "2026-01-01"
    }]
    assert len(inventory_records(inventory, "SKU1", batch_code="SS16726")) == 1
    assert len(dispatch_records(dispatches, "SKU1", batch_code="SS16726")) == 1
