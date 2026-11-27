from pathlib import Path
from ingestion.load_data import load_bundle
from tools.context import ToolContext
from tools.registry import execute_tool
from agent.policies import validate_tool_call

ROOT=Path(__file__).resolve().parents[1]

def test_tool_registry_inventory():
    ctx=ToolContext(load_bundle(ROOT/"demo_data"),{})
    obs=execute_tool(ctx,"get_inventory",{"sku":"SKU001","batch_code":"SS16726"})
    assert obs["ok"]
    assert obs["total_quantity"]==41

def test_policy_blocks_unregistered_consequential_tool():
    ok,error=validate_tool_call("approve_task",{"task_id":"T1"})
    assert not ok
