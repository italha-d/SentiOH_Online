from .recall_tools import get_recall
from .catalogue_tools import search_catalogue, get_batches
from .exposure_tools import resolve_exposure
from .inventory_tools import get_inventory
from .dispatch_tools import get_dispatches
from .supplier_tools import get_purchase_history
from .workflow_tools import open_response_case, request_human_approval
from .demo_tools import resolve_company_exposure, trace_internal_evidence

TOOLS = {
    "get_recall": get_recall,
    "search_catalogue": search_catalogue,
    "get_batches": get_batches,
    "resolve_exposure": resolve_exposure,
    "get_inventory": get_inventory,
    "get_dispatches": get_dispatches,
    "get_purchase_history": get_purchase_history,
    "open_response_case": open_response_case,
    "request_human_approval": request_human_approval,
    "resolve_company_exposure": resolve_company_exposure,
    "trace_internal_evidence": trace_internal_evidence,
}

TOOL_DESCRIPTIONS = {
    "get_recall": "Load one recall record by recall_id.",
    "search_catalogue": "Return candidate company products for a recall. Similarity only identifies candidates.",
    "get_batches": "Retrieve structured batch/lot and date records for a company SKU.",
    "resolve_exposure": "Run the deterministic exposure resolver for a recall and SKU.",
    "get_inventory": "Retrieve remaining structured inventory records and quantity.",
    "get_dispatches": "Retrieve downstream dispatch records and quantity.",
    "get_purchase_history": "Retrieve upstream purchase-order and supplier records.",
    "open_response_case": "Create a governed response case from CONFIRMED or POSSIBLE exposure.",
    "request_human_approval": "Stop at the human approval boundary and return tasks awaiting approval.",
    "resolve_company_exposure": "High-level agent tool for the Live Demo. Deterministically searches the catalogue, retrieves lot records and resolves exposure in ranked candidate order.",
    "trace_internal_evidence": "High-level agent tool for the Live Demo. Retrieves inventory, dispatch and purchase/supplier evidence for the confirmed or possible affected lots.",
}

def execute_tool(ctx, name, arguments):
    if name not in TOOLS:
        return {"ok":False,"error":"UNKNOWN_TOOL","tool":name}
    return TOOLS[name](ctx, **arguments)
