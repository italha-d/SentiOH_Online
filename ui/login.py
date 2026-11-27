from __future__ import annotations

from auth.service import authenticate, available_accounts
from .branding import render_brand_header
from storage.case_store import CaseStore
from workflow.action_center import (
    human_action_summary,
    personal_action_summary,
)
from workflow.approvals import approve_task, reject_task, complete_task
from workflow.reviews import mark_reviewed
from workflow.quick_demo import submit_demo_corrective_evidence
from workflow.roles import ROLE_DESCRIPTIONS


def _open_cases(active_case_id=None):
    cases = {
        case_id: case
        for case_id, case in CaseStore().load_cases().items()
        if case.get("state") != "CLOSED"
    }
    if active_case_id and active_case_id in cases:
        return {active_case_id: cases[active_case_id]}
    return cases


def _active_demo_handoff_case(cases):
    """Return the most recent active Live Demo case that has a governed hand-off.

    This is deliberately inferred from persisted case state instead of relying on
    Streamlit session state, so the hand-off survives sign-out and browser reruns.
    """
    demo_cases = [
        case for case in cases.values()
        if case.get("demo_profile") == "QUICK_CLOSE_TWO_APPROVALS"
        and not case.get("demo_archived")
        and case.get("state") != "CLOSED"
    ]
    if not demo_cases:
        return None
    demo_cases.sort(
        key=lambda case: case.get("updated_time") or case.get("created_time") or "",
        reverse=True,
    )
    return demo_cases[0]


def _demo_handoff_rows(cases):
    """Resolve the single next human hand-off for the prepared Live Demo.

    The login page should always make an escalation or governed approval hand-off
    visible after sign-out, even when Streamlit session-state keys have been reset.
    """
    case = _active_demo_handoff_case(cases)
    if not case:
        return []

    tasks = list(case.get("tasks") or [])
    primary = [task for task in tasks if task.get("demo_approval_ordinal") in {1, 2}]
    first = next((task for task in primary if task.get("demo_approval_ordinal") == 1), None)
    second = next((task for task in primary if task.get("demo_approval_ordinal") == 2), None)
    if not first or not second:
        return []

    def row(role, approvals=0, reviews=0, work=0):
        total = approvals + reviews + work
        return {
            "role": role,
            "approvals / rejections": approvals,
            "mark as reviewed": reviews,
            "mark work done": work,
            "total actions": total,
        }

    if first.get("status") == "REJECTED":
        return [row("Recall / Incident Manager", reviews=1)]

    if first.get("status") == "WAITING_FOR_APPROVAL":
        return [row(first.get("assigned_to") or "Store / Site Manager", approvals=1)]

    if first.get("status") == "COMPLETED":
        if second.get("status") == "WAITING_FOR_CORRECTIVE_ACTION":
            corrective = next(
                (task for task in reversed(tasks)
                 if task.get("demo_corrective_action") and task.get("status") == "PENDING"),
                None,
            )
            if corrective:
                return [row(corrective.get("assigned_to") or "Store / Site Manager", work=1)]
        if second.get("status") == "WAITING_FOR_APPROVAL":
            return [row("Recall / Incident Manager", approvals=1)]

    return []


def _public_status(active_case_id=None):
    """
    Aggregate, non-sensitive workflow counts for the sign-in page.
    No product, customer, supplier, batch or case identifiers are exposed.
    """
    cases = _open_cases(active_case_id)
    summary = human_action_summary(cases)
    return {
        "active_cases": len(cases),
        "human_actions_pending": summary["total_human_actions_left"],
        "critical_approvals_pending": summary[
            "critical_approval_decisions_left"
        ],
        "approvals_left": summary["approval_decisions_left"],
        "reviews_left": summary["reviews_left"],
        "operational_tasks_left": summary["operational_tasks_left"],
    }


def _public_role_attention_rows(active_case_id=None):
    """
    Show only which organisational roles still need to act and how many actions
    are waiting. This intentionally excludes case/product/customer details.
    """
    cases = _open_cases(active_case_id)

    # For the prepared demo, show the single persisted next-human hand-off first.
    # This survives sign-out because it is derived from the stored case, not only
    # from Streamlit session state.
    demo_rows = _demo_handoff_rows(cases)
    if demo_rows:
        return demo_rows

    rows = []
    for role in ROLE_DESCRIPTIONS:
        personal = personal_action_summary(cases, role)
        if personal["total"]:
            rows.append({
                "role": role,
                "approvals / rejections": personal["approval_count"],
                "mark as reviewed": personal["review_count"],
                "mark work done": personal["work_count"],
                "total actions": personal["total"],
            })
    rows.sort(key=lambda row: (-row["total actions"], row["role"]))
    return rows


def require_login(st):
    """Require an authorised demo account before any case/workflow UI is shown.

    The pre-login screen exposes only role-level action counts so the demo
    hand-off remains visible after sign-out. Case, recall, product, lot,
    supplier and customer details remain behind authentication.
    """
    user = st.session_state.get("auth_user")
    if user:
        return user

    render_brand_header(st, width=650)
    st.subheader("From food-safety alert to evidence-backed action")
    st.caption("Authorised user sign-in")
    st.caption(
        "Sign in with an authorised SentiOH role to view recall evidence, "
        "run investigations and complete assigned human actions."
    )

    # Keep the sign-in screen free of sensitive case details, but preserve the
    # role-level hand-off view used during the demo. After an investigation
    # allocates human actions, signing out should still make it immediately
    # clear which authorised role needs to act next.
    demo_active_case_id = (
        st.session_state.get("active_case_id")
        if st.session_state.get("recall_source_mode") == "Demo"
        else None
    )
    role_rows = _public_role_attention_rows(demo_active_case_id)
    if role_rows:
        st.warning(
            "Human action is waiting. Sign in with the relevant authorised "
            "account to continue the governed response."
        )
        st.markdown("### Who needs to act")
        st.dataframe(
            role_rows,
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Only role-level action counts are shown before sign-in. "
            "Recall, product, lot, supplier and customer details remain hidden."
        )

    accounts = available_accounts()
    usernames = [account["username"] for account in accounts]
    account_by_username = {
        account["username"]: account for account in accounts
    }

    with st.form("login_form", clear_on_submit=False):
        username = st.selectbox(
            "Username",
            usernames,
            format_func=lambda value: (
                f"{value} · {account_by_username[value]['role']}"
            ),
        )
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")

    if submitted:
        user = authenticate(username, password)
        if user:
            st.session_state["auth_user"] = user
            st.rerun()
        else:
            st.error("Incorrect password for the selected username.")

    st.caption(
        "Demo credentials are documented in docs/DEMO_ACCOUNTS.md."
    )
    return None


def _sidebar_approval_item(st, store, case, task, user):
    role = user["role"]
    with st.expander(f"APPROVE / REJECT · {task['title']}"):
        st.caption(
            f"Priority: {task.get('priority')} · "
            f"Exposure: {case.get('exposure', {}).get('status')}"
        )
        st.write(task.get("why_generated", ""))
        comment = st.text_input(
            "Decision note",
            "Reviewed against the available evidence.",
            key=(
                f"sidebar_decision_{case['case_id']}_"
                f"{task['task_id']}_{user['username']}"
            ),
        )
        left, right = st.columns(2)

        if left.button(
            "Approve",
            type="primary",
            key=(
                f"sidebar_approve_{case['case_id']}_"
                f"{task['task_id']}_{user['username']}"
            ),
            use_container_width=True,
        ):
            try:
                def _approve(latest_case):
                    approve_task(
                        latest_case,
                        task["task_id"],
                        user["display_name"],
                        comment,
                        approver_role=role,
                        approver_username=user.get("username"),
                    )
                    return latest_case

                store.mutate_case(case["case_id"], _approve)
                st.rerun()
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))

        if right.button(
            "Reject",
            key=(
                f"sidebar_reject_{case['case_id']}_"
                f"{task['task_id']}_{user['username']}"
            ),
            use_container_width=True,
        ):
            try:
                def _reject(latest_case):
                    reject_task(
                        latest_case,
                        task["task_id"],
                        user["display_name"],
                        comment,
                        approver_role=role,
                        approver_username=user.get("username"),
                    )
                    return latest_case

                store.mutate_case(case["case_id"], _reject)
                st.rerun()
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))


def _sidebar_review_item(st, store, case, review, user):
    with st.expander(f"REVIEW · {review['title']}"):
        st.caption(
            f"Priority: {review.get('priority')} · "
            f"Exposure: {case.get('exposure', {}).get('status')}"
        )
        st.write(review.get("description", ""))
        comment = st.text_input(
            "Review note",
            "Evidence reviewed.",
            key=(
                f"sidebar_review_note_{case['case_id']}_"
                f"{review['review_id']}_{user['username']}"
            ),
        )
        if st.button(
            "Mark as reviewed",
            type="primary",
            key=(
                f"sidebar_review_{case['case_id']}_"
                f"{review['review_id']}_{user['username']}"
            ),
            use_container_width=True,
        ):
            try:
                def _mark(latest_case):
                    mark_reviewed(
                        latest_case,
                        review["review_id"],
                        user["display_name"],
                        user["role"],
                        comment,
                    )
                    return latest_case

                store.mutate_case(case["case_id"], _mark)
                st.rerun()
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))


def _sidebar_work_item(st, store, case, task, user):
    with st.expander(f"DONE · {task['title']}"):
        st.caption(
            f"Priority: {task.get('priority')} · Status: {task.get('status')}"
        )
        st.write(task.get("description", ""))
        if task.get("demo_corrective_action"):
            st.caption(f"Incident Manager request: {task.get('request_reason') or 'Further evidence required.'}")
            evidence_note = st.text_area(
                "Corrective action taken / revised evidence",
                key=f"sidebar_corrective_{case['case_id']}_{task['task_id']}_{user['username']}",
            )
            button_label = "Submit corrective evidence"
        else:
            evidence_note = None
            button_label = "Mark as done"
        if st.button(
            button_label,
            type="primary",
            key=(
                f"sidebar_done_{case['case_id']}_"
                f"{task['task_id']}_{user['username']}"
            ),
            use_container_width=True,
        ):
            try:
                def _complete(latest_case):
                    if task.get("demo_corrective_action"):
                        submit_demo_corrective_evidence(
                            latest_case,
                            task["task_id"],
                            user["display_name"],
                            user["role"],
                            user.get("username"),
                            evidence_note,
                        )
                    else:
                        complete_task(
                            latest_case,
                            task["task_id"],
                            user["display_name"],
                            actor_role=user["role"],
                        )
                    return latest_case

                store.mutate_case(case["case_id"], _complete)
                st.rerun()
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))


def render_account_panel(st, user):
    store = CaseStore()
    cases = {
        case_id: case
        for case_id, case in store.load_cases().items()
        if case.get("state") != "CLOSED"
    }
    live_demo_selected = (
        st.session_state.get("prototype_view_mode") == "Live Demo (Prepared FSAI Case)"
        or st.session_state.get("recall_source_mode") == "Demo"
    )
    if live_demo_selected:
        demo_active_case_id = st.session_state.get("active_case_id")
        if demo_active_case_id in cases:
            cases = {demo_active_case_id: cases[demo_active_case_id]}
    personal = personal_action_summary(cases, user["role"], username=user.get("username"))

    with st.sidebar:
        st.markdown("### Signed in")
        st.write(user["display_name"])
        st.caption(user["role"])
        st.caption(f"Username: {user['username']}")

        st.divider()
        st.markdown("### My actions")
        a, b, c = st.columns(3)
        a.metric("Approve", personal["approval_count"])
        b.metric("Review", personal["review_count"])
        c.metric("Done", personal["work_count"])

        if personal["total"] == 0:
            st.success("No actions are currently assigned to you.")
        else:
            st.warning(f"{personal['total']} action(s) require your attention.")

            for case, task in personal["approvals"]:
                _sidebar_approval_item(st, store, case, task, user)

            for case, review in personal["reviews"]:
                _sidebar_review_item(st, store, case, review, user)

            for case, task in personal["work"]:
                _sidebar_work_item(st, store, case, task, user)

        st.divider()
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("auth_user", None)
            st.rerun()
