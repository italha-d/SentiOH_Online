# Official FSAI regulatory-data integration

SentiOH now uses a corrected snapshot of genuine Food Safety Authority of
Ireland (FSAI) food recall notices as the **primary regulatory input**.

The company-side catalogue, supplier, lot, inventory, purchase-order, dispatch
and customer records remain synthetic by design.

## Data separation

```text
Official FSAI website
        |
        v
Corrected Playwright scraper
        |
        v
Raw / corrected CSV snapshot
        |
        v
FSAI adapter + validation
        |
        +--> Primary regulatory recall store
        |       regulatory_data/fsai_recalls.json
        |
        +--> Review-required store
                regulatory_data/fsai_needs_review.json
                        |
                        v
                  SentiOH agent
                        |
                        v
              Synthetic company sandbox
```

This separation is intentional. SentiOH does not pretend that synthetic
company stock, purchase or dispatch data came from a real organisation.

## Bundled regulatory snapshot

The bundled corrected CSV contains 313 corrected source/product rows.

After product-scope consolidation:

- 181 primary FSAI product-scope recall records are available to the agent.
- They represent 50 official FSAI alert IDs in the primary store.
- 3 product-scope records are held separately for manual source review.
- The three old `FSAI_DEMO_*` synthetic recalls remain only as fallback and
  regression-test fixtures.

An official FSAI alert can contain several products, packs, batches or later
updates. The adapter therefore creates a stable product-scope recall record
rather than forcing an entire multi-product alert into one ambiguous object.

For example, FSAI Alert 2026.38 is consolidated so the original and update
source history is retained together:

```text
Product: K O'Connell Fishmongers Smoked Salmon Slices
Affected batch: SS16726
Use-by scope: 2026-07-16 + 2026-07-17
Alert versions: Base + Update 1
```

## Missing-data policy

The ingestion layer never invents a missing public field.

- missing brand -> null
- missing lot -> []
- ambiguous regulator date wording -> preserved in `date_scope_text`
- manual-review item -> excluded from the primary agent recall store
- official source URL and source history -> preserved

Month-level FSAI dates such as `2027-05` are supported by the deterministic
matcher as month scopes; SentiOH does not fabricate a day.

## Genuine-FSAI showcase scenarios

Nine synthetic company products are deliberately aligned to genuine FSAI
regulatory notices so the challenge demo can show three examples of each main outcome
without claiming access to a real retailer's ERP.

### CONFIRMED

Official FSAI Alert `2026.38`:

```text
K O'Connell Fishmongers Smoked Salmon Slices
Batch SS16726
```

Synthetic company SKU:

```text
SKU398
150g
Affected lot SS16726
17 units remaining
13 affected units dispatched
```

Expected deterministic outcome:

```text
CONFIRMED / EXACT_PRODUCT_AND_LOT_MATCH
```

### POSSIBLE

Official FSAI Alert `2026.52`:

```text
Tesco Sesame Seeds
100g
Affected batches 155 N01 and 203 N01
```

Synthetic company SKU:

```text
SKU399
Tesco Sesame Seeds
100g
Company lot code missing
24 units remaining
29 dispatched
```

Expected deterministic outcome:

```text
POSSIBLE / LOT_INFORMATION_MISSING
```

The local Llama 3.2 evidence-gap layer can then explain which evidence should
be verified next, while the classification remains deterministic.

### NOT_AFFECTED

Official FSAI Alert `2026.48`:

```text
SuperValu Sesame Seeds
200g
Affected batches 167 and 168
```

Synthetic company SKU:

```text
SKU400
SuperValu Sesame Seeds
200g
Company lots 997 / 998 / 999
```

Expected deterministic outcome:

```text
NOT_AFFECTED / LOT_MISMATCH
```

## Dashboard behaviour

The Investigation tab defaults to:

```text
Regulatory input = Official FSAI
```

Nine real showcase scenarios are labelled in the recall selector: three CONFIRMED,
three POSSIBLE and three NOT_AFFECTED. The first CONFIRMED FSAI scenario is the
default selection for the challenge demo.

Operators can switch to:

- Official FSAI
- Synthetic fallback / tests
- All

For official recalls the dashboard shows:

- FSAI alert ID
- source URL
- publication date
- extraction status
- source verification
- affected product/pack/lot/date scope
- source history / update versions
- original FSAI notice link

## Optional live refresh

The bundled snapshot is the recommended judging/demo mode because it is
repeatable and does not depend on internet availability.

Authorised Incident/Senior Manager users can optionally run:

```text
Overview -> Official FSAI regulatory feed -> Refresh official FSAI recalls
```

or:

```bash
python scripts/refresh_fsai_recalls.py
```

The live refresh:

1. runs the corrected Playwright scraper;
2. writes a temporary source CSV;
3. attaches the scraper review status;
4. normalises product scopes;
5. merges new/updated FSAI records into the existing snapshot;
6. preserves source history;
7. flags existing response cases for re-analysis when a stable recall scope
   changes.

The LLM is **not** allowed to invoke this external-source refresh itself.

## Setup for live refresh

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Windows users can run:

```bat
scripts\setup_full_windows.bat
```

The application itself continues to work from the bundled FSAI snapshot if the
website, internet connection or Chromium is unavailable.

## Validation

Run:

```bash
python scripts/validate_fsai_snapshot.py
python scripts/check_real_fsai_showcase.py
python scripts/daily_integration_check.py
```


## Recalled product images

The Investigation -> Public Recall Evidence panel now displays the regulator-
provided product image beside the structured recall fields.

SentiOH uses only image URLs captured from the official FSAI notice:

```text
image_url
image_urls
source_history[].image_url
```

The primary/current image is shown first. If several official images exist,
additional source-image links are retained under the source-detail expander.

If an FSAI notice does not contain a product image, the dashboard explicitly
shows:

```text
No product image was provided in the source recall notice.
```

SentiOH never generates or substitutes an artificial product image for
regulatory evidence.


## Clean completion for non-matching recalls

Most official FSAI notices are not deliberately present in the synthetic
company catalogue. This is expected. A no-match investigation now terminates
deterministically as soon as catalogue candidates are exhausted:

```text
NO_ORGANISATIONAL_EXPOSURE_IDENTIFIED
```

The normal no-match path no longer consumes an additional planner turn just to
discover that no candidates remain. The emergency bounded-agent limit has also
been increased from 12 to 16 steps, but ordinary non-matching recalls should
finish well before it.
