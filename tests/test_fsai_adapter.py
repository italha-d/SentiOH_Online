from ingestion.fsai_adapter import normalise_rows


def test_adapter_rejects_alert_summary_labels_as_products():
    primary, review = normalise_rows([
        {
            "Recall ID": "2026.99",
            "Product Name": "Batch Code",
            "Pack Size": "use-by 01/01/2027",
            "Source URL": "https://www.fsai.ie/example",
            "Published Date": "2026-09-01",
            "Hazard": "Test",
        }
    ])
    assert primary == []
    assert review == []


def test_adapter_consolidates_updates_without_erasing_old_scope():
    rows = [
        {
            "Recall ID": "2026.88",
            "Alert Version": "Base",
            "Product Name": "Example Product",
            "Brand": "",
            "Pack Size": "100g",
            "Batch Code": "LOT1",
            "Use By": "2026-09-10",
            "Best Before": "",
            "Expiry Date": "",
            "Country of Origin": "Ireland",
            "Hazard": "Hazard",
            "Published Date": "2026-09-01",
            "Source URL": "https://www.fsai.ie/base",
            "Image URL": "",
            "Data Quality": "VERIFIED_FSAI",
            "Review Reason": "",
        },
        {
            "Recall ID": "2026.88",
            "Alert Version": "Update 1",
            "Product Name": "Example Product",
            "Brand": "",
            "Pack Size": "100g",
            "Batch Code": "LOT1",
            "Use By": "2026-09-11",
            "Best Before": "",
            "Expiry Date": "",
            "Country of Origin": "Ireland",
            "Hazard": "Hazard",
            "Published Date": "2026-09-02",
            "Source URL": "https://www.fsai.ie/update",
            "Image URL": "",
            "Data Quality": "VERIFIED_FSAI",
            "Review Reason": "",
        },
    ]

    primary, review = normalise_rows(rows)
    assert review == []
    assert len(primary) == 1
    recall = primary[0]
    assert set(recall["use_by"]) == {"2026-09-10", "2026-09-11"}
    assert recall["source_url"] == "https://www.fsai.ie/update"
    assert len(recall["source_history"]) == 2


def test_adapter_keeps_free_text_date_scope_out_of_exact_dates():
    primary, review = normalise_rows([
        {
            "Recall ID": "2026.77",
            "Alert Version": "Base",
            "Product Name": "Example Product",
            "Pack Size": "100g",
            "Batch Code": "",
            "Use By": "",
            "Best Before": "All date codes up to and including April 2027",
            "Source URL": "https://www.fsai.ie/example",
            "Published Date": "2026-09-01",
            "Hazard": "Hazard",
            "Data Quality": "VERIFIED_FSAI",
        }
    ])

    assert len(primary) == 1
    assert primary[0]["best_before"] == []
    assert primary[0]["date_scope_text"] == [
        "Best Before / Expiry: All date codes up to and including April 2027"
    ]
