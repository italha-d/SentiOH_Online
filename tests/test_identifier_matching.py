from matching.matcher import search_catalogue, resolve_exposure

PRODUCT = {
    "sku": "SKU-X",
    "barcode": "1234567890123",
    "product_name": "Completely Different Display Name",
    "brand": "Demo Brand",
    "pack_size": "100g",
    "supplier_id": "SUP-X",
}

RECALL = {
    "recall_id": "R-ID",
    "product_name": "Source Product",
    "brand": "Demo Brand",
    "pack_sizes": ["100 g"],
    "batch_codes": ["LOT-1"],
    "use_by": [],
    "best_before": [],
    "gtins": ["1234567890123"],
}


def test_exact_source_identifier_is_ranked_as_candidate():
    candidates = search_catalogue(RECALL, [PRODUCT])
    assert candidates[0]["identifier_match"] is True
    assert candidates[0]["candidate_basis"] == "EXACT_SOURCE_IDENTIFIER"


def test_identifier_can_establish_product_identity_but_lot_stays_deterministic():
    batches = [{
        "batch_id": "B1",
        "sku": "SKU-X",
        "batch_code": "LOT1",
        "use_by": "",
        "best_before": "",
    }]
    inventory = [{
        "site_code": "S1",
        "site": "Site 1",
        "sku": "SKU-X",
        "batch_code": "LOT-1",
        "quantity": "5",
    }]
    result = resolve_exposure(RECALL, PRODUCT, batches, inventory, [])
    assert result["status"] == "CONFIRMED"
    assert result["product_identifier_match"] is True
    assert result["batch_match"] is True
    assert result["stock"] == 5
