from pathlib import Path
from ingestion.load_data import validate_bundle

ROOT = Path(__file__).resolve().parents[1]

def test_validator_reports_missing_values_and_schema():
    result = validate_bundle(ROOT/"demo_data")
    assert result["ok"] is True
    assert "missing_values" in result
    assert "recalls.json" in result["missing_values"]
    assert "products.csv" in result["missing_values"]
