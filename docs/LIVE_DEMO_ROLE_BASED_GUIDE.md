# SentiOH Live Demo: six-step, two-role flow

## Purpose

The application has two top-level tabs. **Official FSAI** is the complete full-feature prototype. **Live Demo** is a presentation-focused single-page workflow using the same verified FSAI input, agentic LLM planner, deterministic evidence tools, role enforcement and audit trail.

## Recommended pitch sequence

1. Sign in as **Recall / Incident Manager** (`incident.manager`) and open **Live Demo**.
2. The page presents a **new verified FSAI recall alert** with the product, affected lot/date scope and hazard/reason.
3. The Incident Manager clicks **Run investigation**. The configured LLM autonomously selects approved tools. The screen shows each selected tool as it runs.
4. SentiOH displays the six-step trace on one page: verified recall, extracted recall fields, company match, stock/dispatch evidence, exposure graph plus rationale, and the human-decision stage.
5. After a confirmed match, SentiOH routes **Confirm and complete affected stock containment** to the manager responsible for the affected stock location. For the prepared FSAI 2026.38 demo, the stock is at Dublin Distribution Centre, so sign out and sign in as `site.manager` (Dublin Site Manager), then approve/complete the containment task or reject it with a reason.
6. Once the warehouse task is completed, SentiOH hands the case back to the **Recall / Incident Manager**. Sign out and sign in as `incident.manager`, review the evidence and select **Approve and close case**. This is the second and final authorised decision.
7. The case changes to **CLOSED** and the complete audit record can be downloaded.

## Six pitch stages

- Load verified recall notice
- Extract affected product + lot
- Resolve against synthetic company records
- Trace stock + dispatch evidence
- Generate exposure graph + rationale
- Require role-based human approval

## Governance boundary

The LLM selects approved investigation tools, but deterministic logic performs product/lot matching and exposure classification. The LLM cannot approve containment, impersonate another role or close the case. The local manager assigned from the affected stock location cannot perform the Incident Manager's final closure action, and the Incident Manager cannot perform the local containment decision.

## Full-feature prototype

The **Official FSAI** tab remains available throughout the demonstration and retains the broader investigation, evidence, response, review, validation and audit workflow. The Live Demo shortens only the human closure path for presentation purposes; the case records how many full-workflow tasks and reviews would normally have been generated.

## Demo reliability

Use the bundled FSAI snapshot during the pitch instead of refreshing the regulator feed. For the default online planner, configure `GROQ_API_KEY`; if using local Ollama instead, keep Ollama running with the configured model.
