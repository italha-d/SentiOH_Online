MAX_AGENT_STEPS = 16

# These actions can exist in workflow tasks but are deliberately unavailable
# as autonomous agent tools.
PROTECTED_ACTIONS = {
    "HOLD_STOCK",
    "RELEASE_STOCK",
    "CONTACT_CUSTOMER",
    "CONTACT_SUPPLIER",
    "ISSUE_RECALL_NOTICE",
    "CLOSE_CASE",
}

ALLOWED_TOOLS = {
    "get_recall","search_catalogue","get_batches","resolve_exposure",
    "get_inventory","get_dispatches","get_purchase_history",
    "open_response_case","request_human_approval",
    "resolve_company_exposure","trace_internal_evidence",
}

def validate_tool_call(tool, arguments):
    if tool not in ALLOWED_TOOLS:
        return False, f"Tool '{tool}' is not allowed."
    if not isinstance(arguments, dict):
        return False, "Tool arguments must be an object."
    return True, None
