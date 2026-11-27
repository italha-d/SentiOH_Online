# SentiOH LLM agent enhancements

The app's default planner uses Groq's OpenAI-compatible API. Local Ollama is
still available by setting `SENTIOH_PLANNER=ollama`. Both planners keep the
recall decision and governance layers deterministic.

## 1. Dynamic task rationale and suggested steps

The workflow engine still decides which tasks exist, their priority, assigned
role, approval authority, required completion evidence, completion criterion
and agent boundary.

After the deterministic case is created, the configured model receives the
structured case evidence and generates only:

- `why_generated`
- `suggested_steps`

The original deterministic text is retained as:

- `template_why_generated`
- `template_suggested_steps`

If LLM text generation fails, SentiOH keeps the deterministic fallback
rather than leaving the task unexplained.

Each enriched task records:

```text
narrative_source = llm
narrative_model = configured model ID
narrative_generated_time = ...
```

The case audit records `LLM_TASK_NARRATIVES_GENERATED`.

## 2. Evidence-gap reasoning for POSSIBLE exposure

For a deterministic `POSSIBLE` result, the configured model produces a structured
evidence-gap analysis with:

- concise summary;
- decisive missing evidence;
- priority evidence to verify first;
- why that evidence should be prioritised;
- recommended internal evidence-gathering action;
- confidence/scope note.

This analysis is advisory. It cannot convert `POSSIBLE` to `CONFIRMED`, cannot
exclude a product and cannot authorise a protected action.

The analysis is stored in the shared case so it remains visible after logout or
role switching.

## 3. Differential re-analysis after recall updates

SentiOH now stores a structured snapshot of material recall fields and records
which fields changed between versions.

If a recall update changes only lot/date/scope fields while product identity
fields remain unchanged, the next investigation uses:

```text
mode = DIFFERENTIAL
```

and reuses the previously established product identity / catalogue candidate.

It therefore skips repeated catalogue search and refreshes:

- current recall evidence;
- batch/lot evidence;
- deterministic exposure;
- inventory;
- dispatches;
- purchase history;
- response case.

If product identity fields change, SentiOH uses `FULL_REANALYSIS` and performs
catalogue identity work again.

The LLM sees this re-analysis context in its `InvestigationState`, so it can
plan around what is already trusted and what needs refreshing.

## 4. Persisted LLM recommendation

The final evidence-grounded recommendation is stored in the response
case with model and generation time, so it is available to other authenticated
roles after logout/login.

## Safety boundary

The model still cannot change:

- `CONFIRMED`, `POSSIBLE`, `NOT_AFFECTED`, `INSUFFICIENT_EVIDENCE`;
- task identity;
- priority;
- assigned role;
- approval authority;
- approval mode;
- completion evidence;
- completion criteria;
- agent boundary;
- workflow state;
- recorded human approvals.

Those remain deterministic Python/governance controls.

## End-to-end verification

Run the app tests with:

```bash
python -m pytest -q
```

For local Ollama testing, first set `SENTIOH_PLANNER=ollama` and follow
`docs/OLLAMA_SETUP.md`.
