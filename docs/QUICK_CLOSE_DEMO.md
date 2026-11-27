# Quick case-closure demo

Recommended sequence:

1. Sign in as `incident.manager / !`.
2. Open **Investigation**.
3. Select **Regulatory input = Demo**.
4. Choose any **DEMO CONFIRMED** recall. The regulatory notice is genuine FSAI data.
5. Click **Run demo investigation**.
6. The normal agentic investigation runs and the deterministic exposure result remains unchanged.
7. Demo mode then replaces the full response workload with exactly two sequential governance approvals.
8. Sign out and sign in as `site.manager / !` (Dublin Site Manager for the prepared 2026.38 case).
9. Open **Response Cases** and approve **Approve containment evidence package**.
10. Sign out and sign in as `incident.manager / !`.
11. Open **Response Cases** and approve **Approve response package for closure**.
12. The case becomes **RESOLVED** automatically.
13. Record the closure comment and click **Approve and close resolved case**.
14. The dashboard shows **CASE CLOSED ✓**.
15. Click **Download Complete Audit Record**.

During Demo mode, the Response tab, sidebar action centre and sign-in role counts focus on the current demo case so older open cases do not clutter the pitch.

The final file is also written to:

```text
audit_exports/<CASE-ID>_audit.json
audit_exports/<CASE-ID>_audit.sha256
```

Important demo wording:

> The FSAI recall is genuine regulatory data. The company-side SKU, stock, dispatch and pre-completed operational evidence are synthetic challenge records. Demo mode shortens only the human response sequence; it does not alter the agent investigation or deterministic exposure classification.
