# Llama 3.2 and recall-data update

This build makes `llama3.2:latest` the default local Ollama model and repairs
the bundled recall fixtures.

## Llama 3.2 changes

- Default Ollama model: `llama3.2:latest`.
- Native Ollama tool calling remains the primary planner path.
- Plain-text model responses cannot prematurely terminate an incomplete
  investigation.
- Invalid/repeated tool choices are retried.
- Candidate traversal follows deterministic catalogue ranking to prevent a
  small local model from repeatedly choosing weaker or already-investigated
  products.
- Repeated unusable model outputs trigger an explicitly logged
  `ollama-guardrail-recovery` decision rather than silently failing.
- LLM-generated recommendation wording remains advisory only.

## Recall-data fixes

The bundled recall records remain synthetic and unverified. They no longer
contain broken `example.invalid` source links. `source_url` is null for the
synthetic fixtures and the UI labels it accordingly.

A new locked recall expectation file verifies:

- `FSAI_DEMO_001` -> `SKU001`, CONFIRMED, stock 41, dispatched 27.
- `FSAI_DEMO_002` -> `SKU005`, POSSIBLE, stock 60, dispatched 15.
- `FSAI_DEMO_003` -> `SKU008`, CONFIRMED, stock 12, dispatched 4.

Run:

```bash
python scripts/check_recall_data.py
```

to verify the recall fixtures and their expected end-to-end outcomes.

The main integration check now runs this recall audit automatically.
