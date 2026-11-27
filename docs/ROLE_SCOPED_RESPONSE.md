# Role-scoped Response tab

The Response tab is scoped to the authenticated user's governance role.

A logged-in user sees only cases containing a response item relevant to their
role. Within those cases SentiOH shows only:

- operational tasks assigned to that role;
- protected tasks assigned to that role while they wait for approval;
- approval decisions currently requiring that role;
- review acknowledgements assigned to that role;
- final case closure when the logged-in role is authorised and the case is
  RESOLVED.

Actions belonging to other roles are not rendered in the Response tab.
Management-wide oversight remains available separately in the Overview tab for
authorised management roles.

Examples for a CONFIRMED exposure:

- Warehouse Operator: stock-hold/physical-quantity work assigned to that role.
- Warehouse Manager: only relevant containment/logistics approval decisions.
- Store / Site Manager: relevant site/stock-hold approval.
- Logistics Operator: distribution trace and assigned dispatch-pause work.
- Logistics Manager: dispatch-pause approval.
- Procurement Team: supplier communication task.
- Procurement Manager: supplier communication approval.
- Customer Communications Team: customer communication task.
- Quality & Food Safety Manager: its assigned documentation/review work and
  relevant customer-communication approval.
- Recall / Incident Manager: its assigned reviews and relevant approvals.
- Senior Responsible Manager: final case closure when the case is RESOLVED,
  unless another explicit action is later assigned.

For a POSSIBLE exposure:

- Warehouse Operator: physical lot/batch verification.
- Quality & Food Safety Manager: date-evidence work and uncertainty review.
- Procurement Team: missing supplier-documentation task.

Role filtering is a presentation restriction, not the only security layer.
Backend approval, review, task-completion and closure functions continue to
validate actor roles before mutating a case.
