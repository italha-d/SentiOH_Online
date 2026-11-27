from pathlib import Path
from ingestion.load_data import load_bundle, validate_bundle
from tools.context import ToolContext
from agent.orchestrator import SentiOHAgent
from agent.planner import RulePlanner
from workflow.approvals import approve_task, complete_task

ROOT=Path(__file__).resolve().parent
validation=validate_bundle(ROOT/"demo_data")
assert validation["ok"], validation

ctx=ToolContext(load_bundle(ROOT/"demo_data"),{})
agent=SentiOHAgent(ctx,RulePlanner())
state=agent.run("FSAI_DEMO_001")

assert state.status=="AWAITING_HUMAN_APPROVAL"
assert state.exposure["status"]=="CONFIRMED"
assert state.inventory["total_quantity"]==41
assert state.dispatches["total_dispatched"]==27
assert state.case_id in ctx.cases

case=ctx.cases[state.case_id]
task=next(t for t in case["tasks"] if t["title"]=="Hold remaining stock")
assert task["status"]=="WAITING_FOR_APPROVAL"

approve_task(case,task["task_id"],"Smoke Test Human","Reviewed",approver_role=task["approval_roles"][0])
complete_task(case,task["task_id"],"Smoke Test Human")
assert task["status"]=="COMPLETED"

print("PASS: recall -> agent tool loop -> deterministic exposure -> trace -> case -> human approval -> completion")
print("Investigation:",state.investigation_id)
print("Steps:",state.step)
print("Exposure:",state.exposure["status"],state.exposure["reason_code"])
print("Stock:",state.inventory["total_quantity"])
print("Dispatched:",state.dispatches["total_dispatched"])
print("Case:",state.case_id)
print("Agent stop:",state.status,state.stop_reason)

assert len(ctx.data["products"]) == 400
assert 20 <= len(ctx.data["suppliers"]) <= 30
assert len(ctx.data["batches"]) >= 800
assert len(ctx.data["purchase_orders"]) >= 500
assert len(ctx.data["dispatches"]) >= 700
print("Expanded sandbox:", len(ctx.data["products"]), "products,", len(ctx.data["batches"]), "lots,", len(ctx.data["dispatches"]), "dispatches")
