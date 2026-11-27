from workflow.approvals import approve_task, reject_task, complete_task

def render(st, case):
    st.header("Response Case")
    for task in case.get("tasks", []):
        with st.container(border=True):
            st.subheader(task["title"])
            st.write(f"Assigned role: {task.get('assigned_to')}")
            st.write(f"Status: {task.get('status')}")
            if task.get("requires_approval") and task.get("status") == "WAITING_FOR_APPROVAL":
                roles = task.get("approval_roles") or []
                role = st.selectbox("Approval role", roles, key=f"legacy_role_{task['task_id']}")
                name = st.text_input("Approver name", f"Demo {role}", key=f"legacy_name_{task['task_id']}")
                comment = st.text_input("Comment", "Reviewed.", key=f"legacy_comment_{task['task_id']}")
                a, b = st.columns(2)
                if a.button("Approve", key=f"legacy_approve_{task['task_id']}"):
                    approve_task(case, task["task_id"], name, comment, approver_role=role)
                    st.rerun()
                if b.button("Reject", key=f"legacy_reject_{task['task_id']}"):
                    reject_task(case, task["task_id"], name, comment, approver_role=role)
                    st.rerun()
            elif task.get("status") in {"PENDING", "APPROVED"}:
                if st.button("Complete", key=f"legacy_complete_{task['task_id']}"):
                    complete_task(case, task["task_id"], task.get("assigned_to") or "Operator")
                    st.rerun()
