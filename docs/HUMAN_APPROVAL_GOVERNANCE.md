# Human approval governance

SentiOH uses bounded agency. The investigation agent can decide what evidence to retrieve next, open a governed response case and propose operational tasks. Protected actions are blocked at a human approval gate.

| Proposed action | Assigned role | Approval authority | Policy |
| --- | --- | --- | --- |
| Hold remaining stock | Warehouse Operator | Warehouse Manager OR Store / Site Manager | Any one |
| Verify physical quantity | Warehouse Operator | None | Evidence task |
| Trace downstream distribution | Logistics Operator | None | Evidence task |
| Pause further dispatch | Logistics Operator | Logistics Manager OR Warehouse Manager | Any one |
| Prepare supplier communication draft | Procurement Team | Procurement Manager | One required |
| Prepare customer communication draft | Customer Communications Team | Quality & Food Safety Manager AND Recall / Incident Manager | Dual approval |
| Record completion evidence | Quality & Food Safety Manager | None | Documentation task |
| Close resolved case | Recall response leadership | Recall / Incident Manager OR Senior Responsible Manager | One required |

Rejection of an action does not change `CONFIRMED`, `POSSIBLE`, `NOT_AFFECTED` or `INSUFFICIENT_EVIDENCE`. Exposure truth remains evidence-driven. The rejection is an operational governance decision and is stored with approver name, role, timestamp and reason.
