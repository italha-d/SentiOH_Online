from pathlib import Path
from ingestion.load_data import load_bundle
from matching.matcher import resolve_exposure
import copy

ROOT = Path(__file__).resolve().parents[1]

def data():
    return load_bundle(ROOT/"demo_data")

def product(d,sku):
    return next(p for p in d["products"] if p["sku"]==sku)

def test_exact_product_lot_confirmed():
    d=data(); r=d["recalls"][0]
    x=resolve_exposure(r,product(d,"SKU001"),d["batches"],d["inventory"],d["dispatches"])
    assert x["status"]=="CONFIRMED"
    assert x["stock"]==41
    assert x["dispatched"]==27

def test_wrong_lot_not_affected():
    d=data(); r=copy.deepcopy(d["recalls"][0]); r["batch_codes"]=["OTHER"]
    x=resolve_exposure(r,product(d,"SKU001"),d["batches"],d["inventory"],d["dispatches"])
    assert x["status"]=="NOT_AFFECTED"
    assert x["reason_code"]=="LOT_MISMATCH"

def test_missing_company_lot_possible():
    d=data(); r=d["recalls"][0]
    batches=[b for b in d["batches"] if b["sku"]!="SKU001"]
    x=resolve_exposure(r,product(d,"SKU001"),batches,d["inventory"],d["dispatches"])
    assert x["status"]=="POSSIBLE"

def test_wrong_pack_not_affected():
    d=data(); r=copy.deepcopy(d["recalls"][0]); r["pack_sizes"]=["999g"]
    x=resolve_exposure(r,product(d,"SKU001"),d["batches"],d["inventory"],d["dispatches"])
    assert x["status"]=="NOT_AFFECTED"

def test_unrelated_insufficient():
    d=data(); r=d["recalls"][0]
    x=resolve_exposure(r,product(d,"SKU010"),d["batches"],d["inventory"],d["dispatches"])
    assert x["status"]=="INSUFFICIENT_EVIDENCE"

def test_date_outside_scope_not_affected():
    d=data(); r=copy.deepcopy(d["recalls"][0]); r["use_by"]=["2099-01-01"]
    x=resolve_exposure(r,product(d,"SKU001"),d["batches"],d["inventory"],d["dispatches"])
    assert x["status"]=="NOT_AFFECTED"
    assert x["reason_code"]=="DATE_OUTSIDE_SCOPE"

def test_fuzzy_similarity_cannot_confirm_without_lot():
    d=data(); r=copy.deepcopy(d["recalls"][0]); r["batch_codes"]=[]
    x=resolve_exposure(r,product(d,"SKU001"),d["batches"],d["inventory"],d["dispatches"])
    assert x["status"]!="CONFIRMED"
