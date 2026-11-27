from difflib import SequenceMatcher
try:
    from rapidfuzz.fuzz import ratio as _ratio
except Exception:
    _ratio = None

def similarity(a, b):
    if not a or not b:
        return 0.0
    if _ratio:
        return float(_ratio(a,b))
    return 100.0 * SequenceMatcher(None,a,b).ratio()
