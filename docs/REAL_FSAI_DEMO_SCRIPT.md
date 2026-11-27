# Real FSAI challenge demo

## Start

```bat
ollama pull llama3.2:latest
streamlit run app.py
```

Recommended login:

```text
Username: incident.manager
Password: !
```

## Demo 1: genuine FSAI confirmed exposure

1. Open **Investigation**.
2. Select **Regulatory input = Demo**.
3. The dropdown now contains only the nine prepared genuine FSAI demo recalls.
   Select `DEMO CONFIRMED 1/3`, FSAI 2026.38 smoked-salmon recall.
4. Open the official-source evidence and show the FSAI URL, batch SS16726 and
   use-by scope.
5. Click **Run full investigation**.
6. Show the agent tool timeline.
7. Show:
   - deterministic `CONFIRMED / EXACT_PRODUCT_AND_LOT_MATCH`;
   - synthetic SKU398;
   - 17 units remaining;
   - 13 affected units dispatched;
   - response case;
   - local Llama recommendation/task rationale;
   - human approval boundary.
8. Sign out and use an appropriate manager account to demonstrate role-routed
   approval.

## Demo 2: genuine FSAI possible exposure

Select `DEMO POSSIBLE 1/3`, FSAI 2026.52 Tesco Sesame Seeds.

Expected:

```text
POSSIBLE / LOT_INFORMATION_MISSING
```

Show the local Llama evidence-gap analysis explaining what internal evidence
should be checked first.

## Demo 3: genuine FSAI excluded lot

Select `DEMO NOT_AFFECTED 1/3`, FSAI 2026.48 SuperValu Sesame Seeds.

Expected deterministic product-level result for synthetic SKU400:

```text
NOT_AFFECTED / LOT_MISMATCH
```

## Explain provenance

Use this wording:

> The regulatory notice is genuine FSAI data. The internal enterprise
> catalogue, stock, supplier and dispatch records are synthetic challenge data.
> Llama 3.2 plans and explains the investigation locally; deterministic Python
> establishes the actual exposure state and human roles govern consequential
> actions.


## Available showcase set

The dropdown now contains exactly three deliberate company-side examples for
each requested outcome:

```text
CONFIRMED
- FSAI 2026.38 -> SKU398
- FSAI 2026.41 -> SKU392
- FSAI 2026.50 Gem Sesame Seeds -> SKU393

POSSIBLE
- FSAI 2026.52 -> SKU399
- FSAI 2026.49 -> SKU394
- FSAI 2026.36 -> SKU395

NOT_AFFECTED
- FSAI 2026.48 -> SKU400
- FSAI 2026.47 -> SKU396
- FSAI 2026.26 -> SKU397
```

These are genuine FSAI regulatory inputs mapped to synthetic internal company
records. Other FSAI recalls can also be selected. If they are absent from the
company catalogue, the agent now finishes with a clean no-exposure conclusion
instead of `MAX_AGENT_STEPS_REACHED`.
