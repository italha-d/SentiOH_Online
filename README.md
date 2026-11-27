# SentiOH Agentic Platform

**Evidence-Grounded Product Recall Exposure & Response Agent**

ONEHEALTH Team prototype for the TechIreland National AI Challenge 2026,
Challenge #17: Catalogue-Aware Product Recall Agent.

## What is included

This repository is a running end-to-end agentic prototype:

- recall ingestion;
- catalogue candidate retrieval;
- deterministic product/brand/pack/lot/date exposure resolution;
- four exposure states:
  `CONFIRMED`, `POSSIBLE`, `NOT_AFFECTED`, `INSUFFICIENT_EVIDENCE`;
- inventory and dispatch tracing;
- upstream purchase/supplier tracing;
- a bounded investigation agent with tool selection;
- persistent investigation state and event timeline;
- response-case creation;
- differentiated tasks for CONFIRMED and POSSIBLE exposure;
- human approval gates for consequential actions;
- case audit history;
- six-screen Streamlit application;
- exposure graph;
- offline Demo Mode;
- online Groq-compatible LLM planner, with optional local Ollama support;
- automated unit and end-to-end tests.

## Important provenance limitation

The bundled recall records are demonstration placeholders with
`example.invalid` URLs and `is_public_source_verified=false`. They are not
presented as genuine FSAI records.

Before a competition demonstration that claims real FSAI coverage, replace them
with manually checked historical recall records while retaining their original
source URLs and publication dates.

The company catalogue, supplier, batch, inventory, purchase-order and dispatch
records are sandbox data.

## Architecture

```text
New recall
    |
    v
SentiOH Investigation Agent
    |
    | chooses approved tools
    v
+---------------------------+
| get_recall                |
| search_catalogue          |
| get_batches               |
| resolve_exposure          |
| get_inventory             |
| get_dispatches            |
| get_purchase_history      |
| open_response_case        |
| request_human_approval    |
+---------------------------+
    |
    v
Deterministic evidence resolver
    |
    +--> CONFIRMED
    +--> POSSIBLE
    +--> NOT_AFFECTED
    +--> INSUFFICIENT_EVIDENCE
    |
    v
Governed response workflow
    |
    v
Human approval boundary
```

The planner does not have `approve`, `send external communication`,
`release stock` or `close case` tools.

## Quick start

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Test the repository

```bash
pytest -q
python smoke_test.py
```

## Online LLM planner

The app defaults to Groq's OpenAI-compatible Chat Completions API. For local
development, the app loads `.env` automatically:

```text
SENTIOH_PLANNER=llm
GROQ_API_KEY=your-key
```

The default endpoint and model can be overridden with `SENTIOH_LLM_BASE_URL`
and `SENTIOH_LLM_MODEL`. `SENTIOH_LLM_API_KEY` can be used instead of
`GROQ_API_KEY` for other OpenAI-compatible providers. The LLM can choose only
registered investigation tools; it cannot override deterministic exposure
resolution or human approval policy. Set `SENTIOH_PLANNER=rule` for the
offline deterministic planner or `SENTIOH_PLANNER=ollama` to use local Ollama.
The default Groq model is `openai/gpt-oss-20b`.

## Deploy on Render

The included `render.yaml` configures the Streamlit web service, Render's
dynamic port, Groq planner defaults, and temporary paths for case and audit
data. Create a new Render Blueprint from this repository and provide
`GROQ_API_KEY` when prompted (or add it under the service's Environment
settings). Do not commit `.env`; Render does not receive your local `.env`
file.

This Blueprint uses Render's free service plan. Its filesystem is ephemeral:
SQLite cases and audit exports can be lost when the service restarts or is
redeployed. Use a persistent database/storage service before relying on it for
operational records.

## Repository structure

```text
SentiOH_Agentic_Platform/
├── agent/
│   ├── orchestrator.py
│   ├── planner.py
│   ├── policies.py
│   ├── prompts.py
│   └── state.py
├── tools/
│   ├── registry.py
│   ├── recall_tools.py
│   ├── catalogue_tools.py
│   ├── exposure_tools.py
│   ├── inventory_tools.py
│   ├── dispatch_tools.py
│   ├── supplier_tools.py
│   └── workflow_tools.py
├── matching/
├── workflow/
├── ingestion/
├── ui/
├── demo_data/
├── starter_data/
├── tests/
├── docs/
├── app.py
├── smoke_test.py
├── demo_script.md
└── requirements.txt
```

## Recommended next data step

Replace the bundled demonstration recall records with 20–50 manually verified
historical FSAI recall notices. Do not guess missing public-source fields.
Use `null` or an empty list when the source does not provide a value.


## Expanded synthetic business sandbox

This version includes **400 products**, **25 suppliers**,
**900 lot/batch records**, **3 sites**, **661 inventory
records**, **628 purchase orders** and **785 downstream
dispatch records**.

The locked evaluation manifest deliberately covers true affected products,
same-product wrong-lot cases, similar-name false positives, missing-lot
`POSSIBLE` cases, wrong pack sizes and unrelated products. See
`demo_data/ground_truth_scenarios.csv` and `demo_data/dataset_manifest.json`.

## Single-screen Control Tower interface

This version replaces the multi-page navigation with one operational dashboard. The complete workflow is visible on a single Streamlit screen:

1. recall selection and agent controls;
2. investigation timeline;
3. exposure evidence and traceability graph;
4. detailed response task board;
5. case audit trail;
6. prototype validation and sandbox scale.

Each response task now contains a plain-language description, the reason SentiOH created it, suggested operator steps, expected completion evidence, a completion criterion, the triggering evidence and an explicit agent/human action boundary. Protected actions remain behind human approval.


## One response case per recall

Repeated analysis is now idempotent:

- the first run creates a response case;
- an unchanged re-run returns the same case ID and preserves task progress;
- changed material evidence updates the same case and increments its revision;
- the previous task set is archived when evidence changes;
- old duplicate cases from earlier versions are collapsed to the latest case per recall.

Repeated clicks on **Run full investigation** therefore no longer inflate the active-case count.


## Clearer validation panel

The final dashboard section is now called **System Validation & Demo Dataset**.

It separates:
- **System Validation**, which reports locked synthetic scenario coverage and pass rate;
- **Demo Environment**, which reports the size of the synthetic catalogue and traceability data.

The dashboard explicitly states that these are prototype synthetic results, not real-world FSAI performance metrics.


## Active case portfolio

The single-screen dashboard now exposes every active response case rather than
showing only the case associated with the currently selected recall.

The **All active cases** table displays case ID, recall ID, exposure status,
SKU, batch, case state, revision, task counts and last update time. The
operator can select any case from **Inspect response case** and immediately
view its detailed task board and audit history without changing the current
recall investigation.

The Active Cases metric counts only cases that are not `RESOLVED` or `CLOSED`.


# Final non-source-dependent prototype completion

This build completes the engineering work that does **not** require verified
FSAI/RASFF source notices.

## Completed in this build

- 400 synthetic catalogue products, 25 suppliers, 900 lots and three sites.
- Synthetic inventory, purchase-order and downstream dispatch histories.
- Exact source GTIN/barcode matching pathway when a recall explicitly supplies
  an identifier. Internal SKU remains a company-side identifier only.
- Unified batch/lot normalisation across matching, inventory, dispatch and
  purchase-order tracing.
- Deterministic four-state exposure resolution.
- Multi-lot recall support.
- Precision, recall, F1, macro F1, weighted F1 and confusion-matrix evaluation
  for the locked **synthetic** evaluation scenarios.
- Full case-state lifecycle:
  DETECTED → ANALYSING → REVIEW_REQUIRED/CONFIRMED → RESPONDING → RESOLVED → CLOSED.
- Idempotent one-case-per-recall behaviour.
- Human approval gates and draft-only external communications.
- Immutable-style append-only audit timeline.
- Synthetic recall revision demonstration that adds an additional affected lot,
  reopens the existing case for analysis and increments its revision.
- Single-screen Recall Inbox, agent timeline, catalogue-wide exposure analysis,
  public-vs-internal evidence separation, complete traceability graph, response
  case portfolio, audit trail and validation panel.
- Detailed missing-value reporting from the data validator.
- Repeatable integration health-check script.

## Still intentionally pending

The only substantive data work intentionally left open is the verified
public-recall layer: selecting and manually checking historical FSAI/RASFF
notices, preserving their real URLs/publication dates and populating the recall
schema only with facts actually shown in those sources.

The company catalogue, SKU, stock, purchase and dispatch data are intended to
remain synthetic sandbox records.

## Role-based human approval governance

SentiOH now separates the **assigned operational role** from the **human approval authority** for protected actions. The agent may investigate, recommend and prepare an action, but it cannot authorise high-consequence actions itself.

Examples:

- Warehouse Operator verifies stock; Warehouse Manager or Store / Site Manager authorises a stock hold.
- Logistics Operator performs trace work; Logistics Manager or Warehouse Manager authorises a dispatch pause.
- Procurement Team prepares supplier communication; Procurement Manager approves or rejects it.
- Customer Communications Team prepares a downstream communication draft; both the Quality & Food Safety Manager and Recall / Incident Manager must approve it.
- Only a Recall / Incident Manager or Senior Responsible Manager may close a resolved case.

An authorised rejection rejects the **proposed action**, not the deterministic exposure result. Rejection reasons are mandatory and are written to the audit timeline.

This prototype models governance roles but does not implement authenticated user accounts or production RBAC. A production deployment would map these roles to the organisation's identity and access-management system.


## Authenticated role-routed web prototype

The Streamlit application now requires an authorised demo login before the
Control Tower is shown.

Each account has one fixed governance role. The browser does not provide a role
selector for approvals. Approval buttons are rendered only when the signed-in
role is authorised for that specific protected action.

Examples:

- Warehouse Manager / Store Site Manager: stock-hold approval.
- Logistics Manager / Warehouse Manager: outbound dispatch-pause approval.
- Procurement Manager: supplier communication approval.
- Quality & Food Safety Manager + Recall / Incident Manager: dual approval for
  customer communication.
- Recall / Incident Manager or Senior Responsible Manager: final case closure.

The top of the website shows:

- approvals left across active cases;
- approvals currently assigned to the signed-in user;
- a personal **My Approval Inbox**;
- a success banner when all required approvals are complete;
- a warning instead when approval routing is complete but an action was
  rejected.

### Shared multi-user state

Response cases are stored in a local SQLite database under `runtime/` so
different browser sessions and different authenticated demo users see the same
case and approval state. Approval decisions use an atomic SQLite mutation to
avoid losing one side of a dual approval when two authorised users act from
different sessions.

This is a challenge prototype authentication layer, not a production identity
system. For live deployment, replace the local demo accounts with enterprise
SSO/OIDC and a managed transactional database.

See `docs/DEMO_ACCOUNTS.md` for the bundled demo credentials.


## Username dropdown sign-in

The prototype login now uses a username dropdown. Users do not type a username.
They select their assigned account and enter only the password. The role is
bound to the selected account and cannot be changed from the approval screen.

The dropdown exposes only username, display name and role. Password hashes and
salts remain internal to the authentication module.


## Human Action Centre

The authenticated website now separates three different human responsibilities:

1. **Approve / Reject** for consequential protected actions.
2. **Mark as reviewed** for important evidence or agent findings that require
   human acknowledgement but not permission.
3. **Complete operational task** for work assigned to operators or teams.

Before authentication, the pitch build shows only the SentiOH brand and the
authorised role sign-in form. Operational case state is deliberately withheld
until authentication so the Live Demo begins with the Incident Manager receiving
the verified recall alert.

After sign-in, every user sees a personal Action Centre containing only the
approval, review and operational items routed to that account's fixed role.

The dashboard also shows:

- approvals left;
- reviews left;
- operational tasks left;
- total human actions left;
- the signed-in user's own action count;
- an **ALL HUMAN ACTIONS COMPLETE** banner when no approvals, reviews or
  operational tasks remain.

### Management roles

The Quality & Food Safety Manager, Recall / Incident Manager and Senior
Responsible Manager receive an additional Incident Management Overview. It
shows each case's approval-decision progress, review progress, completed tasks,
remaining human actions and a table of **who currently needs to act**.

The Recall / Incident Manager is the recommended routine control user for
starting or supervising a recall investigation. The Senior Responsible Manager
can also run the agent for escalation or executive oversight.

### Review acknowledgements

Confirmed exposure, downstream distribution findings, possible/uncertain
exposure and revised recall scope can generate review items. Review controls
appear only to the authenticated role assigned to the review.

Rejecting a protected action does not change the deterministic exposure result.
Instead, SentiOH automatically creates a follow-up Incident Manager review so
the consequence of the rejection cannot silently disappear from the workflow.


## Login and sidebar actions

The pitch build intentionally keeps the pre-login screen clean. No active-case
counts, pending-action counts, product details or role queues are shown before
authorisation. This prevents the login page from competing visually with the
Live Demo narrative.

After login, the left sidebar contains a compact **My actions** area beside
the account/logout controls. The authenticated user can act directly there on
items routed to their role:
- Approve / Reject;
- Mark as reviewed;
- Mark as done.

The same controls remain available in the main Action Centre as well.


## Professional dashboard layout

The authenticated Control Tower has been reorganised to reduce visual overload
while preserving the single-page application design.

The main content is now divided into five tabs:

- **Overview**: executive KPIs, portfolio status and the signed-in user's workload.
- **Investigation**: recall selection, public recall evidence, agent controls and
  the agent tool-call timeline.
- **Exposure & Evidence**: catalogue-wide exposure decisions, evidence panels
  and traceability graph.
- **Response**: response case selection, human-action progress, compact task
  cards and the governed audit trail.
- **Validation**: synthetic evaluation metrics and demo-environment validation.

The left sidebar remains the primary quick-action area for the authenticated
user's Approve/Reject, Mark as Reviewed and Mark as Done controls.

Detailed evidence, task rationale, long tables, traceability graphs and audit
history are collapsed into expanders by default so the first view remains
focused and readable.


## Online agent planner

The interactive app defaults to Groq's online LLM planner, configured by
`GROQ_API_KEY` in the local `.env` file or in Render's environment settings.
For local Ollama use, set `SENTIOH_PLANNER=ollama`, install Ollama, then run:

```bash
ollama pull llama3.2:latest
```

The model chooses the next permitted investigation tool from the current
`InvestigationState`. SentiOH then applies two safety layers:

1. the normal allowed-tool policy; and
2. a state-aware grounding layer that binds sensitive arguments to evidence
   already observed by the system.

The LLM therefore controls investigation strategy, while deterministic Python
remains responsible for exposure classification, stock/dispatch totals,
workflow state and approval enforcement.

After a completed investigation the configured model may generate a concise
evidence-grounded recommendation for the dashboard. That wording is advisory
and cannot alter the deterministic exposure status or approve protected actions.

For optional local Ollama setup instructions see:

```text
docs/OLLAMA_SETUP.md
```

Windows helpers:

```bat
scripts\setup_ollama_windows.bat
scripts\run_ollama_demo.bat
```

Connection check:

```bash
python scripts/check_ollama.py
```

The `RulePlanner` remains in the repository for regression tests and an
explicit deterministic fallback mode:

```text
SENTIOH_PLANNER=rule
```


## Enhanced local Llama 3.2 reasoning

The current build extends the local `llama3.2:latest` agent in three visible
ways:

1. **Case-specific task rationale and suggested steps** are generated locally
   from structured evidence after deterministic tasks have been created.
2. **POSSIBLE exposure evidence-gap analysis** identifies what evidence should
   be verified first and why.
3. **Differential recall re-analysis** records changed recall fields and reuses
   established product identity when only lot/date/scope fields change, instead
   of blindly repeating catalogue search.

Approval roles, task assignment, completion criteria, evidence requirements,
agent boundaries and exposure classification remain deterministic.

Detailed design:
`docs/LOCAL_LLM_AGENT_ENHANCEMENTS.md`

Live local-model check:

```bash
python scripts/test_ollama_agent_e2e.py
```


## Official FSAI recall integration

The main dashboard now uses **genuine FSAI regulatory recall records** by
default. The company-side catalogue, lot, supplier, inventory, purchase and
dispatch data remains synthetic.

Bundled regulatory data:

```text
regulatory_data/fsai_recalls.json
regulatory_data/fsai_needs_review.json
regulatory_data/fsai_recalls_corrected.csv
regulatory_data/fsai_ingestion_metadata.json
```

Legacy synthetic regulatory fixtures remain in the repository for regression testing only. They are not exposed as a selectable dashboard source.

The corrected FSAI scraper is bundled under:

```text
integrations/fsai_scraper/
```

A live refresh can be run with:

```bash
python scripts/refresh_fsai_recalls.py
```

Live scraping requires Chromium:

```bash
python -m playwright install chromium
```

The recommended judging mode uses the bundled FSAI snapshot, so the end-to-end
recall investigation remains reproducible even without internet access.

Nine genuine FSAI alerts/product scopes are linked to deliberately synthetic
company records for clear challenge scenarios:

- **CONFIRMED:** FSAI 2026.38, 2026.41, 2026.50 (Gem Sesame Seeds)
- **POSSIBLE:** FSAI 2026.52, 2026.49, 2026.36
- **NOT_AFFECTED:** FSAI 2026.48, 2026.47, 2026.26

Other genuine FSAI recalls remain available for normal investigation. When no
plausible company product can establish exposure, SentiOH now finishes cleanly
with `NO_ORGANISATIONAL_EXPOSURE_IDENTIFIED` rather than using the maximum-step
safety stop. The emergency cap is 16 steps.

See `docs/FSAI_INTEGRATION.md` for the full provenance, ingestion, live-refresh
and safety design.


### Official recalled-product images

The Public Recall Evidence card now displays the official FSAI product image
next to product, pack, lot/date and hazard evidence. The original FSAI image
can also be opened directly from the dashboard. No synthetic image is used
when the regulator did not publish one.


## Role-scoped Response workspace

The Response tab now shows only work relevant to the authenticated role:
assigned operational tasks, protected tasks waiting on approval, approval
decisions for that role, assigned review acknowledgements and authorised final
closure. Work belonging to other roles is hidden from the Response tab.

Management-wide oversight remains available separately in the Overview tab for
authorised management roles. Backend RBAC checks remain enforced even though
the UI is filtered.

See `docs/ROLE_SCOPED_RESPONSE.md`.


## Official FSAI and Live Demo tabs

After sign-in, the application exposes two top-level tabs:

```text
Official FSAI | Live Demo
```

The **Official FSAI** tab retains the full-feature prototype: genuine FSAI recall snapshot, investigation, exposure and evidence views, response workflow, validation and audit controls.

The **Live Demo** tab is a deliberately focused single-page pitch flow. It begins with a verified FSAI recall alert for the **Recall / Incident Manager**. Only that role can start the investigation. With the default `SENTIOH_PLANNER=llm`, the online LLM is the agentic planner and selects approved tools for recall retrieval, catalogue search, lot lookup, exposure resolution, stock tracing, dispatch tracing and case creation. Deterministic tools continue to establish the product/lot match and exposure classification.

For the pitch, the normal downstream human workload is represented by exactly **two sequential authorised decisions**:

1. **Warehouse Manager**: confirm and complete affected-stock containment.
2. **Recall / Incident Manager**: review the evidence and authorise final case closure.

The first decision is routed dynamically to the manager responsible for the affected stock location and cannot be performed by the Incident Manager. The second decision remains with the Recall / Incident Manager and is locked until the local containment task is completed. The Live Demo preserves the original full-workflow task/review definitions as a case reference so the presenter can explain that the full prototype contains broader operational controls while the pitch demonstrates the core governed sequence.

When a case is CLOSED, SentiOH can export the complete audit record. Locally,
the SQLite source of truth is `runtime/sentioh_cases.db`; the Render free
service uses temporary storage as described above.

See:

- `docs/CASE_CLOSURE_AND_AUDIT.md`
- `docs/LIVE_DEMO_ROLE_BASED_GUIDE.md`


## SentiOH branding

The supplied SentiOH logo is packaged at:

```text
assets/sentioh_logo.png
```

and is rendered on both the authorised sign-in screen and the main
authenticated dashboard. The image is used as supplied without stylistic
alteration.
