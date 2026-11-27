# SentiOH demo accounts

These accounts are for the offline prototype only. They demonstrate role-based
routing of work and approvals. They are not production identity credentials.

| Username | Role | Password |
|---|---|---|
| `warehouse.operator` | Warehouse Operator | `Warehouse2026!` |
| `warehouse.manager` | Warehouse Manager | `!` |
| `site.manager` | Store / Site Manager | `!` |
| `cork.manager` | Store / Site Manager | `!` |
| `logistics.operator` | Logistics Operator | `Logistics2026!` |
| `logistics.manager` | Logistics Manager | `!` |
| `quality.manager` | Quality & Food Safety Manager | `!` |
| `procurement.team` | Procurement Team | `ProcurementTeam2026!` |
| `procurement.manager` | Procurement Manager | `!` |
| `communications.team` | Customer Communications Team | `Comms2026!` |
| `incident.manager` | Recall / Incident Manager | `!` |
| `senior.manager` | Senior Responsible Manager | `!` |

## Important

A production deployment should replace these local demo accounts with an
enterprise identity provider such as Microsoft Entra ID / Azure AD, Okta or
another SSO/OIDC provider, and store secrets outside the repository.
