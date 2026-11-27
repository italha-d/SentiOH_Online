from __future__ import annotations
from pathlib import Path
import csv
import json
import os
import textwrap

from .common import get_context, get_data
from .branding import render_brand_header
from agent.orchestrator import SentiOHAgent
from agent.planner import (
    RulePlanner,
    OpenAICompatibleJSONPlanner,
    OllamaToolPlanner,
)
from workflow.approvals import approve_task, reject_task, complete_task
from workflow.states import close_case
from workflow.quick_demo import (
    streamline_existing_confirmed_case_for_demo,
    QUICK_CLOSE_PROFILE,
    DEMO_SITE_APPROVERS,
    reassign_rejected_demo_containment,
    request_demo_corrective_action,
    submit_demo_corrective_evidence,
)
from workflow.audit_export import audit_download_bytes, audit_export_filename
from workflow.roles import (
    ROLE_DESCRIPTIONS,
    CASE_CLOSURE_ROLES,
    INVESTIGATION_ROLES,
    DEMO_RESET_ROLES,
    MANAGEMENT_OVERVIEW_ROLES,
    RECALL_INCIDENT_MANAGER,
    WAREHOUSE_MANAGER,
)
from workflow.approval_queue import (
    approval_tasks_for_role,
    work_tasks_for_role,
    approval_statistics,
    approval_progress,
    remaining_approval_roles,
    role_has_decided,
    task_dependencies_complete,
)
from workflow.reviews import (
    review_items_for_role,
    review_statistics,
    mark_reviewed,
)
from workflow.action_center import (
    human_action_summary,
    personal_action_summary,
    case_action_progress,
    management_case_rows,
    case_attention_rows,
)
from workflow.versioning import register_recall_version
from matching.matcher import resolve_exposure
from matching.evaluate import evaluate_scenarios
from ingestion.fsai_refresh import refresh_fsai_snapshot
from ingestion.load_data import validate_fsai_snapshot
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]

FULL_FEATURE_MODE = "Official FSAI (Full Feature Prototype)"
LIVE_DEMO_MODE = "Live Demo (Prepared FSAI Case)"


def _agent_tool_trace_rows(state):
    rows = []
    if not state:
        return rows
    for event in state.events or []:
        if event.event_type != "TOOL_CALL" or not event.tool:
            continue
        observation = event.observation or {}
        rows.append({
            "step": event.step,
            "tool": event.tool,
            "planner decision": event.summary,
            "result": "Completed" if observation.get("ok") else "Stopped",
        })
    return rows


def _render_live_demo_progress(st, state, case):
    """Show the six pitch stages without changing the underlying workflow."""
    case_progress = case_action_progress(case) if case else None
    stages = [
        ("Load verified recall notice", True),
        ("Extract affected product + lot", bool(state and state.recall)),
        ("Resolve against company records", bool(state and state.exposure)),
        ("Trace stock + dispatch evidence", bool(state and state.inventory is not None and state.dispatches is not None)),
        ("Generate exposure graph + rationale", bool(state and state.case_id)),
        (
            "Role-based human completion",
            bool(case and case.get("state") == "CLOSED"),
        ),
    ]

    cols = st.columns(6)
    first_incomplete = next((i for i, (_, done) in enumerate(stages) if not done), None)
    for index, ((label, done), col) in enumerate(zip(stages, cols), 1):
        active = first_incomplete == index - 1
        icon = "✓" if done else ("●" if active else "○")
        col.markdown(f"**{icon} {index}**")
        col.caption(label)

    if case_progress and case.get("state") != "CLOSED":
        st.caption(
            "Human workflow remains active: "
            f"{case_progress['total_human_actions_left']} action(s) remain across the assigned roles. "
            "Each user can complete only work or approvals authorised for their logged-in role."
        )


def _render_live_demo_handoff(st, case):
    if not case:
        return
    rows = []
    for task in case.get("tasks", []):
        approval_roles = task.get("approval_roles") or []
        rows.append({
            "task": task.get("title"),
            "assigned role": task.get("assigned_to"),
            "approval authority": " + ".join(approval_roles) if task.get("approval_mode") == "ALL_ROLES" else " OR ".join(approval_roles),
            "status": task.get("status"),
        })
    if rows:
        with st.expander("Role-based human handoff generated", expanded=True):
            st.dataframe(rows, use_container_width=True, hide_index=True)
            st.caption(
                "Assignments appear only after the investigation creates the response case. "
                "The Response workspace then filters controls to the logged-in role."
            )



def _planner(st):
    mode = os.getenv("SENTIOH_PLANNER", "llm").strip().lower()

    if mode == "ollama":
        return OllamaToolPlanner()

    if mode == "rule":
        return RulePlanner()

    if mode == "llm":
        try:
            return OpenAICompatibleJSONPlanner()
        except Exception as exc:
            st.warning(
                "Online LLM planner configuration is incomplete. "
                f"Using the deterministic rule planner instead. {exc}"
            )
            return RulePlanner()

    st.warning(
        f"Unknown SENTIOH_PLANNER='{mode}'. Using the deterministic rule planner."
    )
    return RulePlanner()


def _fast_demo_planner(base_planner):
    """Return a fast planner only for the prepared Live Demo.

    Official FSAI continues to use the original planner unchanged. The fast
    planner remains an Ollama LLM tool-selection agent, but it sees five
    higher-level approved tools instead of nine low-level planning turns.
    """
    if isinstance(base_planner, OllamaToolPlanner):
        return OllamaToolPlanner(
            base_url=base_planner.base_url,
            model=base_planner.model,
            timeout=base_planner.timeout,
            retries=1,
            fast_mode=True,
        )
    return base_planner


def _label(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value is None:
        return "Not resolved"
    return str(value).replace("_", " ").title()


def _priority_rank(value):
    return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(value, 3)


def _recall_image_urls(recall):
    """
    Return unique regulator-provided product image URLs in preferred display
    order. No generated or guessed substitute image is ever introduced.
    """
    candidates = []

    if recall.get("image_url"):
        candidates.append(recall.get("image_url"))

    candidates.extend(recall.get("image_urls") or [])

    for item in reversed(recall.get("source_history") or []):
        if item.get("image_url"):
            candidates.append(item.get("image_url"))

    unique = []
    seen = set()
    for value in candidates:
        value = str(value or "").strip()
        if value and value not in seen:
            seen.add(value)
            unique.append(value)

    return unique


def _case_status_counts(case):
    statuses = [
        "PENDING", "WAITING_FOR_APPROVAL", "APPROVED",
        "COMPLETED", "REJECTED",
    ]
    return {
        status: sum(
            task.get("status") == status for task in case.get("tasks", [])
        )
        for status in statuses
    }


def _active_cases(cases):
    # RESOLVED is still an open case until an authorised final closure action
    # moves it to CLOSED.
    return {
        case_id: case
        for case_id, case in cases.items()
        if case.get("state") != "CLOSED"
        and not case.get("demo_archived")
    }


def _response_cases(cases):
    """Cases still available for operator review, including RESOLVED before closure."""
    return {
        case_id: case
        for case_id, case in cases.items()
        if case.get("state") != "CLOSED"
        and not case.get("demo_archived")
    }


def _closed_cases(cases):
    return {
        case_id: case
        for case_id, case in cases.items()
        if case.get("state") == "CLOSED"
        and not case.get("demo_archived")
    }


def _role_response_items_for_case(case, role):
    """
    Return only response actions the logged-in role can perform now.

    A task is relevant when the role either:
    - owns an operational task that is ready or currently blocked on approval; or
    - is currently an outstanding approval authority for a protected task.

    Review acknowledgements and final case closure are scoped separately.
    Completed work, rejected actions, actions assigned to another role and
    approvals already decided by this role are deliberately hidden.
    """
    tasks = []
    approval_task_ids = set()
    operational_task_ids = set()

    for task in case.get("tasks", []):
        task_id = task.get("task_id")
        dependency_ready = task_dependencies_complete(case, task)

        operational = (
            dependency_ready
            and task.get("assigned_to") == role
            and task.get("status")
            in {"PENDING", "APPROVED", "WAITING_FOR_APPROVAL"}
        )
        approval = (
            dependency_ready
            and task.get("status") == "WAITING_FOR_APPROVAL"
            and role in remaining_approval_roles(task)
            and not role_has_decided(task, role)
        )

        if operational:
            operational_task_ids.add(task_id)
        if approval:
            approval_task_ids.add(task_id)

        if operational or approval:
            tasks.append(task)

    reviews = [
        review
        for review in case.get("reviews", [])
        if (
            review.get("status") == "WAITING_FOR_REVIEW"
            and review.get("assigned_role") == role
        )
    ]

    can_close = (
        case.get("state") == "RESOLVED"
        and role in CASE_CLOSURE_ROLES
    )

    return {
        "tasks": tasks,
        "approval_task_ids": approval_task_ids,
        "operational_task_ids": operational_task_ids,
        "reviews": reviews,
        "can_close": can_close,
        "total": len(tasks) + len(reviews) + int(can_close),
    }


def _role_response_cases(cases, role):
    """Cases containing at least one action currently relevant to `role`."""
    return {
        case_id: case
        for case_id, case in cases.items()
        if _role_response_items_for_case(case, role)["total"] > 0
    }


def _case_for_recall(cases, recall_id):
    return next(
        (
            case for case in cases.values()
            if case.get("recall_id") == recall_id
            and not case.get("demo_archived")
        ),
        None,
    )


def _case_portfolio_rows(cases):
    rows = []
    for case_id, case in cases.items():
        counts = _case_status_counts(case)
        exposure = case.get("exposure", {})
        progress = case_action_progress(case)
        rows.append({
            "case_id": case_id,
            "recall_id": case.get("recall_id"),
            "exposure": exposure.get("status"),
            "sku": exposure.get("sku"),
            "batch": ", ".join(exposure.get("matched_batches") or [])
                     or exposure.get("batch") or "Unresolved",
            "case_state": case.get("state"),
            "revision": case.get("analysis_revision", 1),
            "tasks": len(case.get("tasks", [])),
            "approvals_left": progress["approval_left"],
            "reviews_left": progress["reviews_left"],
            "human_actions_left": progress["total_human_actions_left"],
            "completed": counts["COMPLETED"],
            "updated": case.get("updated_time") or case.get("created_time"),
        })
    rows.sort(key=lambda row: row["updated"] or "", reverse=True)
    return rows


def _recall_inbox_rows(data, cases, recalls=None):
    rows = []
    recalls = recalls if recalls is not None else data["recalls"]
    for recall in recalls:
        case = _case_for_recall(cases, recall["recall_id"])
        exposure = case.get("exposure", {}) if case else {}
        source_type = recall.get("source_type")
        rows.append({
            "recall_id": recall["recall_id"],
            "official_alert": recall.get("official_recall_id") or "Synthetic",
            "source": (
                "Official FSAI"
                if source_type == "official_fsai_snapshot"
                else "Synthetic fallback"
            ),
            "publication_date": recall.get("published_date") or "Not stated",
            "product": recall.get("product_name"),
            "pack_scope": ", ".join(recall.get("pack_sizes") or []),
            "hazard": recall.get("hazard"),
            "ingestion_status": recall.get("ingestion_status") or "SYNTHETIC",
            "exposure_status": exposure.get("status") or "NOT_ANALYSED",
            "case_state": case.get("state") if case else "NO_CASE",
            "source_verified": bool(recall.get("is_public_source_verified")),
        })
    return rows


def _catalogue_scan(data, recall):
    rows = []
    for product in data["products"]:
        result = resolve_exposure(
            recall,
            product,
            data["batches"],
            data["inventory"],
            data["dispatches"],
        )
        rows.append({
            "sku": product["sku"],
            "product": product["product_name"],
            "brand": product["brand"],
            "pack": product["pack_size"],
            "status": result["status"],
            "reason_code": result["reason_code"],
            "similarity": result.get("product_name_similarity"),
            "identifier_match": result.get("product_identifier_match"),
            "batch": ", ".join(result.get("matched_batches") or [])
                     or result.get("batch") or "",
            "stock": result.get("stock", 0),
            "dispatched": result.get("dispatched", 0),
        })
    return rows


def _load_ground_truth():
    with open(
        ROOT / "demo_data" / "ground_truth_scenarios.csv",
        newline="",
        encoding="utf-8",
    ) as handle:
        return list(csv.DictReader(handle))


def _load_updates():
    path = ROOT / "demo_data" / "recall_updates.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _load_real_fsai_showcase():
    path = ROOT / "demo_data" / "real_fsai_showcase_scenarios.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _render_traceability_graph(st, state, presentation=False):
    if not state or not state.exposure:
        st.info("Run an investigation to generate the traceability graph.")
        return

    exposure = state.exposure
    recall = state.recall or {}
    batches = exposure.get("matched_batches") or (
        [exposure.get("batch")] if exposure.get("batch") else []
    )

    def esc(value):
        return str(value or "").replace('"', "'")

    dot = [
        "digraph G {",
        "rankdir=LR;",
        'graph [pad="0.45", nodesep="0.75", ranksep="1.05", bgcolor="transparent"];',
        'node [shape=box, style="rounded", fontsize=16, margin="0.24,0.16", penwidth=1.4];',
        'edge [penwidth=1.7, arrowsize=0.85];',
        (
            f'recall [label="{esc(recall.get("authority", "Recall"))} Recall\\n'
            f'{esc(recall.get("product_name"))}"];'
        ),
        (
            f'product [label="{esc(exposure.get("sku"))}\\n'
            f'{esc(exposure.get("product_name"))}"];'
        ),
        "recall -> product;",
    ]

    for i, batch in enumerate(batches or ["UNRESOLVED"]):
        dot.append(f'batch{i} [label="Lot / Batch\\n{esc(batch)}"];')
        dot.append(f"product -> batch{i};")

    po_records = (state.purchase_history or {}).get("records", [])
    for i, po in enumerate(po_records):
        po_node = f"po{i}"
        supplier_node = f"supplier{i}"
        dot.append(
            f'{po_node} [label="Purchase Order\\n{esc(po.get("po"))}\\n'
            f'{esc(po.get("quantity"))} units"];'
        )
        dot.append(
            f'{supplier_node} [label="Supplier\\n{esc(po.get("supplier_name") or po.get("supplier_id"))}"];'
        )
        target = 0
        po_batch = str(po.get("batch_code") or "")
        for j, batch in enumerate(batches):
            if str(batch) == po_batch.replace("-", "").replace(" ", ""):
                target = j
                break
        dot.append(f"batch{target} -> {po_node};")
        dot.append(f"{po_node} -> {supplier_node};")

    inventory_records = (state.inventory or {}).get("records", [])
    site_nodes = {}
    for row in inventory_records:
        site = row.get("site") or row.get("site_code") or "Site"
        site_key = esc(site)
        if site_key not in site_nodes:
            node = f"site{len(site_nodes)}"
            site_nodes[site_key] = node
            dot.append(f'{node} [label="Site\\n{site_key}"];')
        node = site_nodes[site_key]
        batch_index = 0
        row_batch = str(row.get("batch_code") or "").replace("-", "").replace(" ", "")
        for j, batch in enumerate(batches):
            if str(batch) == row_batch:
                batch_index = j
                break
        stock_node = f"stock{len(site_nodes)}_{batch_index}_{len(dot)}"
        dot.append(
            f'{stock_node} [label="Remaining Stock\\n{esc(row.get("quantity"))} units"];'
        )
        dot.append(f"batch{batch_index} -> {node};")
        dot.append(f"{node} -> {stock_node};")

    dispatch_records = (state.dispatches or {}).get("records", [])
    for i, row in enumerate(dispatch_records):
        dispatch_node = f"dispatch{i}"
        customer_node = f"customer{i}"
        batch_index = 0
        row_batch = str(row.get("batch_code") or "").replace("-", "").replace(" ", "")
        for j, batch in enumerate(batches):
            if str(batch) == row_batch:
                batch_index = j
                break
        dot.append(
            f'{dispatch_node} [label="Dispatch\\n{esc(row.get("dispatch_id"))}\\n'
            f'{esc(row.get("quantity"))} units"];'
        )
        dot.append(
            f'{customer_node} [label="Customer\\n{esc(row.get("customer"))}"];'
        )
        dot.append(f"batch{batch_index} -> {dispatch_node};")
        dot.append(f"{dispatch_node} -> {customer_node};")

    dot.append("}")
    st.graphviz_chart("\n".join(dot), use_container_width=True)




def _render_task(st, ctx, case, task, current_user):
    """Compact task card. Operational detail stays collapsed until requested."""
    current_role = current_user["role"]
    current_name = current_user["display_name"]
    progress = approval_progress(task)

    with st.container(border=True):
        title_col, priority_col, status_col = st.columns([5.2, 1.2, 1.6])
        title_col.markdown(f"#### {task['title']}")
        priority_col.caption("PRIORITY")
        priority_col.write(f"**{task['priority']}**")
        status_col.caption("STATUS")
        status_col.write(f"**{_label(task['status'])}**")

        meta = [f"Assigned to: {task.get('assigned_to') or 'Unassigned'}"]
        if task.get("requires_approval"):
            meta.append(f"Approvals left: {progress['left']}")
        st.caption(" · ".join(meta))
        st.write(task.get("description", ""))

        if task.get("requires_approval"):
            approval_roles = task.get("approval_roles") or []
            approval_mode = task.get("approval_mode") or "ANY_ONE"
            authority = (
                " + ".join(approval_roles)
                if approval_mode == "ALL_ROLES"
                else " or ".join(approval_roles)
            )
            st.caption(f"Approval authority: {authority}")
            remaining = remaining_approval_roles(task)
            if task["status"] == "WAITING_FOR_APPROVAL" and remaining:
                st.info("Waiting for: " + " | ".join(remaining))
            elif task["status"] == "APPROVED":
                st.success("Required approval is complete.")
            elif task["status"] == "REJECTED":
                st.warning(
                    "This action was rejected. The deterministic exposure result is unchanged."
                )

        with st.expander("View task rationale, evidence and audit detail"):
            st.markdown("**Why SentiOH created this task**")
            st.write(task.get("why_generated", "No rationale recorded."))

            if task.get("narrative_source") == "llm":
                st.caption(
                    "Generated from this case's structured evidence by "
                    f"{task.get('narrative_model') or 'the configured LLM'}. "
                    "Governance fields below remain deterministic."
                )
            else:
                st.caption(
                    "Deterministic fallback wording is shown because no LLM "
                    "task narrative has been applied."
                )

            detail_left, detail_right = st.columns(2)
            with detail_left:
                st.markdown("**Suggested steps**")
                for i, step in enumerate(task.get("suggested_steps") or [], 1):
                    st.write(f"{i}. {step}")
                st.markdown("**Completion evidence expected**")
                for item in task.get("completion_evidence") or []:
                    st.write(f"• {item}")

            with detail_right:
                st.markdown("**Completion criterion**")
                st.write(task.get("completion_criteria", ""))
                st.markdown("**Agent boundary**")
                st.write(task.get("action_boundary", "No boundary note recorded."))

            evidence = task.get("evidence") or {}
            if evidence:
                st.markdown("**Evidence that triggered the task**")
                st.json(evidence)

            approvals = task.get("approvals") or []
            if approvals:
                st.markdown("**Recorded human decisions**")
                st.dataframe(
                    [
                        {
                            "decision": item.get("decision"),
                            "approver": item.get("approver"),
                            "role": item.get("approver_role"),
                            "time": item.get("time"),
                            "comment": item.get("comment"),
                        }
                        for item in approvals
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

        can_decide = (
            task.get("status") == "WAITING_FOR_APPROVAL"
            and current_role in remaining_approval_roles(task)
            and (
                not task.get("approval_usernames")
                or current_user.get("username") in task.get("approval_usernames", [])
            )
            and not role_has_decided(task, current_role)
        )

        if can_decide:
            st.caption(
                f"This protected action is assigned to your authority as {current_role}."
            )
            comment = st.text_input(
                "Decision note",
                "Reviewed against the structured recall and company evidence.",
                key=f"comment_{case['case_id']}_{task['task_id']}_{current_user['username']}",
            )
            approve_col, reject_col = st.columns(2)

            if approve_col.button(
                "Approve proposed action",
                key=f"approve_{case['case_id']}_{task['task_id']}_{current_user['username']}",
                type="primary",
                use_container_width=True,
            ):
                try:
                    def _approve(latest_case):
                        approve_task(
                            latest_case,
                            task["task_id"],
                            current_name,
                            comment,
                            approver_role=current_role,
                            approver_username=current_user.get("username"),
                        )
                        return latest_case

                    ctx.mutate_case(case["case_id"], _approve)
                    st.rerun()
                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))

            if reject_col.button(
                "Reject proposed action",
                key=f"reject_{case['case_id']}_{task['task_id']}_{current_user['username']}",
                use_container_width=True,
            ):
                try:
                    def _reject(latest_case):
                        reject_task(
                            latest_case,
                            task["task_id"],
                            current_name,
                            comment,
                            approver_role=current_role,
                            approver_username=current_user.get("username"),
                        )
                        return latest_case

                    ctx.mutate_case(case["case_id"], _reject)
                    st.rerun()
                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))

        elif (
            task.get("status") == "WAITING_FOR_APPROVAL"
            and task.get("requires_approval")
            and role_has_decided(task, current_role)
        ):
            st.success(
                "Your decision is recorded. This action is waiting on another authorised role."
            )

        can_complete = (
            task["status"] in {"PENDING", "APPROVED"}
            and task.get("assigned_to") == current_role
        )
        if can_complete:
            if st.button(
                "Mark my assigned task completed",
                key=f"complete_{case['case_id']}_{task['task_id']}_{current_user['username']}",
                use_container_width=True,
            ):
                try:
                    def _complete(latest_case):
                        complete_task(
                            latest_case,
                            task["task_id"],
                            current_name,
                            actor_role=current_role,
                        )
                        return latest_case

                    ctx.mutate_case(case["case_id"], _complete)
                    st.rerun()
                except PermissionError as exc:
                    st.error(str(exc))


def _render_my_approval_inbox(st, ctx, current_user):
    role = current_user["role"]
    pending = approval_tasks_for_role(ctx.cases, role, username=current_user.get("username"))

    st.header("My Approval Inbox")
    if not pending:
        st.success(f"No approval decisions are currently waiting for {role}.")
        return

    st.warning(
        f"{len(pending)} protected action(s) currently require a decision from your role."
    )
    for case, task in pending:
        with st.container(border=True):
            left, mid, right = st.columns([3.5, 1.6, 1.3])
            left.markdown(f"### {task['title']}")
            left.caption(
                f"Case {case['case_id']} | Recall {case.get('recall_id')} | "
                f"Exposure {_label(case.get('exposure', {}).get('status'))}"
            )
            mid.metric("Priority", task.get("priority"))
            right.metric("Approvals left", approval_progress(task)["left"])

            st.write(task.get("why_generated", ""))
            evidence = task.get("evidence") or {}
            st.caption(
                "Evidence: "
                + " | ".join(
                    f"{key}={value}" for key, value in evidence.items()
                    if value not in (None, "")
                )
            )

            comment = st.text_input(
                "Decision comment / rejection reason",
                "Reviewed against the structured recall and company evidence.",
                key=f"inbox_comment_{case['case_id']}_{task['task_id']}_{current_user['username']}",
            )
            a, b = st.columns(2)
            if a.button(
                "Approve",
                type="primary",
                key=f"inbox_approve_{case['case_id']}_{task['task_id']}_{current_user['username']}",
            ):
                try:
                    def _approve_inbox(latest_case):
                        approve_task(
                            latest_case,
                            task["task_id"],
                            current_user["display_name"],
                            comment,
                            approver_role=role,
                        )
                        return latest_case
                    ctx.mutate_case(case["case_id"], _approve_inbox)
                    st.rerun()
                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))
            if b.button(
                "Reject",
                key=f"inbox_reject_{case['case_id']}_{task['task_id']}_{current_user['username']}",
            ):
                try:
                    def _reject_inbox(latest_case):
                        reject_task(
                            latest_case,
                            task["task_id"],
                            current_user["display_name"],
                            comment,
                            approver_role=role,
                        )
                        return latest_case
                    ctx.mutate_case(case["case_id"], _reject_inbox)
                    st.rerun()
                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))



def _render_review_action(st, ctx, case, review, current_user):
    """Render one review acknowledgement that belongs to the logged-in role."""
    with st.container(border=True):
        left, mid = st.columns([4.5, 1.2])
        left.markdown(f"### {review['title']}")
        left.caption(
            f"Case {case['case_id']} | Recall {case.get('recall_id')} | "
            f"Assigned to {review.get('assigned_role')}"
        )
        mid.metric("Priority", review.get("priority"))
        st.write(review.get("description", ""))

        evidence = review.get("evidence") or {}
        if evidence:
            st.caption(
                "Evidence: "
                + " | ".join(
                    f"{key}={value}"
                    for key, value in evidence.items()
                    if value not in (None, "", [])
                )
            )

        comment = st.text_input(
            "Review note",
            "Reviewed against the available recall and company evidence.",
            key=(
                f"response_review_comment_{case['case_id']}_"
                f"{review['review_id']}_{current_user['username']}"
            ),
        )
        if st.button(
            "Mark as reviewed",
            type="primary",
            key=(
                f"response_mark_reviewed_{case['case_id']}_"
                f"{review['review_id']}_{current_user['username']}"
            ),
            use_container_width=True,
        ):
            try:
                def _mark(latest_case):
                    mark_reviewed(
                        latest_case,
                        review["review_id"],
                        current_user["display_name"],
                        current_user["role"],
                        comment,
                    )
                    return latest_case

                ctx.mutate_case(case["case_id"], _mark)
                st.rerun()
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))


def _render_my_review_inbox(st, ctx, current_user):
    role = current_user["role"]
    pending = review_items_for_role(ctx.cases, role)

    st.header("My Review Inbox")
    if not pending:
        st.success(f"No review acknowledgements are currently waiting for {role}.")
        return

    st.warning(
        f"{len(pending)} review item(s) require acknowledgement from your role."
    )
    for case, review in pending:
        with st.container(border=True):
            left, mid = st.columns([4.5, 1.2])
            left.markdown(f"### {review['title']}")
            left.caption(
                f"Case {case['case_id']} | Recall {case.get('recall_id')} | "
                f"Exposure {_label(case.get('exposure', {}).get('status'))}"
            )
            mid.metric("Priority", review.get("priority"))
            st.write(review.get("description", ""))

            evidence = review.get("evidence") or {}
            if evidence:
                st.caption(
                    "Evidence: "
                    + " | ".join(
                        f"{key}={value}"
                        for key, value in evidence.items()
                        if value not in (None, "", [])
                    )
                )

            comment = st.text_input(
                "Review note",
                "Reviewed against the available recall and company evidence.",
                key=(
                    f"review_comment_{case['case_id']}_"
                    f"{review['review_id']}_{current_user['username']}"
                ),
            )
            if st.button(
                "Mark as reviewed",
                type="primary",
                key=(
                    f"mark_reviewed_{case['case_id']}_"
                    f"{review['review_id']}_{current_user['username']}"
                ),
            ):
                try:
                    def _mark(latest_case):
                        mark_reviewed(
                            latest_case,
                            review["review_id"],
                            current_user["display_name"],
                            current_user["role"],
                            comment,
                        )
                        return latest_case

                    ctx.mutate_case(case["case_id"], _mark)
                    st.rerun()
                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))


def _render_management_overview(st, ctx, current_user):
    if current_user["role"] not in MANAGEMENT_OVERVIEW_ROLES:
        return

    response_cases = _response_cases(ctx.cases)
    st.header("Incident Management Overview")
    st.caption(
        "Management view of where each recall response is waiting on a human "
        "approval, review acknowledgement or operational completion."
    )

    if not response_cases:
        st.info("No response cases are currently open.")
        return

    st.dataframe(
        management_case_rows(response_cases),
        use_container_width=True,
        hide_index=True,
    )

    role_rows = []
    for role in ROLE_DESCRIPTIONS:
        personal = personal_action_summary(response_cases, role)
        if personal["total"]:
            role_rows.append({
                "role": role,
                "approval_inbox": personal["approval_count"],
                "reviews_required": personal["review_count"],
                "operational_work": personal["work_count"],
                "total_attention_items": personal["total"],
            })

    if role_rows:
        st.markdown("**Who currently needs to act**")
        st.dataframe(
            role_rows,
            use_container_width=True,
            hide_index=True,
        )

    case_ids = list(response_cases)
    selected_case_id = st.selectbox(
        "Management case attention view",
        case_ids,
        format_func=lambda case_id: (
            f"{case_id} | {response_cases[case_id].get('recall_id')} | "
            f"{_label(response_cases[case_id].get('exposure', {}).get('status'))}"
        ),
        key="management_case_attention_selector",
    )
    selected_case = response_cases[selected_case_id]
    progress = case_action_progress(selected_case)

    a, b, c, d = st.columns(4)
    a.metric(
        "Approval decisions",
        f"{progress['approval_decisions_completed']} / {progress['approval_required']}",
    )
    b.metric(
        "Reviews",
        f"{progress['reviews_completed']} / {progress['reviews_required']}",
    )
    c.metric(
        "Tasks",
        f"{progress['tasks_completed']} / {progress['tasks_total']}",
    )
    d.metric("Human actions left", progress["total_human_actions_left"])

    attention_rows = case_attention_rows(selected_case)
    if attention_rows:
        st.markdown("**Attention required for selected case**")
        st.dataframe(
            attention_rows,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No outstanding human actions remain for this selected case.")



def _render_my_work_queue(st, ctx, current_user):
    role = current_user["role"]
    work = work_tasks_for_role(ctx.cases, role)

    st.header("My Operational Work")
    if not work:
        st.success("No operational tasks are currently assigned to your role.")
        return

    st.warning(f"{len(work)} operational task(s) are ready for your role.")
    for case, task in work:
        with st.container(border=True):
            left, mid, right = st.columns([4, 1.2, 1.6])
            left.markdown(f"### {task['title']}")
            left.caption(
                f"Case {case['case_id']} | Recall {case.get('recall_id')}"
            )
            mid.metric("Priority", task.get("priority"))
            right.metric("Status", _label(task.get("status")))
            st.write(task.get("description", ""))
            if st.button(
                "Mark operational task completed",
                key=(
                    f"action_centre_complete_{case['case_id']}_"
                    f"{task['task_id']}_{current_user['username']}"
                ),
            ):
                try:
                    def _complete_work(latest_case):
                        complete_task(
                            latest_case,
                            task["task_id"],
                            current_user["display_name"],
                            actor_role=current_role,
                        )
                        return latest_case

                    ctx.mutate_case(case["case_id"], _complete_work)
                    st.rerun()
                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))


def _apply_demo_update(st, ctx, recall_id):
    update = next(
        (
            item for item in _load_updates()
            if item.get("recall_id") == recall_id
        ),
        None,
    )
    if not update:
        return False

    recall = next(
        r for r in ctx.data["recalls"] if r["recall_id"] == recall_id
    )
    for key, value in update["patch"].items():
        recall[key] = value

    case = _case_for_recall(ctx.cases, recall_id)
    if case:
        register_recall_version(case, recall)
        ctx.save_case(case)

    st.session_state.pop(f"investigation_{recall_id}", None)
    st.session_state[f"demo_update_applied_{recall_id}"] = True
    return True


def _inject_dashboard_css(st):
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1500px;
            padding-top: 1.6rem;
            padding-bottom: 3rem;
        }
        div[data-testid="stMetric"] {
            border: 1px solid rgba(128,128,128,0.22);
            border-radius: 12px;
            padding: 0.75rem 0.9rem;
            background: rgba(128,128,128,0.035);
            min-height: 6.4rem;
            height: 100%;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 0.78rem;
            letter-spacing: 0.01em;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        div[data-testid="stMetricLabel"] p {
            white-space: normal !important;
            overflow-wrap: anywhere !important;
            line-height: 1.2 !important;
        }
        div[data-testid="stMetricValue"] {
            width: 100%;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        div[data-testid="stMetricValue"] > div {
            white-space: normal !important;
            overflow: visible !important;
            overflow-wrap: anywhere !important;
            word-break: normal !important;
            text-overflow: clip !important;
            line-height: 1.15 !important;
            font-size: clamp(1.05rem, 1.45vw, 1.55rem) !important;
        }
        div[data-testid="stExpander"] {
            border-radius: 10px;
        }
        button[data-baseweb="tab"] {
            padding: 0.7rem 1.35rem !important;
            min-height: 3rem !important;
            border-radius: 10px 10px 0 0 !important;
            font-size: 1.02rem !important;
            font-weight: 700 !important;
        }
        div[data-baseweb="tab-list"] {
            gap: 0.45rem !important;
            border-bottom: 1px solid rgba(128,128,128,0.30) !important;
            margin-bottom: 0.8rem !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background: rgba(128,128,128,0.11) !important;
            border: 1px solid rgba(128,128,128,0.30) !important;
            border-bottom-color: transparent !important;
        }
        /* Keep Graphviz completely inside the bordered Streamlit card. */
        div[data-testid="stGraphVizChart"] {
            width: 100% !important;
            max-width: 100% !important;
            overflow: hidden !important;
            box-sizing: border-box !important;
        }
        div[data-testid="stGraphVizChart"] > div {
            width: 100% !important;
            max-width: 100% !important;
            overflow: hidden !important;
            box-sizing: border-box !important;
        }
        div[data-testid="stGraphVizChart"] svg {
            width: 100% !important;
            max-width: 100% !important;
            height: auto !important;
            display: block !important;
            margin: 0 auto !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _status_banner(st, action_stats):
    if action_stats["all_human_actions_complete"]:
        st.success(
            "ALL HUMAN ACTIONS COMPLETE. No approval, review or operational actions remain."
        )
        return

    if (
        action_stats.get("protected_tasks")
        and action_stats.get("approval_decisions_left") == 0
        and action_stats.get("rejected_actions") == 0
    ):
        st.success(
            "All required human approvals are complete. "
            "Any remaining reviews or operational tasks are shown below."
        )

    parts = []
    if action_stats["approval_decisions_left"]:
        parts.append(
            f"{action_stats['approval_decisions_left']} approval decision(s)"
        )
    if action_stats["reviews_left"]:
        parts.append(f"{action_stats['reviews_left']} review(s)")
    if action_stats["operational_tasks_left"]:
        parts.append(
            f"{action_stats['operational_tasks_left']} operational task(s)"
        )

    if parts:
        st.warning("Attention required: " + ", ".join(parts) + " remain.")
    elif action_stats["rejected_actions"]:
        st.warning(
            "Approval routing is complete, but at least one proposed action was rejected."
        )


def _selected_case(cases, state, st):
    if not cases:
        return None

    rows = _case_portfolio_rows(cases)
    if state and getattr(state, "case_id", None) in cases:
        default_case_id = state.case_id
    elif st.session_state.get("active_case_id") in cases:
        default_case_id = st.session_state["active_case_id"]
    else:
        default_case_id = rows[0]["case_id"]

    case_ids = [row["case_id"] for row in rows]
    selected_case_id = st.selectbox(
        "Inspect response case",
        case_ids,
        index=case_ids.index(default_case_id)
        if default_case_id in case_ids
        else 0,
        format_func=lambda case_id: (
            f"{case_id} · {cases[case_id].get('recall_id')} · "
            f"{_label(cases[case_id].get('exposure', {}).get('status'))}"
        ),
        key="case_portfolio_selector",
    )
    st.session_state["active_case_id"] = selected_case_id
    return cases[selected_case_id]


def _render_official_fsai(st, current_user=None):
    _inject_dashboard_css(st)

    ctx = get_context(st)
    data = ctx.data
    planner = _planner(st)

    if current_user is None:
        current_user = {
            "username": "system",
            "display_name": "System User",
            "role": "Recall / Incident Manager",
        }

    current_role = current_user["role"]
    manifest = json.loads(
        (ROOT / "demo_data" / "dataset_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    active_case_map = _active_cases(ctx.cases)
    response_case_map = _response_cases(ctx.cases)
    action_stats = human_action_summary(active_case_map)
    personal = personal_action_summary(active_case_map, current_role, username=current_user.get("username"))

    confirmed_exposures = sum(
        case.get("exposure", {}).get("status") == "CONFIRMED"
        for case in active_case_map.values()
    )
    possible_exposures = sum(
        case.get("exposure", {}).get("status") == "POSSIBLE"
        for case in active_case_map.values()
    )

    st.caption(
        "Recall Response Control Tower · Evidence-grounded bounded agency with governed human action"
    )
    st.caption(
        f"Signed in as **{current_user['display_name']}** · {current_role}"
    )

    # This renderer is the unchanged full-feature Official FSAI experience.
    # The challenge-focused Live Demo is rendered separately in the second top-level tab.
    live_demo_mode = False
    st.session_state["recall_source_mode"] = "Official FSAI"

    st.subheader("Attention Required")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Open response cases", len(active_case_map))
    k2.metric("Confirmed exposures", confirmed_exposures)
    k3.metric("Human actions left", action_stats["total_human_actions_left"])
    k4.metric("Approvals left", action_stats["approval_decisions_left"])
    k5.metric("My actions", personal["total"])

    _status_banner(st, action_stats)

    tabs = st.tabs(
        [
            "Overview",
            "Investigation",
            "Exposure & Evidence",
            "Response",
            "Validation",
        ]
    )

    # ================================================================
    # OVERVIEW
    # ================================================================
    with tabs[0]:
        st.subheader("Operational overview")
        st.subheader("All active cases")
        left, right = st.columns([1.7, 1])

        with left:
            if response_case_map:
                rows = management_case_rows(response_case_map)
                st.dataframe(
                    rows,
                    use_container_width=True,
                    hide_index=True,
                    height=min(260, 38 + 35 * max(len(rows), 1)),
                )
            else:
                st.info(
                    "No response case exists yet. Run an investigation from the Investigation tab."
                )

        with right:
            st.markdown("#### Your workload")
            w1, w2, w3 = st.columns(3)
            w1.metric("Approve", personal["approval_count"])
            w2.metric("Review", personal["review_count"])
            w3.metric("Complete", personal["work_count"])
            if personal["total"]:
                st.info(
                    "Your actionable controls are available in the left sidebar."
                )
            else:
                st.success("Nothing is currently assigned to your role.")

            st.markdown("#### Portfolio")
            p1, p2 = st.columns(2)
            p1.metric("Possible exposures", possible_exposures)
            p2.metric("Official FSAI product recalls", len(data.get("real_recalls") or []))

        if current_role in MANAGEMENT_OVERVIEW_ROLES:
            with st.expander("Management overview", expanded=False):
                _render_management_overview(st, ctx, current_user)

        with st.expander("Data provenance"):
            st.write(
                "Regulatory recall input is sourced from the bundled official FSAI "
                "snapshot produced by the corrected scraper/ingestion pipeline. "
                "Company catalogue, SKU, supplier, lot, stock, purchase and dispatch "
                "records remain synthetic by design for the challenge prototype."
            )
            st.caption(
                f"Official FSAI product-scope recalls: {len(data.get('real_recalls') or [])} · "
                f"FSAI records held for review: {len(data.get('fsai_review') or [])} · "
                "Company catalogue, stock, supplier and dispatch records: synthetic challenge sandbox"
            )

        if current_role in DEMO_RESET_ROLES:
            with st.expander("Official FSAI regulatory feed", expanded=False):
                fsai_status = validate_fsai_snapshot(ROOT / "regulatory_data")
                s1, s2, s3 = st.columns(3)
                s1.metric(
                    "Primary FSAI recalls",
                    fsai_status["counts"]["primary_product_scope_recalls"],
                )
                s2.metric(
                    "Official alert IDs",
                    fsai_status["counts"]["official_alert_ids"],
                )
                s3.metric(
                    "Needs review",
                    fsai_status["counts"]["review_required_product_scope_recalls"],
                )

                if fsai_status["ok"]:
                    st.success("Bundled official FSAI snapshot passes validation.")
                else:
                    st.error("FSAI snapshot validation found issues.")
                    for issue in fsai_status["issues"]:
                        st.write(f"• {issue}")

                st.caption(
                    "The bundled snapshot is the safe default for the live demo. "
                    "A live refresh is optional and requires internet access, Playwright "
                    "and Chromium. Refreshing the regulator feed is application-controlled, "
                    "not an autonomous LLM tool."
                )

                default_from = date.today() - timedelta(days=60)
                refresh_from = st.date_input(
                    "Refresh from",
                    value=default_from,
                    key="fsai_refresh_from",
                )
                refresh_to = st.date_input(
                    "Refresh to",
                    value=date.today(),
                    key="fsai_refresh_to",
                )

                if st.button(
                    "Refresh official FSAI recalls",
                    key="refresh_official_fsai",
                    use_container_width=True,
                ):
                    with st.spinner(
                        "Running the corrected FSAI scraper and merging new/updated recalls..."
                    ):
                        try:
                            result = refresh_fsai_snapshot(
                                ROOT,
                                from_date=refresh_from.isoformat(),
                                to_date=refresh_to.isoformat(),
                                max_pages=10,
                                delay=0.5,
                            )
                            new_data = get_data()

                            for changed_id in result.get("changed_recall_ids") or []:
                                case = _case_for_recall(ctx.cases, changed_id)
                                refreshed = next(
                                    (
                                        item
                                        for item in new_data.get("real_recalls", [])
                                        if item.get("recall_id") == changed_id
                                    ),
                                    None,
                                )
                                if case and refreshed:
                                    register_recall_version(case, refreshed)
                                    ctx.save_case(case)

                            st.session_state["data"] = new_data
                            st.success(
                                "FSAI refresh completed: "
                                f"{len(result.get('new_recall_ids') or [])} new, "
                                f"{len(result.get('changed_recall_ids') or [])} updated."
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(
                                "Live FSAI refresh failed. The bundled verified snapshot "
                                f"remains available. Details: {exc}"
                            )

            with st.expander("Demo administration"):
                st.markdown("**End-to-end multi-role demo**")
                st.caption(
                    "Select Live Demo at the top of the application, then open Investigation. "
                    "A Recall / Incident Manager can run the agentic investigation on a prepared "
                    "genuine FSAI case. SentiOH then keeps the full task, approval and review set. "
                    "Each subsequent user must sign in with the role assigned to their action; "
                    "the case resolves only after the required human work is completed."
                )

                if st.button("Reset shared demo", use_container_width=False):
                    st.session_state["data"] = get_data()
                    ctx.clear_cases()
                    st.session_state.pop("active_case_id", None)
                    st.session_state.pop("recently_closed_case_id", None)
                    for session_key in list(st.session_state.keys()):
                        if (
                            str(session_key).startswith("investigation_")
                            or str(session_key).startswith("demo_update_applied_")
                            or str(session_key).startswith("quick_close_")
                            or str(session_key).startswith("recently_closed_")
                        ):
                            del st.session_state[session_key]
                    st.rerun()

    # ================================================================
    # INVESTIGATION
    # ================================================================
    with tabs[1]:
        st.header("1. Recall Inbox & Investigation")

        source_mode = "Demo" if live_demo_mode else "Official FSAI"
        st.caption(
            "Regulatory input: "
            + (
                "Prepared genuine FSAI recall set for the live demonstration."
                if live_demo_mode
                else "Complete genuine FSAI snapshot with the full feature prototype."
            )
        )

        showcase_items = _load_real_fsai_showcase()
        showcase = {
            item["recall_id"]: item
            for item in showcase_items
        }

        if live_demo_mode:
            showcase_ids = set(showcase)
            recall_pool = [
                recall
                for recall in (data.get("real_recalls") or [])
                if recall.get("recall_id") in showcase_ids
            ]
        else:
            recall_pool = data.get("real_recalls") or []

        if not recall_pool:
            st.error("No recall records are available for the selected source.")
            st.stop()

        recall_ids = [r["recall_id"] for r in recall_pool]
        showcase_position = {}
        for status in ["CONFIRMED", "POSSIBLE", "NOT_AFFECTED"]:
            grouped = [
                item
                for item in showcase_items
                if item.get("expected_status") == status
            ]
            for position, item in enumerate(grouped, 1):
                showcase_position[item["recall_id"]] = (
                    position,
                    len(grouped),
                )
        default_real_id = next(
            (
                item["recall_id"]
                for item in _load_real_fsai_showcase()
                if item.get("expected_status") == "CONFIRMED"
                and item["recall_id"] in recall_ids
            ),
            recall_ids[0],
        )
        selected = st.session_state.get(
            "selected_recall_id",
            default_real_id,
        )
        if selected not in recall_ids:
            selected = default_real_id

        rid = st.selectbox(
            "Recall",
            recall_ids,
            index=recall_ids.index(selected)
            if selected in recall_ids
            else 0,
            format_func=lambda item_id: (
                (
                    (
                        f"DEMO {showcase[item_id]['expected_status']} "
                        f"{showcase_position[item_id][0]}/{showcase_position[item_id][1]} · "
                    )
                    if live_demo_mode and item_id in showcase
                    else ""
                )
                + next(
                    (
                        (
                            f"FSAI {item.get('official_recall_id')} · "
                            f"{item.get('product_name')} · "
                            f"{', '.join(item.get('pack_sizes') or []) or 'pack not stated'}"
                        )
                        if item.get("source_type") == "official_fsai_snapshot"
                        else f"{item_id} · {item.get('product_name')}"
                    )
                    for item in recall_pool
                    if item.get("recall_id") == item_id
                )
            ),
            key="investigation_recall_selector",
        )
        st.session_state["selected_recall_id"] = rid
        recall = next(
            r for r in recall_pool
            if r["recall_id"] == rid
        )
        key = f"investigation_{rid}"
        state = st.session_state.get(key)
        selected_case = _case_for_recall(ctx.cases, rid)

        if live_demo_mode:
            st.subheader("Live demo path")
            _render_live_demo_progress(st, state, selected_case)

        with st.expander("View Recall Inbox"):
            st.dataframe(
                _recall_inbox_rows(data, ctx.cases, recall_pool),
                use_container_width=True,
                hide_index=True,
            )

        source_col, agent_col = st.columns([1.35, 1])

        with source_col:
            st.subheader("Public Recall Evidence")
            r1, r2, r3 = st.columns(3)
            r1.metric(
                "Authority",
                "FSAI"
                if recall.get("source_type") == "official_fsai_snapshot"
                else recall.get("authority") or "Not stated",
            )
            r2.metric(
                "Date of alert",
                recall.get("published_date") or "Not stated",
            )
            r3.metric(
                "Source",
                (
                    recall.get("ingestion_status") or "OFFICIAL"
                    if recall.get("source_type") == "official_fsai_snapshot"
                    else "SYNTHETIC"
                ),
            )

            image_col, evidence_col = st.columns([0.9, 2.3])

            with image_col:
                st.markdown("**Recalled product image**")
                image_urls = _recall_image_urls(recall)
                if image_urls:
                    st.image(
                        image_urls[0],
                        caption="Official FSAI product image",
                        use_container_width=True,
                    )
                    st.caption("Image source: official FSAI recall notice")
                    st.link_button(
                        "Open original image",
                        image_urls[0],
                        use_container_width=True,
                    )
                else:
                    st.info(
                        "No product image was provided in the source recall notice."
                    )

            with evidence_col:
                st.markdown(
                    f"**Product:** {recall.get('product_name') or 'Not stated'}"
                )
                st.markdown(
                    f"**Brand:** {recall.get('brand') or 'Not stated'}"
                )
                st.markdown(
                    "**Pack scope:** "
                    + (
                        ", ".join(recall.get("pack_sizes") or [])
                        or "Not stated"
                    )
                )
                st.markdown(
                    "**Affected lot(s):** "
                    + (
                        ", ".join(recall.get("batch_codes") or [])
                        or "Not stated"
                    )
                )
                dates = list(recall.get("use_by") or []) + list(
                    recall.get("best_before") or []
                )
                dates += list(recall.get("date_scope_text") or [])
                st.markdown(
                    f"**Date scope:** {', '.join(dates) or 'Not stated'}"
                )
                st.markdown(
                    "**Hazard / reason:** "
                    f"{recall.get('hazard') or 'Not stated'}"
                )

            with st.expander("Additional source fields"):
                st.write(
                    f"Manufacturer: {recall.get('manufacturer') or 'Not stated'}"
                )
                ids = list(recall.get("gtins") or []) + list(
                    recall.get("barcodes") or []
                )
                st.write(
                    f"GTIN / barcode: {', '.join(ids) or 'Not stated'}"
                )
                if recall.get("official_recall_id"):
                    st.write(
                        f"Official FSAI alert: {recall.get('official_recall_id')}"
                    )
                if recall.get("alert_versions"):
                    st.write(
                        "Alert version(s): "
                        + ", ".join(recall.get("alert_versions") or [])
                    )
                if recall.get("country_of_origin"):
                    st.write(
                        "Country of origin: "
                        + ", ".join(recall.get("country_of_origin") or [])
                    )
                st.write(
                    f"Extraction status: {recall.get('ingestion_status') or 'Not stated'}"
                )
                if recall.get("review_reason"):
                    st.write(f"Source review note: {recall.get('review_reason')}")
                st.caption(
                    f"Source URL: {recall.get('source_url') or 'Not available'}"
                )
                if recall.get("source_note"):
                    st.caption(recall.get("source_note"))

                source_images = _recall_image_urls(recall)
                if len(source_images) > 1:
                    st.markdown("**Other official source image(s)**")
                    for image_index, source_image in enumerate(
                        source_images[1:],
                        2,
                    ):
                        st.markdown(
                            f"[Open source image {image_index}]({source_image})"
                        )

            if recall.get("source_url"):
                st.link_button(
                    "Open official FSAI notice",
                    recall.get("source_url"),
                    use_container_width=True,
                )

            if recall.get("source_type") == "official_fsai_snapshot":
                st.success(
                    "Official FSAI regulatory input. Missing public fields remain empty rather than guessed."
                )

        with agent_col:
            st.subheader("Agent investigation")
            st.caption(
                f"Planner: {getattr(planner, 'display_name', planner.name)}. "
                "The planner chooses bounded investigation tools; "
                "exposure resolution remains deterministic."
            )

            if isinstance(planner, OllamaToolPlanner):
                st.caption(
                    f"Local endpoint: {planner.base_url} · "
                    f"Model: {planner.model} · No cloud LLM required"
                )
                if st.button(
                    "Check local Ollama model",
                    key="check_ollama_connection",
                    use_container_width=True,
                ):
                    health = planner.health()
                    if health["ok"] and health["model_installed"]:
                        st.success(
                            f"Ollama is running and {planner.model} is installed."
                        )
                    elif health["ok"]:
                        st.error(
                            f"Ollama is running, but {planner.model} is not installed. "
                            f"Run: ollama pull {planner.model}"
                        )
                    else:
                        st.error(
                            "Ollama is not reachable. Start Ollama first. "
                            f"Details: {health.get('error')}"
                        )

            if current_role in INVESTIGATION_ROLES:
                run_col, step_col = st.columns(2)
                run_label = (
                    "Run live demo investigation"
                    if live_demo_mode
                    else "Run full investigation"
                )
                if run_col.button(
                    run_label,
                    type="primary",
                    use_container_width=True,
                ):
                    state = SentiOHAgent(ctx, planner).run(rid)

                    ctx.save_cases()
                    st.session_state[key] = state
                    if state.case_id:
                        st.session_state["active_case_id"] = state.case_id
                    st.rerun()

                if step_col.button(
                    "Run one agent step",
                    use_container_width=True,
                ):
                    state = st.session_state.get(key)
                    if state is None or state.status != "ACTIVE":
                        from agent.state import InvestigationState

                        state = InvestigationState(recall_id=rid)
                        state.log("START", "Investigation started.")
                    SentiOHAgent(ctx, planner).step(state)

                    ctx.save_cases()
                    st.session_state[key] = state
                    if state.case_id:
                        st.session_state["active_case_id"] = state.case_id
                    st.rerun()

                update = next(
                    (
                        item
                        for item in _load_updates()
                        if item.get("recall_id") == rid
                    ),
                    None,
                )
                if update and not live_demo_mode:
                    already = st.session_state.get(
                        f"demo_update_applied_{rid}",
                        False,
                    )
                    if already:
                        st.success(
                            "Recall revision applied. Re-run the investigation to update the existing case."
                        )
                    elif st.button(
                        "Simulate recall revision",
                        use_container_width=True,
                    ):
                        _apply_demo_update(st, ctx, rid)
                        st.rerun()
                    st.caption(update.get("description"))
            else:
                st.info(
                    "Agent controls are restricted to Quality & Food Safety, "
                    "Recall / Incident, and Senior Responsible Manager roles."
                )

            state = st.session_state.get(key)
            if state:
                s1, s2, s3 = st.columns(3)
                s1.metric("Status", _label(state.status))
                s2.metric("Steps", state.step)
                s3.metric(
                    "Exposure",
                    _label((state.exposure or {}).get("status")),
                )

                if state.planner_model:
                    st.caption(
                        f"Planner model: {state.planner_model}"
                    )

                if state.status == "ERROR":
                    last_message = (
                        state.events[-1].summary
                        if state.events
                        else state.stop_reason
                    )
                    st.error(
                        f"Agent stopped: {state.stop_reason}. {last_message}"
                    )
                elif (
                    state.investigation_conclusion
                    == "NO_ORGANISATIONAL_EXPOSURE_IDENTIFIED"
                ):
                    st.success(
                        "Investigation complete: no organisational exposure was identified "
                        "from the available company catalogue and lot evidence."
                    )
                    if state.investigated_skus:
                        st.caption(
                            f"Catalogue candidates investigated: {len(state.investigated_skus)}. "
                            f"Stop reason: {state.stop_reason}"
                        )
                    else:
                        st.caption(
                            "No plausible company catalogue candidate was found for this recall."
                        )
                elif state.stop_reason:
                    st.caption(f"Stop reason: {state.stop_reason}")

                if state.reanalysis_context:
                    context = state.reanalysis_context
                    if context.get("mode") == "DIFFERENTIAL":
                        st.info(
                            "Differential re-analysis: product identity was reused from "
                            "the existing case because identity fields did not change. "
                            "Lot/date and operational evidence were refreshed."
                        )
                    else:
                        st.info(
                            "Full re-analysis: product identity evidence changed or "
                            "could not be safely reused."
                        )
                    changed = context.get("changed_fields") or []
                    if changed:
                        st.caption(
                            "Changed recall fields: " + ", ".join(changed)
                        )

                if state.evidence_gap_analysis:
                    gap = state.evidence_gap_analysis
                    st.markdown("#### LLM evidence-gap analysis")
                    st.write(gap.get("summary", ""))
                    missing = gap.get("decisive_missing_evidence") or []
                    if missing:
                        st.markdown(
                            "**Decisive missing evidence:** "
                            + "; ".join(missing)
                        )
                    st.markdown(
                        f"**Priority evidence:** {gap.get('priority_evidence', '')}"
                    )
                    st.write(gap.get("why_this_evidence_first", ""))
                    st.info(gap.get("recommended_evidence_action", ""))
                    st.caption(gap.get("confidence_note", ""))

                if state.llm_recommendation:
                    recommendation = state.llm_recommendation
                    st.markdown("#### LLM recommendation")
                    st.markdown(
                        f"**{recommendation.get('headline', 'Recommendation')}**"
                    )
                    st.write(
                        recommendation.get("justification", "")
                    )
                    st.info(
                        recommendation.get(
                            "recommended_next_step",
                            "",
                        )
                    )
                    st.caption(
                        "This wording is generated from structured evidence. "
                        "It cannot change exposure classification or approve protected actions."
                    )

                if live_demo_mode:
                    tool_rows = _agent_tool_trace_rows(state)
                    if tool_rows:
                        st.markdown("#### Agentic tool-use trace")
                        st.dataframe(
                            tool_rows,
                            use_container_width=True,
                            hide_index=True,
                        )
                        if str(state.planner_source or "").startswith("ollama"):
                            st.caption(
                                "The local LLM selected the approved investigation tools autonomously. "
                                "Matching and exposure classification were performed by deterministic tools."
                            )
                        else:
                            st.caption(
                                "The configured LLM planner selected the approved investigation tools. "
                                "Matching and exposure classification were performed by deterministic tools."
                            )
                    live_case = _case_for_recall(ctx.cases, rid)
                    _render_live_demo_handoff(st, live_case)
            else:
                st.info("This recall has not been investigated in this session.")

        st.header("2. Agent Investigation Timeline")
        state = st.session_state.get(key)
        with st.expander(
            "Open agent tool-call timeline",
            expanded=False,
        ):
            if state:
                timeline = [
                    {
                        "step": event.step,
                        "time": event.time,
                        "event": event.event_type,
                        "tool": event.tool or "",
                    }
                    for event in state.events
                ]
                st.dataframe(
                    timeline,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("The timeline appears after investigation starts.")

    # Establish selected recall/state even if the user has not yet opened Investigation.
    recall_ids = [r["recall_id"] for r in data["recalls"]]
    rid = st.session_state.get(
        "selected_recall_id",
        recall_ids[0],
    )
    if rid not in recall_ids:
        rid = recall_ids[0]
    recall = next(
        r for r in data["recalls"]
        if r["recall_id"] == rid
    )
    key = f"investigation_{rid}"
    state = st.session_state.get(key)

    # ================================================================
    # EXPOSURE / EVIDENCE
    # ================================================================
    with tabs[2]:
        st.header("3. Exposure Analysis & Evidence")
        st.caption(f"Current recall: {rid}")

        scan = _catalogue_scan(data, recall)
        counts = {
            status: sum(row["status"] == status for row in scan)
            for status in [
                "CONFIRMED",
                "POSSIBLE",
                "NOT_AFFECTED",
                "INSUFFICIENT_EVIDENCE",
            ]
        }

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("CONFIRMED", counts["CONFIRMED"])
        e2.metric("POSSIBLE", counts["POSSIBLE"])
        e3.metric("NOT AFFECTED", counts["NOT_AFFECTED"])
        e4.metric(
            "INSUFFICIENT EVIDENCE",
            counts["INSUFFICIENT_EVIDENCE"],
        )

        actionable = [
            row
            for row in scan
            if row["status"]
            in {"CONFIRMED", "POSSIBLE", "NOT_AFFECTED"}
        ]

        st.subheader("Exposure decisions")
        st.dataframe(
            actionable,
            use_container_width=True,
            hide_index=True,
            height=min(320, 38 + 35 * max(len(actionable), 1)),
        )

        with st.expander("View all catalogue decisions"):
            st.dataframe(
                scan,
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("Decision Evidence Panel")
        public_col, internal_col = st.columns(2)

        with public_col:
            st.markdown("#### Recall Source Evidence")
            source_rows = {
                "Authority": recall.get("authority"),
                "Published": recall.get("published_date"),
                "Verified source": (
                    "Yes"
                    if recall.get("is_public_source_verified")
                    else "No"
                ),
                "Product": recall.get("product_name"),
                "Brand": recall.get("brand"),
                "Pack scope": ", ".join(
                    recall.get("pack_sizes") or []
                )
                or "Not stated",
                "Lot scope": ", ".join(
                    recall.get("batch_codes") or []
                )
                or "Not stated",
            }
            for field, value in source_rows.items():
                st.markdown(f"**{field}:** {value or 'Not stated'}")

        with internal_col:
            st.markdown("#### Internal Company Evidence")
            if state and state.exposure:
                internal_rows = {
                    "SKU": state.exposure.get("sku"),
                    "Identity method": state.exposure.get(
                        "product_identity_method"
                    ),
                    "Brand match": state.exposure.get("brand_match"),
                    "Pack match": state.exposure.get(
                        "pack_size_match"
                    ),
                    "Matched lots": ", ".join(
                        state.exposure.get("matched_batches") or []
                    )
                    or "None",
                    "Batch match": state.exposure.get("batch_match"),
                    "Date match": state.exposure.get("date_match"),
                    "Remaining stock": (
                        state.inventory or {}
                    ).get(
                        "total_quantity",
                        state.exposure.get("stock", 0),
                    ),
                    "Dispatched": (
                        state.dispatches or {}
                    ).get(
                        "total_dispatched",
                        state.exposure.get("dispatched", 0),
                    ),
                    "Reason code": state.exposure.get("reason_code"),
                }
                for field, value in internal_rows.items():
                    st.markdown(
                        f"**{field}:** "
                        f"{value if value not in (None, '') else 'Not resolved'}"
                    )
            else:
                st.info(
                    "Run an investigation to populate internal evidence."
                )

        if state and state.evidence_gap_analysis:
            gap = state.evidence_gap_analysis
            st.subheader("Evidence-gap reasoning")
            left_gap, right_gap = st.columns(2)
            with left_gap:
                st.markdown("**What is unresolved**")
                st.write(gap.get("summary", ""))
                for item in gap.get("decisive_missing_evidence") or []:
                    st.write(f"• {item}")
            with right_gap:
                st.markdown("**What to verify first**")
                st.write(gap.get("priority_evidence", ""))
                st.write(gap.get("why_this_evidence_first", ""))
                st.info(gap.get("recommended_evidence_action", ""))

        st.subheader("Exposure Graph")
        with st.expander(
            "Open traceability graph",
            expanded=bool(state and state.exposure),
        ):
            _render_traceability_graph(st, state)

    # ================================================================
    # RESPONSE
    # ================================================================
    with tabs[3]:
        st.header("4. Response Cases")
        st.subheader("My Response Actions")
        st.caption(
            f"Role-scoped workspace for **{current_role}**. "
            "Only actions assigned to, awaiting approval from, or awaiting review by this logged-in role are shown."
        )

        recently_closed_id = st.session_state.get("recently_closed_case_id")
        recently_closed = (
            ctx.cases.get(recently_closed_id)
            if recently_closed_id
            else None
        )
        if recently_closed and recently_closed.get("state") == "CLOSED":
            closure = recently_closed.get("closure") or {}
            progress = case_action_progress(recently_closed)

            with st.container(border=True):
                st.success("CASE CLOSED ✓")
                q1, q2, q3, q4 = st.columns(4)
                q1.metric("Case", recently_closed.get("case_id"))
                q2.metric(
                    "Final exposure",
                    _label(
                        (recently_closed.get("exposure") or {}).get("status")
                    ),
                )
                q3.metric(
                    "Tasks completed",
                    f"{progress['tasks_completed']} / {progress['tasks_total']}",
                )
                q4.metric(
                    "Reviews completed",
                    f"{progress['reviews_completed']} / {progress['reviews_required']}",
                )
                st.write(
                    f"**Closed by:** {closure.get('closed_by') or 'Not recorded'} "
                    f"({closure.get('closed_by_role') or 'role not recorded'})"
                )
                st.write(
                    f"**Closure time:** {closure.get('closed_time') or 'Not recorded'}"
                )
                if closure.get("comment"):
                    st.write(f"**Closure comment:** {closure.get('comment')}")

                st.download_button(
                    "Download Complete Audit Record",
                    data=audit_download_bytes(recently_closed),
                    file_name=audit_export_filename(recently_closed),
                    mime="application/json",
                    use_container_width=True,
                    key=f"download_recent_audit_{recently_closed['case_id']}",
                )
                audit_meta = recently_closed.get("audit_export") or {}
                if audit_meta:
                    st.caption(
                        "Portable audit file: "
                        f"audit_exports/{audit_meta.get('filename')} · "
                        f"SHA-256: {audit_meta.get('sha256')}"
                    )

        with st.expander("Human approval authority matrix (my role)", expanded=False):
            st.dataframe(
                [
                    {
                        "role": current_role,
                        "responsibility": ROLE_DESCRIPTIONS.get(
                            current_role,
                            "No response responsibility description is configured for this role.",
                        ),
                    }
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "Only the logged-in role is shown here. The complete organisation-wide "
                "view remains in the authorised Management overview."
            )

        with st.expander("My role responsibility", expanded=False):
            st.write(
                ROLE_DESCRIPTIONS.get(
                    current_role,
                    "No response responsibility description is configured for this role.",
                )
            )
            st.caption(
                "Actions owned by other roles are hidden from this Response tab. "
                "Management-wide oversight remains available in the Overview tab "
                "for authorised management roles."
            )

        response_scope = response_case_map
        if st.session_state.get("recall_source_mode") == "Demo":
            demo_active_case_id = st.session_state.get("active_case_id")
            if demo_active_case_id in response_case_map:
                response_scope = {
                    demo_active_case_id: response_case_map[demo_active_case_id]
                }
                st.caption(
                    "Demo session focus is active: Response shows only the current "
                    "demo case so approvals from older/open cases do not clutter "
                    "the pitch workflow."
                )

        role_case_map = _role_response_cases(
            response_scope,
            current_role,
        )

        if not role_case_map:
            st.success(
                "No response actions are currently assigned to, awaiting approval "
                "from, or awaiting review by your role."
            )
            st.caption(
                "This does not mean there are no open recall cases. It means no "
                f"current action requires the {current_role} role."
            )
            case = None

        else:
            # Only cases containing a current action for this role appear here.
            role_case_rows = []
            for case_id, role_case in role_case_map.items():
                items = _role_response_items_for_case(
                    role_case,
                    current_role,
                )
                role_case_rows.append(
                    {
                        "case_id": case_id,
                        "recall_id": role_case.get("recall_id"),
                        "exposure": role_case.get("exposure", {}).get("status"),
                        "case_state": role_case.get("state"),
                        "operational_tasks": len(items["operational_task_ids"]),
                        "approval_decisions": len(items["approval_task_ids"]),
                        "reviews": len(items["reviews"]),
                        "closure": "Yes" if items["can_close"] else "No",
                        "my_actions": items["total"],
                    }
                )

            role_case_rows.sort(
                key=lambda row: (
                    -row["my_actions"],
                    row["case_id"],
                )
            )

            with st.expander(
                f"Cases requiring my role ({len(role_case_rows)})",
                expanded=False,
            ):
                st.dataframe(
                    role_case_rows,
                    use_container_width=True,
                    hide_index=True,
                )

            role_case_ids = [row["case_id"] for row in role_case_rows]
            default_role_case = (
                st.session_state.get(
                    f"role_response_case_{current_user['username']}"
                )
                if st.session_state.get(
                    f"role_response_case_{current_user['username']}"
                ) in role_case_ids
                else role_case_ids[0]
            )

            selector_key = (
                f"role_response_case_selector_{current_user['username']}"
            )
            if (
                st.session_state.get(selector_key) is not None
                and st.session_state.get(selector_key) not in role_case_ids
            ):
                st.session_state.pop(selector_key, None)

            selected_role_case_id = st.selectbox(
                "Inspect response case requiring my action",
                role_case_ids,
                index=role_case_ids.index(default_role_case),
                format_func=lambda case_id: (
                    f"{case_id} · "
                    f"{role_case_map[case_id].get('recall_id')} · "
                    f"{_label(role_case_map[case_id].get('exposure', {}).get('status'))}"
                ),
                key=selector_key,
            )
            st.session_state[
                f"role_response_case_{current_user['username']}"
            ] = selected_role_case_id

            case = role_case_map[selected_role_case_id]
            role_items = _role_response_items_for_case(
                case,
                current_role,
            )

            st.subheader("Case context")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Case", case["case_id"])
            c2.metric(
                "Exposure",
                _label(case.get("exposure", {}).get("status")),
            )
            c3.metric("State", _label(case.get("state")))
            c4.metric(
                "Revision",
                case.get("analysis_revision", 1),
            )

            a1, a2, a3, a4 = st.columns(4)
            a1.metric(
                "My assigned tasks",
                len(role_items["operational_task_ids"]),
            )
            a2.metric(
                "My approval decisions",
                len(role_items["approval_task_ids"]),
            )
            a3.metric(
                "My reviews",
                len(role_items["reviews"]),
            )
            a4.metric(
                "Final closure",
                "Required" if role_items["can_close"] else "No",
            )

            st.subheader(f"Actions for {current_role}")

            relevant_tasks = sorted(
                role_items["tasks"],
                key=lambda task: (
                    _priority_rank(task["priority"]),
                    task["created_time"],
                ),
            )

            if relevant_tasks:
                approval_tasks = [
                    task
                    for task in relevant_tasks
                    if task.get("task_id")
                    in role_items["approval_task_ids"]
                ]
                operational_tasks = [
                    task
                    for task in relevant_tasks
                    if task.get("task_id")
                    in role_items["operational_task_ids"]
                ]

                if approval_tasks:
                    st.markdown("### Approval decisions")
                    st.caption(
                        "Only protected actions currently waiting for a decision "
                        "from your role are listed."
                    )
                    for task in approval_tasks:
                        _render_task(
                            st,
                            ctx,
                            case,
                            task,
                            current_user,
                        )

                if operational_tasks:
                    st.markdown("### Operational work")
                    st.caption(
                        "Only tasks assigned to your role are listed. Protected "
                        "tasks remain visible while they wait for the required "
                        "manager approval, but cannot be completed early."
                    )
                    for task in operational_tasks:
                        # Avoid rendering the same card twice if a role is both
                        # operator and approver for an unusual future task.
                        if task.get("task_id") in role_items["approval_task_ids"]:
                            continue
                        _render_task(
                            st,
                            ctx,
                            case,
                            task,
                            current_user,
                        )

            if role_items["reviews"]:
                st.markdown("### Review acknowledgements")
                for review in sorted(
                    role_items["reviews"],
                    key=lambda review: (
                        _priority_rank(review.get("priority")),
                        review.get("created_time") or "",
                    ),
                ):
                    _render_review_action(
                        st,
                        ctx,
                        case,
                        review,
                        current_user,
                    )

            if role_items["can_close"]:
                st.markdown("### Final case closure approval")
                st.info(
                    "All operational response work is resolved. Your role is "
                    "authorised to make the final recorded case-closure decision."
                )
                closure_comment = st.text_input(
                    "Closure comment",
                    "All response tasks and evidence reviewed.",
                    key=(
                        f"role_closure_comment_{case['case_id']}_"
                        f"{current_user['username']}"
                    ),
                )
                if st.button(
                    "Approve and close resolved case",
                    key=(
                        f"role_close_{case['case_id']}_"
                        f"{current_user['username']}"
                    ),
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        def _close(latest_case):
                            close_case(
                                latest_case,
                                current_user["display_name"],
                                closure_comment,
                                actor_role=current_role,
                            )
                            return latest_case

                        closed_case = ctx.mutate_case(
                            case["case_id"],
                            _close,
                        )
                        st.session_state["recently_closed_case_id"] = closed_case["case_id"]
                        st.rerun()
                    except (
                        PermissionError,
                        ValueError,
                    ) as exc:
                        st.error(str(exc))

            persisted_recommendation = case.get("llm_recommendation")
            persisted_gap = case.get("evidence_gap_analysis")
            if persisted_recommendation or persisted_gap:
                with st.expander(
                    "LLM case reasoning",
                    expanded=False,
                ):
                    if persisted_recommendation:
                        st.markdown("**LLM case recommendation**")
                        st.markdown(
                            f"**{persisted_recommendation.get('headline', 'Recommendation')}**"
                        )
                        st.write(
                            persisted_recommendation.get("justification", "")
                        )
                        st.info(
                            persisted_recommendation.get(
                                "recommended_next_step",
                                "",
                            )
                        )
                        st.caption(
                            "This explanation is generated from structured "
                            "evidence. It cannot alter approval authority or execute "
                            "another role's action."
                        )

                    if persisted_gap:
                        st.markdown("**Evidence-gap analysis**")
                        st.write(persisted_gap.get("summary", ""))
                        for item in (
                            persisted_gap.get("decisive_missing_evidence")
                            or []
                        ):
                            st.write(f"• {item}")
                        st.markdown(
                            f"**Priority evidence:** "
                            f"{persisted_gap.get('priority_evidence', '')}"
                        )

            st.header("5. Selected Case Audit Trail")
            st.caption(
                "Selected Case Audit Trail & Lifecycle: DETECTED → ANALYSING → "
                "REVIEW_REQUIRED / CONFIRMED → RESPONDING → RESOLVED → CLOSED"
            )
            with st.expander(
                "Open audit trail and lifecycle",
                expanded=False,
            ):
                st.caption(
                    "Audit evidence is visible only for the case that currently requires "
                    "your role. Actions belonging to other roles remain hidden."
                )
                st.dataframe(
                    case.get("audit_timeline", []),
                    use_container_width=True,
                    hide_index=True,
                )
                if case.get("needs_reanalysis"):
                    st.warning(
                        "Recall evidence changed. This case is marked for re-analysis."
                    )

        closed_case_map = _closed_cases(ctx.cases)
        if (
            closed_case_map
            and current_role in MANAGEMENT_OVERVIEW_ROLES
        ):
            with st.expander(
                f"Closed Case Archive ({len(closed_case_map)})",
                expanded=False,
            ):
                st.caption(
                    "Closed cases remain in runtime/sentioh_cases.db as the live "
                    "case record. Each closed case also has a portable JSON audit "
                    "export under audit_exports/."
                )
                closed_rows = []
                for closed_id, closed_case in closed_case_map.items():
                    closure = closed_case.get("closure") or {}
                    audit_meta = closed_case.get("audit_export") or {}
                    closed_rows.append(
                        {
                            "case_id": closed_id,
                            "recall_id": closed_case.get("recall_id"),
                            "exposure": (
                                closed_case.get("exposure") or {}
                            ).get("status"),
                            "closed_by": closure.get("closed_by"),
                            "closed_by_role": closure.get("closed_by_role"),
                            "closed_time": closure.get("closed_time"),
                            "audit_file": audit_meta.get("filename"),
                        }
                    )
                closed_rows.sort(
                    key=lambda row: row.get("closed_time") or "",
                    reverse=True,
                )
                st.dataframe(
                    closed_rows,
                    use_container_width=True,
                    hide_index=True,
                )

                closed_ids = [row["case_id"] for row in closed_rows]
                archive_case_id = st.selectbox(
                    "Closed case audit",
                    closed_ids,
                    format_func=lambda case_id: (
                        f"{case_id} · "
                        f"{closed_case_map[case_id].get('recall_id')} · "
                        f"{_label((closed_case_map[case_id].get('exposure') or {}).get('status'))}"
                    ),
                    key=f"closed_case_archive_{current_user['username']}",
                )
                archive_case = closed_case_map[archive_case_id]
                archive_meta = archive_case.get("audit_export") or {}

                st.download_button(
                    "Download selected audit JSON",
                    data=audit_download_bytes(archive_case),
                    file_name=audit_export_filename(archive_case),
                    mime="application/json",
                    use_container_width=True,
                    key=f"download_archive_audit_{archive_case_id}",
                )

                if archive_meta:
                    st.caption(
                        f"Stored export: audit_exports/{archive_meta.get('filename')} · "
                        f"Checksum file: {archive_meta.get('checksum_filename')}"
                    )

    # ================================================================
    # VALIDATION
    # ================================================================
    with tabs[4]:
        st.header("6. System Validation & Demo Dataset")
        scenarios = _load_ground_truth()
        metrics = evaluate_scenarios(data, scenarios)

        vleft, vright = st.columns([1.35, 1])

        with vleft:
            st.subheader("System Validation")
            st.caption(
                "Synthetic prototype evaluation only. These are not real-world FSAI/RASFF performance estimates."
            )
            a, b, c, d = st.columns(4)
            a.metric(
                "Test scenarios passed",
                f"{sum(r['pass'] for r in metrics['scenario_results'])} / "
                f"{metrics['scenario_count']}",
            )
            b.metric(
                "Scenario pass rate",
                f"{metrics['accuracy']:.1%}",
            )
            c.metric(
                "Macro F1",
                f"{metrics['macro_f1']:.3f}",
            )
            d.metric(
                "Weighted F1",
                f"{metrics['weighted_f1']:.3f}",
            )

            per_class_rows = [
                {
                    "class": cls,
                    "precision": round(
                        values["precision"],
                        3,
                    ),
                    "recall": round(
                        values["recall"],
                        3,
                    ),
                    "f1": round(values["f1"], 3),
                    "support": values["support"],
                }
                for cls, values
                in metrics["per_class"].items()
            ]
            st.dataframe(
                per_class_rows,
                use_container_width=True,
                hide_index=True,
            )

            with st.expander("Detailed evaluation"):
                st.markdown("**Confusion matrix**")
                st.dataframe(
                    metrics["confusion_matrix"],
                    use_container_width=True,
                    hide_index=True,
                )
                st.markdown("**Scenario-level results**")
                st.dataframe(
                    metrics["scenario_results"],
                    use_container_width=True,
                    hide_index=True,
                )
                st.warning(metrics["warning"])

        with vright:
            st.subheader("Demo Environment")
            st.caption("Official FSAI regulatory data + synthetic company sandbox")

            fsai_validation = validate_fsai_snapshot(ROOT / "regulatory_data")
            f1, f2, f3 = st.columns(3)
            f1.metric(
                "Official FSAI recalls",
                fsai_validation["counts"]["primary_product_scope_recalls"],
            )
            f2.metric(
                "FSAI alert IDs",
                fsai_validation["counts"]["official_alert_ids"],
            )
            f3.metric(
                "FSAI needs review",
                fsai_validation["counts"]["review_required_product_scope_recalls"],
            )
            st.metric(
                "FSAI snapshot validation",
                "PASS" if fsai_validation["ok"] else "FAIL",
            )

            st.markdown("**Synthetic company sandbox**")
            d1, d2, d3 = st.columns(3)
            d1.metric(
                "Products",
                manifest["catalogue_products"],
            )
            d2.metric("Lots", manifest["batch_records"])
            d3.metric("Suppliers", manifest["suppliers"])

            d4, d5, d6 = st.columns(3)
            d4.metric(
                "Inventory",
                manifest["inventory_records"],
            )
            d5.metric(
                "Purchase orders",
                manifest["purchase_orders"],
            )
            d6.metric(
                "Dispatches",
                manifest["dispatch_records"],
            )

            st.metric("Operational sites", manifest["sites"])

            from ingestion.load_data import validate_bundle

            validation = validate_bundle(ROOT / "demo_data")
            st.metric(
                "Company sandbox schema validation",
                "PASS" if validation["ok"] else "FAIL",
            )

            with st.expander("Validation detail"):
                st.markdown("**FSAI regulatory snapshot**")
                st.json(fsai_validation)
                st.markdown("**Synthetic company missing-value report**")
                st.json(validation["missing_values"])

            st.caption(
                "Regulatory input is official FSAI source data. Company catalogue, "
                "lot, inventory, purchase and dispatch evidence is synthetic by design."
            )


# ============================================================================
# Challenge live demo: same agentic investigation, deliberately shorter human
# closure sequence. The Official FSAI tab above is not modified by this path.
# ============================================================================
PITCH_DEMO_RECALL_ID = "PITCH_DEMO_FSAI_2026_38"
PITCH_DEMO_STEPS = [
    "Load verified recall notice",
    "Extract affected product + lot",
    "Resolve against synthetic company records",
    "Trace stock + dispatch evidence",
    "Generate exposure graph + rationale",
    "Require human approval",
]
PITCH_DEMO_TOOL_LABELS = {
    "get_recall": "Load verified recall evidence",
    "resolve_company_exposure": "Resolve company exposure (catalogue + lots + deterministic match)",
    "trace_internal_evidence": "Trace internal evidence (stock + dispatch + purchase history)",
    "search_catalogue": "Search company product catalogue",
    "get_batches": "Retrieve company lot and date records",
    "resolve_exposure": "Resolve organisational exposure",
    "get_inventory": "Trace remaining stock",
    "get_dispatches": "Trace downstream dispatches",
    "get_purchase_history": "Trace upstream purchase evidence",
    "open_response_case": "Open governed response case",
    "request_human_approval": "Stop at the human approval boundary",
}


def _pitch_demo_source_recall(data):
    preferred = next(
        (
            recall
            for recall in (data.get("real_recalls") or [])
            if recall.get("official_recall_id") == "2026.38"
        ),
        None,
    )
    if preferred:
        return preferred
    showcase_ids = {
        item.get("recall_id")
        for item in _load_real_fsai_showcase()
        if item.get("expected_status") == "CONFIRMED"
    }
    return next(
        (
            recall
            for recall in (data.get("real_recalls") or [])
            if recall.get("recall_id") in showcase_ids
        ),
        None,
    )


def _pitch_demo_alias(source_recall):
    recall = dict(source_recall)
    recall["source_recall_id"] = source_recall.get("recall_id")
    recall["recall_id"] = PITCH_DEMO_RECALL_ID
    return recall


def _pitch_demo_case(ctx):
    session_case_id = st_case_id = None
    try:
        # Streamlit is deliberately not imported here; the caller passes its
        # session case through context when available. Kept defensive for tests.
        pass
    except Exception:
        pass
    candidates = [
        case
        for case in ctx.cases.values()
        if case.get("demo_profile") == QUICK_CLOSE_PROFILE
        and not case.get("demo_archived")
        and (case.get("source_recall") or {}).get("official_recall_id") == "2026.38"
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda case: case.get("updated_time") or case.get("created_time") or "",
        reverse=True,
    )[0]


def _pitch_demo_archived_cases(ctx):
    """Return prior Live Demo runs that were reset but retained for audit."""
    rows = [
        case
        for case in ctx.cases.values()
        if case.get("demo_profile") == QUICK_CLOSE_PROFILE
        and case.get("demo_archived")
        and (case.get("source_recall") or {}).get("official_recall_id") == "2026.38"
    ]
    return sorted(
        rows,
        key=lambda case: (case.get("demo_reset") or {}).get("reset_time")
        or case.get("updated_time")
        or case.get("created_time")
        or "",
        reverse=True,
    )


def _pitch_demo_tool_trace_rows(state):
    rows = []
    if not state:
        return rows
    major = 0
    for event in state.events or []:
        if event.event_type != "TOOL_CALL" or not event.tool:
            continue
        major += 1
        observation = event.observation or {}
        rows.append({
            "Step": major,
            "LLM-selected tool": event.tool,
            "Purpose": PITCH_DEMO_TOOL_LABELS.get(event.tool, event.summary),
            "Result": "Completed" if observation.get("ok") else "Stopped",
        })
        for minor, subtool in enumerate(observation.get("subtools") or [], 1):
            rows.append({
                "Step": f"{major}.{minor}",
                "LLM-selected tool": f"↳ {subtool.get('tool')}",
                "Purpose": "Deterministic sub-tool executed inside the selected agent tool",
                "Result": "Completed" if (subtool.get("observation") or {}).get("ok") else "Stopped",
            })
    return rows


def _render_pitch_progress(st, stage, case=None):
    if case and case.get("state") == "CLOSED":
        stage = 6
    cols = st.columns(6)
    for idx, (label, col) in enumerate(zip(PITCH_DEMO_STEPS, cols), 1):
        if idx <= stage:
            marker = "✓"
        elif idx == stage + 1:
            marker = "●"
        else:
            marker = "○"
        col.markdown(f"**{marker} {idx}**")
        col.caption(label)


def _render_demo_approval_task(st, ctx, case, task, current_user, ordinal):
    role = current_user.get("role")
    required_roles = task.get("approval_roles") or []
    required_usernames = task.get("approval_usernames") or []
    assigned_display_name = task.get("assigned_display_name")
    affected_site_name = task.get("affected_site_name")
    dependency_ready = task_dependencies_complete(case, task)
    status = task.get("status")

    with st.container(border=True):
        top_left, top_right = st.columns([4, 1])
        with top_left:
            st.markdown(f"#### Approval {ordinal}: {task.get('title')}")
            authority = assigned_display_name or (' / '.join(required_roles) or 'Not stated')
            if affected_site_name:
                authority += f" · {affected_site_name}"
            st.caption(f"Authorised approver: {authority}")
        with top_right:
            st.metric("Status", _label(status))

        st.write(task.get("description") or "")
        if ordinal == 1:
            st.caption(
                "This containment approval is routed to the manager responsible for the "
                "affected stock location. Approval records that the local manager reviewed "
                "the evidence and completed the required control."
            )
        else:
            st.caption(
                "This is the Incident Manager's final case decision. It unlocks only after "
                "the responsible local manager has completed the first task."
            )
        if task.get("why_generated"):
            st.markdown("**Why this decision is required**")
            st.write(task.get("why_generated"))

        if status == "COMPLETED":
            approval = task.get("approval") or {}
            st.success(
                f"Approved by {approval.get('approver') or 'authorised user'} "
                f"({approval.get('approver_role') or 'role recorded'})."
            )
            if approval.get("comment"):
                st.caption(f"Decision note: {approval.get('comment')}")
            return

        if status == "REJECTED":
            decision = task.get("approval") or {}
            st.error(
                f"Rejected by {decision.get('approver') or 'authorised user'} "
                f"({decision.get('approver_role') or 'role recorded'})."
            )
            if decision.get("comment"):
                st.caption(f"Reason: {decision.get('comment')}")
            return

        if status == "WAITING_FOR_CORRECTIVE_ACTION":
            history = task.get("final_review_history") or []
            latest_request = next((item for item in reversed(history) if item.get("decision") == "FURTHER_ACTION_REQUESTED"), None) or {}
            st.warning("Further action has been requested. Final closure remains locked until revised site evidence is submitted.")
            if latest_request.get("reason"):
                st.caption(f"Incident Manager request: {latest_request['reason']}")
            return

        if not dependency_ready:
            st.info("Locked until the preceding authorised approval is completed.")
            return

        user_allowed = not required_usernames or current_user.get("username") in required_usernames
        if role not in required_roles or not user_allowed:
            next_user = (required_usernames[0] if required_usernames else ("warehouse.manager" if ordinal == 1 else "incident.manager"))
            st.warning(
                "🔒 This action is role-protected. Required role: "
                + " / ".join(required_roles)
                + f". Sign out, then sign in as `{next_user}` to continue the Live Demo."
            )
            return

        note = st.text_input(
            "Decision note",
            value="Reviewed against the verified recall and traced company evidence.",
            key=f"live_demo_decision_{case['case_id']}_{task['task_id']}_{current_user['username']}",
        )
        corrective_reason = None
        if ordinal == 2:
            corrective_reason = st.text_area(
                "If the evidence is not acceptable, state what further action or evidence is required",
                value="",
                placeholder="Example: Provide a verified physical stock count and attach the containment reference.",
                key=f"live_demo_corrective_reason_{case['case_id']}_{task['task_id']}_{current_user['username']}",
            )
        approve_col, reject_col = st.columns(2)
        approve_label = (
            "Approve and complete containment task"
            if ordinal == 1
            else "Approve and close case"
        )
        if approve_col.button(
            approve_label,
            type="primary",
            key=f"live_demo_approve_{case['case_id']}_{task['task_id']}_{current_user['username']}",
            use_container_width=True,
        ):
            try:
                def _approve(latest_case):
                    approve_task(
                        latest_case,
                        task["task_id"],
                        current_user["display_name"],
                        note,
                        approver_role=role,
                        approver_username=current_user.get("username"),
                    )
                    # The second approval is the Incident Manager's explicit
                    # closure authorisation. Once the two approvals resolve the
                    # case, close it immediately under that same authorised actor.
                    if (
                        ordinal == 2
                        and role == RECALL_INCIDENT_MANAGER
                        and latest_case.get("state") == "RESOLVED"
                    ):
                        close_case(
                            latest_case,
                            actor=current_user["display_name"],
                            actor_role=role,
                            comment=(
                                "Live Demo case closed after the two required "
                                "role-based approvals were recorded."
                            ),
                        )
                    return latest_case

                updated = ctx.mutate_case(case["case_id"], _approve)
                ctx.cases[case["case_id"]] = updated
                st.rerun()
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))

        secondary_label = "Reject containment" if ordinal == 1 else "Request further action"
        if reject_col.button(
            secondary_label,
            key=f"live_demo_reject_{case['case_id']}_{task['task_id']}_{current_user['username']}",
            use_container_width=True,
        ):
            try:
                if ordinal == 2:
                    def _request_more(latest_case):
                        request_demo_corrective_action(
                            latest_case,
                            task["task_id"],
                            current_user["display_name"],
                            role,
                            corrective_reason,
                        )
                        return latest_case
                    updated = ctx.mutate_case(case["case_id"], _request_more)
                else:
                    def _reject(latest_case):
                        reject_task(
                            latest_case,
                            task["task_id"],
                            current_user["display_name"],
                            note,
                            approver_role=role,
                            approver_username=current_user.get("username"),
                        )
                        return latest_case
                    updated = ctx.mutate_case(case["case_id"], _reject)
                ctx.cases[case["case_id"]] = updated
                st.rerun()
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))


def _render_live_demo_page(st, current_user=None):
    _inject_dashboard_css(st)
    ctx = get_context(st)
    data = ctx.data
    planner = _planner(st)
    demo_planner = _fast_demo_planner(planner)

    if current_user is None:
        current_user = {
            "username": "system",
            "display_name": "System User",
            "role": RECALL_INCIDENT_MANAGER,
        }

    # Pre-warm the local model once when the Incident Manager opens the Live Demo.
    # This moves model-loading latency away from the Run investigation click.
    if (
        isinstance(demo_planner, OllamaToolPlanner)
        and current_user.get("role") == RECALL_INCIDENT_MANAGER
        and not st.session_state.get("pitch_demo_ollama_warmed")
        and os.getenv("SENTIOH_DEMO_PREWARM", "1").strip() != "0"
    ):
        st.session_state["pitch_demo_ollama_warmed"] = bool(demo_planner.warmup())

    st.header("Live Demo · Agentic recall trace")
    st.caption(
        "One-page challenge demonstration: a genuine FSAI recall is investigated by the "
        "LLM agent, resolved against the synthetic company sandbox, and stopped at "
        "two authenticated human approvals."
    )
    st.caption(
        f"Signed in as **{current_user['display_name']}** · {current_user['role']}"
    )

    source_recall = _pitch_demo_source_recall(data)
    if source_recall is None:
        st.error("No prepared confirmed FSAI showcase recall is available for the live demo.")
        return

    stage = int(st.session_state.get("pitch_demo_stage", 1))
    state = st.session_state.get("pitch_demo_state")
    case_id = st.session_state.get("pitch_demo_case_id")
    case = ctx.cases.get(case_id) if case_id else None
    if case and case.get("demo_archived"):
        case = None
        case_id = None
    if case is None:
        case = _pitch_demo_case(ctx)
        if case:
            case_id = case.get("case_id")
            st.session_state["pitch_demo_case_id"] = case_id
            if case.get("state") == "CLOSED":
                stage = 6
            elif case.get("tasks"):
                stage = max(stage, 5)

    _render_pitch_progress(st, stage, case)

    toolbar_left, toolbar_right = st.columns([5, 1.25])
    with toolbar_left:
        st.caption(
            "The regulatory notice is genuine FSAI data from the bundled verified snapshot. "
            "Company catalogue, lot, inventory and dispatch records are synthetic challenge data."
        )
    with toolbar_right:
        if current_user.get("role") == RECALL_INCIDENT_MANAGER:
            if st.button("Reset live demo", key="pitch_demo_reset", use_container_width=True):
                for existing_id, existing_case in list(ctx.cases.items()):
                    if (
                        existing_case.get("demo_profile") == QUICK_CLOSE_PROFILE
                        and not existing_case.get("demo_archived")
                        and (existing_case.get("source_recall") or {}).get("official_recall_id") == "2026.38"
                    ):
                        ctx.archive_case_for_audit(
                            existing_id,
                            actor=current_user.get("display_name") or current_user.get("username") or "SYSTEM",
                            actor_role=current_user.get("role"),
                            reason=(
                                "Live Demo reset by an authorised Incident Manager. "
                                "The case is removed from the active demo but retained as a "
                                "Reset / Deleted audit record."
                            ),
                        )
                for key in [
                    "pitch_demo_stage",
                    "pitch_demo_state",
                    "pitch_demo_case_id",
                    "pitch_demo_started",
                    "active_case_id",
                ]:
                    st.session_state.pop(key, None)
                st.rerun()

    archived_demo_cases = _pitch_demo_archived_cases(ctx)
    if archived_demo_cases:
        with st.expander(
            f"Reset / Deleted Demo Cases · retained for audit ({len(archived_demo_cases)})",
            expanded=False,
        ):
            archived_rows = []
            for archived_case in archived_demo_cases:
                reset_meta = archived_case.get("demo_reset") or {}
                archived_rows.append({
                    "case_id": archived_case.get("case_id"),
                    "status": "Reset / Deleted from Live Demo",
                    "case state at reset": reset_meta.get("previous_state") or archived_case.get("state"),
                    "exposure": reset_meta.get("previous_exposure_status")
                        or (archived_case.get("exposure") or {}).get("status"),
                    "reset by": reset_meta.get("reset_by"),
                    "role": reset_meta.get("reset_by_role"),
                    "reset time": reset_meta.get("reset_time"),
                })
            st.dataframe(archived_rows, use_container_width=True, hide_index=True)
            selected_archived = st.selectbox(
                "Audit record",
                [case.get("case_id") for case in archived_demo_cases],
                format_func=lambda archived_id: (
                    f"{archived_id} · "
                    f"{(ctx.cases[archived_id].get('demo_reset') or {}).get('previous_state') or ctx.cases[archived_id].get('state')} · "
                    "retained for audit"
                ),
                key=f"live_demo_archived_case_{current_user.get('username')}",
            )
            archived_case = ctx.cases[selected_archived]
            st.download_button(
                "Download reset/deleted case audit JSON",
                data=audit_download_bytes(archived_case),
                file_name=audit_export_filename(archived_case),
                mime="application/json",
                use_container_width=True,
                key=f"download_live_demo_archived_{selected_archived}",
            )
            st.caption(
                "Reset is a logical deletion from the active demo only. The original case, "
                "decisions, tool history and audit timeline remain stored for traceability."
            )

    # ------------------------------------------------------------------
    # Step 1: verified recall + Incident Manager starts the investigation
    # ------------------------------------------------------------------
    st.markdown("### 1. Load verified recall notice")
    if case is None:
        st.warning(
            "🚨 NEW VERIFIED FSAI RECALL · Recall / Incident Manager action required. "
            "Review the alert below and start the agentic investigation."
        )
        if current_user.get("role") == RECALL_INCIDENT_MANAGER:
            st.success(
                "You are signed in as the authorised Recall / Incident Manager. "
                "Run the investigation after reviewing the recall details."
            )
        else:
            st.info(
                "The recall is visible for awareness, but only the Recall / Incident "
                "Manager can initiate this Live Demo investigation."
            )
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Verified source", "FSAI ✓")
        c2.metric("Official alert", source_recall.get("official_recall_id") or "Not stated")
        c3.metric("Date of alert", source_recall.get("published_date") or "Not stated")
        st.markdown(f"**Product:** {source_recall.get('product_name') or 'Not stated'}")
        st.markdown(
            "**Affected lot(s):** "
            + (", ".join(source_recall.get("batch_codes") or []) or "Not stated")
        )
        st.markdown(f"**Hazard / reason:** {source_recall.get('hazard') or 'Not stated'}")
        if source_recall.get("source_url"):
            st.link_button("Open official FSAI notice", source_recall.get("source_url"))

        if stage <= 1 and case is None:
            st.divider()
            st.markdown("#### Start agentic investigation")
            st.write(
                "The Incident Manager initiates the investigation. The LLM then "
                "autonomously selects approved tools to gather evidence and determine what "
                "the organisation should do next."
            )
            if current_user.get("role") != RECALL_INCIDENT_MANAGER:
                st.warning(
                    "🔒 Investigation initiation is restricted to the Recall / Incident Manager "
                    "for this live demonstration. Sign out and use that authorised account to start."
                )
            elif st.button(
                "Run investigation",
                type="primary",
                key="pitch_demo_run_analysis",
                use_container_width=True,
            ):
                # Remove any previous prepared live-demo alias from in-memory recalls.
                data["recalls"] = [
                    item for item in data.get("recalls", [])
                    if item.get("recall_id") != PITCH_DEMO_RECALL_ID
                ]
                alias_recall = _pitch_demo_alias(source_recall)
                data.setdefault("recalls", []).append(alias_recall)
                try:
                    with st.status(
                        "SentiOH is investigating the recall through company evidence…",
                        expanded=True,
                    ) as status:
                        st.write("🤖 Online LLM is the active agentic planner")
                        st.caption(
                            "The LLM autonomously selects which approved high-level tool to call next. "
                            "Each selected tool executes deterministic evidence sub-tools and preserves "
                            "their audit trace."
                        )
                        shown_tools = set()

                        def _show_agent_step(current_state):
                            # A terminal tool call can be followed immediately by
                            # LLM enrichment/audit events, so inspect all events and
                            # render only tool calls not already shown. This keeps the
                            # live trace complete without affecting agent behaviour.
                            for event in current_state.events:
                                if event.event_type != "TOOL_CALL" or not event.tool:
                                    continue
                                marker = (event.step, event.tool)
                                if marker in shown_tools:
                                    continue
                                shown_tools.add(marker)
                                label = PITCH_DEMO_TOOL_LABELS.get(event.tool, event.tool)
                                st.write(f"✓ LLM selected `{event.tool}` · {label}")
                                for subtool in (event.observation or {}).get("subtools") or []:
                                    sub_name = subtool.get("tool")
                                    sub_ok = (subtool.get("observation") or {}).get("ok")
                                    st.caption(
                                        f"   ↳ {'✓' if sub_ok else '✗'} {sub_name} · deterministic sub-tool"
                                    )

                        live_state = SentiOHAgent(
                            ctx,
                            demo_planner,
                            enrichment_mode="recommendation_only",
                        ).run(
                            PITCH_DEMO_RECALL_ID,
                            on_step=_show_agent_step,
                        )
                        if live_state.status == "ERROR":
                            status.update(
                                label="Investigation stopped before completion",
                                state="error",
                                expanded=True,
                            )
                            st.error(live_state.stop_reason or "Agent investigation failed.")
                            st.session_state["pitch_demo_state"] = live_state
                            return
                        if (live_state.exposure or {}).get("status") != "CONFIRMED":
                            status.update(
                                label="Prepared scenario did not resolve as CONFIRMED",
                                state="error",
                                expanded=True,
                            )
                            st.error(
                                "The prepared demo scenario no longer produces the expected "
                                "confirmed match. Reset the demo data before presenting."
                            )
                            st.session_state["pitch_demo_state"] = live_state
                            return

                        pitch_case = streamline_existing_confirmed_case_for_demo(
                            ctx,
                            live_state.case_id,
                            source_recall=source_recall,
                        )
                        ctx.save_cases()
                        st.write("✓ Confirmed product and lot exposure")
                        st.write("✓ Collected inventory and downstream dispatch evidence")
                        st.write("✓ Generated an evidence-backed rationale")
                        st.write("✓ Assigned the containment task to the Warehouse Manager")
                        st.write("✓ Stopped at the role-protected human decision boundary")
                        status.update(
                            label="Investigation complete · human decisions required",
                            state="complete",
                            expanded=False,
                        )

                    st.session_state["pitch_demo_state"] = live_state
                    st.session_state["pitch_demo_case_id"] = pitch_case["case_id"]
                    st.session_state["active_case_id"] = pitch_case["case_id"]
                    st.session_state["pitch_demo_stage"] = 5
                    st.rerun()
                finally:
                    data["recalls"] = [
                        item for item in data.get("recalls", [])
                        if item.get("recall_id") != PITCH_DEMO_RECALL_ID
                    ]

    state = st.session_state.get("pitch_demo_state") or state
    case_id = st.session_state.get("pitch_demo_case_id") or case_id
    case = ctx.cases.get(case_id) if case_id else case
    if not state or not case:
        return

    exposure = state.exposure or case.get("exposure") or {}
    matched_batches = exposure.get("matched_batches") or (
        [exposure.get("batch")] if exposure.get("batch") else []
    )

    # ------------------------------------------------------------------
    # Step 2: extraction
    # ------------------------------------------------------------------
    st.markdown("### 2. Extract affected product + lot")
    with st.container(border=True):
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("Product", source_recall.get("product_name") or "Not stated")
        x2.metric("Affected lot", ", ".join(source_recall.get("batch_codes") or []) or "Not stated")
        date_scope = list(source_recall.get("use_by") or []) + list(source_recall.get("best_before") or [])
        x3.metric("Date scope", ", ".join(date_scope) or "Not stated")
        x4.metric("Hazard / reason", source_recall.get("hazard") or "Not stated")
        st.caption(
            "These fields originate from verified regulatory ingestion. Missing public "
            "fields remain empty rather than being invented by the LLM."
        )

    # ------------------------------------------------------------------
    # Step 3: deterministic company resolution
    # ------------------------------------------------------------------
    st.markdown("### 3. Resolve against synthetic company records")
    with st.container(border=True):
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Exposure", _label(exposure.get("status")))
        r2.metric("Internal SKU", exposure.get("sku") or "Not resolved")
        r3.metric("Product match", "Exact ✓" if exposure.get("product_name_match") else "No")
        r4.metric("Lot match", "Exact ✓" if exposure.get("batch_match") else "No")
        st.success(exposure.get("reason") or "Product and lot evidence matched company records.")
        st.caption(f"Deterministic reason code: {exposure.get('reason_code') or 'Not stated'}")

    # ------------------------------------------------------------------
    # Step 4: traceability evidence
    # ------------------------------------------------------------------
    st.markdown("### 4. Trace stock + dispatch evidence")
    with st.container(border=True):
        inventory_records = (state.inventory or {}).get("records", [])
        dispatch_records = (state.dispatches or {}).get("records", [])
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Remaining affected stock", exposure.get("stock", 0))
        t2.metric("Affected units dispatched", exposure.get("dispatched", 0))
        t3.metric(
            "Stock locations",
            len({row.get("site") or row.get("site_code") for row in inventory_records}),
        )
        t4.metric("Affected dispatches", len(dispatch_records))

        left, right = st.columns(2)
        with left:
            st.markdown("**Current stock evidence**")
            if inventory_records:
                st.dataframe(
                    [
                        {
                            "site": row.get("site") or row.get("site_code"),
                            "lot": row.get("batch_code"),
                            "quantity": row.get("quantity"),
                        }
                        for row in inventory_records
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No remaining affected stock record was returned.")
        with right:
            st.markdown("**Dispatch evidence**")
            if dispatch_records:
                st.dataframe(
                    [
                        {
                            "dispatch": row.get("dispatch_id"),
                            "recipient": row.get("customer"),
                            "lot": row.get("batch_code"),
                            "quantity": row.get("quantity"),
                            "date": row.get("date"),
                        }
                        for row in dispatch_records
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No affected downstream dispatch record was returned.")

    # ------------------------------------------------------------------
    # Step 5: graph + LLM trace and rationale
    # ------------------------------------------------------------------
    st.markdown("### 5. Generate exposure graph + rationale")
    with st.container(border=True):
        st.markdown("#### Exposure and traceability graph")
        st.caption(
            "Verified recall → matched company product/lot → inventory, purchase and downstream dispatch evidence."
        )
        _render_traceability_graph(st, state, presentation=True)

    rationale_col, trace_col = st.columns([1, 1.2])
    with rationale_col:
        with st.container(border=True):
            st.markdown("#### Why SentiOH recommends action")
            st.write(exposure.get("reason") or "Verified evidence confirms organisational exposure.")
            if exposure.get("stock", 0):
                st.write(f"• **{exposure.get('stock', 0)} unit(s)** of the affected lot remain in stock.")
            if exposure.get("dispatched", 0):
                st.write(f"• **{exposure.get('dispatched', 0)} unit(s)** were dispatched downstream.")

            planner_name = state.planner_model or getattr(planner, "model", None) or "configured planner"
            if state.planner_source == "ollama":
                st.success(f"Agentic planner: local Ollama · {planner_name}")
            elif state.planner_model:
                st.success(f"Agentic planner: online LLM · {planner_name}")
            elif state.planner_source:
                st.info(f"Agentic planner source: {state.planner_source} · {planner_name}")

            if state.llm_recommendation:
                st.markdown("**LLM evidence synthesis**")
                st.write(state.llm_recommendation.get("justification", ""))
                if state.llm_recommendation.get("recommended_next_step"):
                    st.info(state.llm_recommendation.get("recommended_next_step"))

    with trace_col:
        with st.container(border=True):
            st.markdown("#### Agentic LLM tool trace")
            tool_rows = _pitch_demo_tool_trace_rows(state)
            if tool_rows:
                st.dataframe(tool_rows, use_container_width=True, hide_index=True)
                st.caption(
                    "The LLM selected the approved tool sequence. Matching and exposure "
                    "classification remain deterministic and human authority is policy-enforced."
                )
            else:
                st.info("No tool trace is available for this run.")

            reference = case.get("demo_full_workflow_reference") or {}
            if reference:
                st.caption(
                    "The Official FSAI tab retains the full response workflow: the normal "
                    f"confirmed case would create {reference.get('task_count', 0)} operational task(s) and "
                    f"{reference.get('review_count', 0)} review item(s). The Live Demo keeps "
                    "only two authorised decisions active for presentation."
                )

    # ------------------------------------------------------------------
    # Step 6: exactly two role-based approvals, then closure
    # ------------------------------------------------------------------
    st.markdown("### 6. Require human approval")
    st.caption(
        "The demo uses exactly two sequential authorised decisions. First, the manager "
        "responsible for the affected stock location confirms containment. Second, the "
        "Recall / Incident Manager reviews the evidence and closes the case."
    )
    tasks = case.get("tasks") or []
    core_tasks = [task for task in tasks if not task.get("demo_corrective_action")]
    corrective_tasks = [task for task in tasks if task.get("demo_corrective_action")]
    if len(core_tasks) != 2:
        st.error("The live-demo case does not contain the expected two core approval tasks.")
        return
    core_tasks.sort(key=lambda task: task.get("demo_approval_ordinal") or (1 if task.get("title", "").startswith("Confirm and complete") else 2))
    first_task, second_task = core_tasks
    first_status = first_task.get("status")
    second_status = second_task.get("status")
    if first_status not in {"COMPLETED", "REJECTED"}:
        first_user = first_task.get("assigned_username") or "warehouse.manager"
        first_name = first_task.get("assigned_display_name") or "Warehouse Manager"
        first_site = first_task.get("affected_site_name")
        first_role = (first_task.get("approval_roles") or [first_task.get("assigned_to")])[0]
        if (
            current_user.get("role") == first_role
            and (not first_task.get("approval_usernames") or current_user.get("username") == first_user)
        ):
            st.warning(
                f"📣 {first_name.upper()} TASK ASSIGNED TO YOU · Confirm the affected stock "
                "containment below. This action cannot be completed by the Incident Manager."
            )
        else:
            site_text = f" for {first_site}" if first_site else ""
            st.info(
                f"📣 NEXT HUMAN: {first_name}{site_text} · The agentic investigation is complete. "
                f"Sign out and sign in as `{first_user}` to perform the assigned task."
            )
    elif first_status == "COMPLETED" and second_status == "WAITING_FOR_CORRECTIVE_ACTION":
        pending_corrective = next((item for item in reversed(corrective_tasks) if item.get("status") == "PENDING"), None)
        if pending_corrective:
            target_user = pending_corrective.get("assigned_username") or "site.manager"
            target_name = pending_corrective.get("assigned_display_name") or "Site Manager"
            if current_user.get("username") == target_user:
                st.warning("📣 CORRECTIVE ACTION ASSIGNED TO YOU · The Incident Manager requires further evidence before this recall can be closed.")
            else:
                st.info(f"📣 NEXT HUMAN: {target_name} · Further evidence is required. Sign out and sign in as `{target_user}` to submit the corrective evidence.")
    elif first_status == "COMPLETED" and second_status not in {"COMPLETED", "REJECTED"}:
        if current_user.get("role") == RECALL_INCIDENT_MANAGER:
            st.warning(
                "📣 INCIDENT MANAGER FINAL ACTION · Local containment is complete. "
                "Review the evidence and either close the case or request further site action."
            )
        else:
            st.info(
                "📣 NEXT HUMAN: Recall / Incident Manager · The responsible local manager has "
                "completed the containment task. Sign out and sign in as `incident.manager` "
                "for final evidence review."
            )

    # A rejection is an escalation, not a terminal state. Make that hand-off
    # explicit in the Live Demo and let the Incident Manager re-issue the
    # containment decision to the responsible site manager.
    if first_status == "REJECTED":
        rejection = first_task.get("approval") or {}
        st.error(
            "🚨 ESCALATION REQUIRED · The local containment decision was rejected. "
            "The recall remains open and the final closure approval is locked."
        )
        with st.container(border=True):
            st.markdown("#### Rejection escalation · Incident Manager action required")
            st.write(
                f"**Rejected by:** {rejection.get('approver') or 'authorised site manager'}"
            )
            st.write(f"**Reason:** {rejection.get('comment') or 'No reason recorded'}")
            st.caption(
                "Exposure remains CONFIRMED. The Incident Manager must review the rejection "
                "and re-assign the containment task before the case can progress."
            )
            if current_user.get("role") == RECALL_INCIDENT_MANAGER:
                current_site = first_task.get("affected_site_code")
                site_owner = DEMO_SITE_APPROVERS.get(current_site)
                if site_owner:
                    st.write(
                        f"**Re-assign to:** {site_owner['display_name']} "
                        f"(`{site_owner['username']}`)"
                    )
                    st.caption(
                        "The containment task can only be re-issued to the manager "
                        "responsible for the affected stock location. Unrelated city "
                        "managers are not shown or selectable."
                    )
                    if st.button(
                        "Review escalation and re-assign containment task",
                        type="primary",
                        use_container_width=True,
                        key=f"demo_reassign_{case['case_id']}_{first_task['task_id']}",
                    ):
                        try:
                            def _reassign(latest_case):
                                reassign_rejected_demo_containment(
                                    latest_case,
                                    first_task["task_id"],
                                    current_user["display_name"],
                                    current_user["role"],
                                    target_site_code=current_site,
                                )
                                return latest_case
                            updated = ctx.mutate_case(case["case_id"], _reassign)
                            ctx.cases[case["case_id"]] = updated
                            st.rerun()
                        except (PermissionError, ValueError) as exc:
                            st.error(str(exc))
                else:
                    st.error(
                        "The affected site has no authorised demo manager configured. "
                        "Re-assignment is blocked until site ownership is resolved."
                    )
            else:
                st.info(
                    "📣 NEXT HUMAN: Recall / Incident Manager · Sign out and sign in as "
                    "`incident.manager` to review the rejection and re-assign the task."
                )

    _render_demo_approval_task(st, ctx, case, first_task, current_user, 1)
    # Refresh after rendering the first card so corrective work and final review reflect persistence.
    case = ctx.cases.get(case["case_id"], case)
    tasks = case.get("tasks") or tasks
    corrective_tasks = [task for task in tasks if task.get("demo_corrective_action")]
    for corrective in corrective_tasks:
        with st.container(border=True):
            st.markdown(f"#### Corrective action round {corrective.get('corrective_round')}: Site evidence resubmission")
            st.caption(f"Requested because: {corrective.get('request_reason') or corrective.get('why_generated') or 'Further evidence required'}")
            st.write(corrective.get("description") or "")
            if corrective.get("status") == "COMPLETED":
                submission = corrective.get("corrective_submission") or {}
                st.success(f"Revised evidence submitted by {submission.get('submitted_by') or 'site manager'}.")
                if submission.get("evidence_note"):
                    st.write(f"**Submitted evidence:** {submission['evidence_note']}")
            elif current_user.get("username") == corrective.get("assigned_username"):
                evidence_note = st.text_area(
                    "Corrective action taken / revised evidence",
                    placeholder="Describe the corrective action and the evidence now available for Incident Manager review.",
                    key=f"demo_corrective_evidence_{case['case_id']}_{corrective['task_id']}_{current_user['username']}",
                )
                if st.button(
                    "Submit corrective evidence to Incident Manager",
                    type="primary",
                    use_container_width=True,
                    key=f"demo_corrective_submit_{case['case_id']}_{corrective['task_id']}_{current_user['username']}",
                ):
                    try:
                        def _submit_corrective(latest_case):
                            submit_demo_corrective_evidence(
                                latest_case,
                                corrective["task_id"],
                                current_user["display_name"],
                                current_user["role"],
                                current_user.get("username"),
                                evidence_note,
                            )
                            return latest_case
                        updated = ctx.mutate_case(case["case_id"], _submit_corrective)
                        ctx.cases[case["case_id"]] = updated
                        st.rerun()
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
            else:
                st.info(f"Waiting for {corrective.get('assigned_display_name') or 'the responsible site manager'} (`{corrective.get('assigned_username') or 'site.manager'}`) to submit revised evidence.")

    case = ctx.cases.get(case["case_id"], case)
    tasks = case.get("tasks") or tasks
    second_task = next((task for task in tasks if task.get("demo_approval_ordinal") == 2), second_task)
    _render_demo_approval_task(st, ctx, case, second_task, current_user, 2)

    case = ctx.cases.get(case["case_id"], case)
    if case.get("state") == "CLOSED":
        st.session_state["pitch_demo_stage"] = 6
        st.success("CASE CLOSED ✓ · Both authorised approvals are recorded in the audit trail.")
        final1, final2, final3, final4 = st.columns(4)
        final1.metric("Verified recall", "1")
        final2.metric("Matched lot", ", ".join(matched_batches) or "1")
        final3.metric("Approvals", "2 / 2")
        final4.metric("Case state", "Closed")
        closure = case.get("closure") or {}
        st.caption(
            f"Closed by {closure.get('closed_by') or 'authorised Incident Manager'} · "
            f"{closure.get('closed_time') or 'timestamp recorded'}"
        )
        try:
            st.download_button(
                "Download Complete Audit Record",
                data=audit_download_bytes(case),
                file_name=audit_export_filename(case),
                mime="application/json",
                key=f"live_demo_audit_{case['case_id']}",
            )
        except Exception:
            st.caption("The audit export is retained in the case store after closure.")


def render(st, current_user=None):
    """Top-level two-tab challenge experience with the brand header above navigation."""
    st.session_state.pop("prototype_view_mode", None)
    _inject_dashboard_css(st)
    render_brand_header(st, width=650)
    top_tabs = st.tabs(["Live Demo", "Official FSAI"])
    with top_tabs[0]:
        _render_live_demo_page(st, current_user=current_user)
    with top_tabs[1]:
        _render_official_fsai(st, current_user=current_user)
