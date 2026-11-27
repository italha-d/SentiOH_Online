# Demo rebuild notes

This build returns to the original SentiOH workflow and keeps the presentation layer separate from governance logic.

## Restored behaviour

- **Official FSAI (Full Feature Prototype)** is the default selectable view.
- **Live Demo (Prepared FSAI Case)** uses the same workflow but filters the recall list to prepared genuine FSAI examples.
- The Incident Manager, Quality/Food Safety Manager or Senior Responsible Manager can start an investigation. Warehouse roles cannot start the agent investigation.
- The default online LLM remains the tool-selection planner. Deterministic tools perform product/lot matching and exposure classification.
- Confirmed cases retain the complete response task set and review set. No quick-close or approval-only reduction is applied.
- Task and approval assignments are shown only after the response case has been generated.
- Operational task completion is checked against the authenticated user's role at both UI and workflow levels.
- Approvals, reviews and final closure retain their existing role checks.

## Presentation additions

- Six-stage live-demo progress rail inside Investigation.
- Agentic tool-use trace after the investigation runs.
- Role-based human handoff table generated from the real case task objects.
- Kiro typography configuration and long-text wrapping retained.

## Removed from the presentation UI

- Synthetic regulatory recall selector.
- All-recalls selector.
- The previous demo shortcut that compressed a confirmed case into a small approval-only sequence.
