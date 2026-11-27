from __future__ import annotations
import re


def norm_text(v):
    v = (v or "").strip().lower()
    v = re.sub(r"[\s\-_]+", " ", v)
    v = re.sub(r"[^\w\s.%]", "", v)
    return v.strip()


def norm_brand(v):
    return norm_text(v)


def norm_batch(v):
    return re.sub(r"[^A-Za-z0-9]", "", v or "").upper()


def norm_identifier(v):
    """Normalise company/product identifiers without inventing or validating them."""
    return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()


def norm_pack(v):
    v = norm_text(v).replace(" ", "")
    replacements = {
        "grams": "g",
        "gram": "g",
        "kilograms": "kg",
        "kilogram": "kg",
        "millilitres": "ml",
        "millilitre": "ml",
        "litres": "l",
        "litre": "l",
    }
    for a, b in replacements.items():
        v = v.replace(a, b)
    return v


def recall_identifiers(recall):
    """
    Return source-side GTIN/EAN/barcode values only when explicitly present.
    Internal company SKU values are deliberately not treated as recall fields.
    """
    values = []
    for key in ("gtins", "barcodes"):
        raw = recall.get(key)
        if isinstance(raw, list):
            values.extend(raw)
    for key in ("gtin", "barcode"):
        raw = recall.get(key)
        if raw:
            values.append(raw)
    return {norm_identifier(v) for v in values if norm_identifier(v)}
