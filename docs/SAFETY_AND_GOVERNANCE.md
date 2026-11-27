# Safety and governance

1. Fuzzy matching generates candidates only.
2. Batch/lot equality is deterministic.
3. Recall date scope is checked against structured fields.
4. Inventory and dispatch quantities come from records, not generated text.
5. Only CONFIRMED or POSSIBLE exposure can create a response case.
6. Consequential tasks can require human approval.
7. The agent has no tool that can approve its own task.
8. External communications remain drafts in this prototype.
9. Maximum agent steps are bounded.
10. Every tool call and observation is added to the investigation timeline.
11. Demo recall records are visibly marked as unverified placeholders.
12. Real competition metrics must be generated from manually labelled,
    source-verified evaluation cases.
