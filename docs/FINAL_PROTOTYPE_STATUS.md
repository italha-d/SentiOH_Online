# SentiOH final prototype status

## Ready without real FSAI/RASFF notices

The runnable prototype now includes:

- synthetic company catalogue and traceability data;
- bounded agent investigation;
- deterministic exposure matching;
- exact identifier support when supplied by a recall;
- four-state exposure logic;
- multi-lot handling;
- current-stock and downstream-dispatch tracing;
- supplier/purchase-order traceability;
- governed response cases;
- explicit case state machine;
- human approval boundaries;
- recall update/re-analysis;
- append-only audit events;
- synthetic precision/recall/F1 evaluation;
- single-screen Streamlit Control Tower;
- offline reproducible Demo Mode;
- automated validation, smoke tests and integration checks.

## Pending source-grounding work

This repository does not claim that its bundled recall fixtures are genuine
FSAI/RASFF notices. Verified public-source data must later replace or supplement
`demo_data/recalls.json`. Real-source fields must never be guessed.
