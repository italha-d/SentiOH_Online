# SentiOH reproducible demo sequence

Run:

```bash
streamlit run app.py
```

## Main demo

1. Click **Reset demo session**.
2. Select `FSAI_DEMO_001`.
3. Show **Public Recall Evidence** and the explicit synthetic-source warning.
4. Click **Run full investigation**.
5. Show the agent timeline.
6. Show the catalogue-wide four-state exposure analysis.
7. Show the evidence panel separating recall evidence from internal company evidence.
8. Show the traceability graph:
   recall → product → lot → purchase order/supplier → site/stock → dispatch/customer.
9. Show the response case and approval-gated tasks.
10. Approve one protected task to demonstrate the human boundary.
11. Click **Simulate recall revision**.
12. Run the investigation again.
13. Show that the same case ID is retained, revision increases and the second
    affected lot is included.
14. Show the audit timeline.
15. Show synthetic precision/recall/F1 validation and the dataset scale.

## Expected fixed story for the first run

- Recall fixture: `FSAI_DEMO_001`
- Exposure: `CONFIRMED`
- Affected lot: `SS16726`
- Remaining stock: `41`
- Already dispatched: `27`
- Response stops at human approval.

## Expected story after the synthetic update

- Existing case is reused.
- Revision becomes `2`.
- Affected lots: `SS16726`, `SS16727`
- Remaining stock: `66`
- Already dispatched: `37`

## Submission recording checklist

A screen recording still has to be captured on the presentation machine before
submission. Record the exact sequence above after the final environment check.
The repository cannot record the user's local Streamlit desktop session itself.


## Role-based approval website demo

For the strongest governance demonstration:

1. Sign in as `quality.manager` and run `FSAI_DEMO_001`.
2. Sign out. Sign in as `warehouse.manager`.
   - The Warehouse Manager sees stock-hold and dispatch-pause approval requests.
   - Approve the stock hold.
3. Sign out. Sign in as `procurement.manager`.
   - Only the supplier communication approval is shown in My Approval Inbox.
   - Approve it.
4. Sign out. Sign in as `quality.manager`.
   - Approve the Quality side of the customer communication dual approval.
   - The task remains waiting with one approval left.
5. Sign out. Sign in as `incident.manager`.
   - The remaining customer communication approval is now routed to the Incident Manager.
   - Approve it.
6. Observe the global **Approvals left** metric and the success banner once all
   remaining protected-action approvals have been completed.
7. Operational users can then sign in to complete work assigned to their role.

The shared SQLite case store means the case and approval progress persist while
switching accounts or using separate browser sessions.


## Human Action Centre demo sequence

1. Start on the clean authorised sign-in page and sign in as `incident.manager`.
2. Open the Live Demo and show the verified recall alert presented to the Incident Manager.
3. Run the investigation and show the new **Attention Required** summary.
4. Show the **Incident Management Overview** and **Who currently needs to act**.
5. Sign out and sign in as `warehouse.manager`.
   Only warehouse-authorised approval requests appear in **My Approval Inbox**.
6. Sign in as `quality.manager`.
   Show the separate **My Review Inbox** and mark the confirmed exposure finding
   as reviewed.
7. Complete the dual customer-communication approval with the Quality Manager
   and Incident Manager accounts.
8. Complete operational tasks with their assigned role accounts.
9. Return to the Incident Manager account and show the remaining action count
   falling to zero.
10. Finish on the green **ALL HUMAN ACTIONS COMPLETE** banner.

This sequence demonstrates that SentiOH does not merely identify recall
exposure. It routes accountability to named governance roles and shows exactly
where the response is waiting.


## Fast closure and audit demonstration

For a short governance ending, use Demo mode directly:

1. Sign in as `incident.manager` and open **Investigation**.
2. Select **Regulatory input = Demo** and choose a **DEMO CONFIRMED** recall.
3. Click **Run demo investigation**.
4. Sign in as `warehouse.manager` and approve the containment evidence package.
5. Sign back in as `incident.manager` and approve the response package.
6. The case becomes **RESOLVED**.
7. Record the closure comment and click **Approve and close resolved case**.
8. Show **CASE CLOSED ✓** and download the complete audit JSON.

The FSAI recall remains genuine. Demo mode changes only the downstream human-action
sequence and clearly records that simplification in the audit.
