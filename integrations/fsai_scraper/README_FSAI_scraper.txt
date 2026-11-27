FSAI Recall Scraper
===================

Purpose
-------
Automates extraction of FSAI Food Alert recall records into an Excel-friendly CSV.

Output columns
--------------
Recall ID
Product Name
Brand
Pack Size
Batch Code
Use By
Best Before
Hazard
Published Date
Source URL
Image URL

Installation
------------
1. Install Python 3.10+.
2. In Command Prompt / PowerShell:

   pip install -r requirements_fsai.txt
   python -m playwright install chromium

Example
-------
python fsai_recall_scraper.py --from-date 2026-01-01 --to-date 2026-09-07 --output fsai_recalls.csv

Then open fsai_recalls.csv directly in Excel.

Why Playwright?
---------------
The FSAI site may reject simple requests-based scrapers. Playwright uses a real Chromium
browser, which is generally more reliable for pages protected against basic automated HTTP
requests.

Quality control
---------------
The program also writes:
    fsai_recalls_needs_review.csv

This contains rows where the page had ambiguous/missing fields. The scraper intentionally
does not invent missing values.

Notes
-----
- Recall ID is stored as text, so values such as 2026.50 remain 2026.50 rather than 2026.5.
- Dates are stored as ISO YYYY-MM-DD to avoid Excel serial-number ambiguity.
- Pack sizes are kept exactly as published rather than converted.
- Source URL is the actual FSAI page URL.


Corrected parser behaviour
--------------------------
This version fixes a major issue in the original parser: FSAI pages can contain
both an Alert Summary key/value table and a separate product-detail table.

The corrected parser:
- never treats Alert Summary labels such as "Batch Code" or
  "Country Of Origin" as product names;
- expands HTML rowspan and colspan before mapping columns;
- propagates shared product, pack-size and date cells across affected rows;
- ignores category/retailer group headings that contain no product scope;
- requires stronger evidence before considering a table a product table;
- preserves ambiguous pages in the *_needs_review.csv output rather than
  inventing product details.

Regression tests:
    python -m pytest -q test_parser_regressions.py
