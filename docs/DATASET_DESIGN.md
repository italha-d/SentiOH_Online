# Expanded synthetic business sandbox

This repository uses a fixed random seed (`20260903`) so the business sandbox
is reproducible.

## Scale

- Catalogue products: 400
- Suppliers: 25
- Batch/lot records: 900
- Operational sites: 3
- Inventory records: 661
- Purchase orders: 628
- Downstream dispatch records: 785
- Locked labelled scenarios: 12

## Deliberate evaluation coverage

The sandbox includes:
- true affected products;
- same-product wrong-lot cases;
- similar-name false positives;
- missing-lot `POSSIBLE` cases;
- wrong pack-size cases;
- unrelated products.

`demo_data/ground_truth_scenarios.csv` contains the expected outcome for every
locked scenario.

## Provenance

All company-side records are synthetic. The bundled recall records are also
synthetic placeholders and remain marked `is_public_source_verified=false`.
They must not be represented as genuine FSAI notices.
