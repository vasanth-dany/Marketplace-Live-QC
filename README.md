# Marketplace Live QC Automation

Automates Live QC for marketplace listings: compares your source Excel file
against what's actually live, per marketplace, and produces a 4-sheet Excel
report plus screenshots of failures.

## Architecture

```
Marketplace-Live-QC/
├── app.py                    Streamlit dashboard
├── config.py                 Column-name mapping, QC field defs, marketplace registry
├── requirements.txt
├── modules/
│   ├── excel_reader.py       Reads Main sheet, identifies columns by HEADER NAME
│   │                         (never fixed position), groups parent/child rows
│   ├── comparator.py         Marketplace-agnostic comparison engine — only
│   │                         knows the "standard product model" (see below)
│   ├── report_generator.py   Generates the 4-sheet Excel report
│   ├── logger.py             Shared logging
│   └── utils.py              Standard product model contract + dashboard
│                             session-state helpers
├── marketplaces/
│   └── shopee.py             ✅ Implemented (V1.0: product_name + price)
├── uploads/
├── reports/
├── screenshots/
├── logs/
└── assets/
```

**Key design decision:** every marketplace module returns the same "standard
product model" shape (defined in `modules/utils.py`). The comparator, report
generator, and dashboard never contain marketplace-specific logic — adding a
new marketplace only means creating `marketplaces/<name>.py` with its own
`scrape_product()`. Nothing else changes.

**On scaling beyond Live QC:** this design already generalizes — a future
Price QC / Image QC / Campaign QC / etc. module can reuse `excel_reader.py`,
`logger.py`, and the marketplace scrapers as-is, adding only its own
comparison rules. Worth revisiting the folder layout as a proper multi-module
"Operations Hub" once Live QC v1.0 is proven working end-to-end against real
marketplace pages — restructuring before that would be premature.

## V1.0 scope

V1.0 deliberately narrows to just **product_name + price** while the Shopee
extractor gets calibrated against real pages (see `config.DEFAULT_ENABLED_QC_FIELDS`).
All other QC fields remain toggle-able in the dashboard — turn them on once
you've confirmed the core extraction works.

The dashboard also has a **Test Mode** (sidebar) that limits a run to the
first N products (default 1) — use this to validate against a single real
product before running the full catalog.

`marketplaces/shopee.py`'s parsing is hardened so `product_name`/`price`
survive independently even if a more speculative field (variations,
dimensions, attributes) fails to parse — each field is extracted in its own
try/except rather than one big block that blanks everything on any error.

## Source Excel requirements
- Sheet must be named `Main`.
- Row 1: instructions (ignored).
- Row 2: column headers — matched by name (see `config.CANONICAL_COLUMNS`
  for accepted header text per field; add variants there if your file uses
  different wording).
- Row 3: required/optional markers (ignored).
- Row 4+: product data. A row with a non-blank **Product Name** starts a
  new parent product; rows below it (with a **Seller SKU**) are its
  variations, until the next Product Name.
- **MP Live URL** column is required — the app errors clearly if it's missing.

## Running it

```bash
pip install -r requirements.txt --break-system-packages
playwright install --with-deps chromium
streamlit run app.py
```

1. Upload your source Excel file.
2. Pick the marketplace (only Shopee is implemented for now).
3. Toggle which QC fields to check (defaults to product_name + price for V1.0).
4. Optionally enable **Test Mode** and set N to validate against a small
   batch first.
5. Click **Run Live QC** — progress bar and live pass/fail counts update as
   it goes.
6. Expand any product to see the field-by-field breakdown; failures show
   their screenshot if enabled.
7. Click **Export Report** for the 4-sheet Excel report.

## ⚠️ Calibration needed on first real run

This code was built in a sandbox with **no network access to shopee.com**,
so `marketplaces/shopee.py` could not be tested against a real live page.
It's built on the commonly-documented shape of Shopee's internal PDP API,
but on your first real run:

1. Turn on **Test Mode** with N=1 and run against a single real product URL.
2. If you see `"no PDP API response captured"` in the results, Shopee's
   internal endpoint path doesn't match `MATCH_PATTERNS` in `shopee.py`.
3. Uncomment the `print(response.url)` line inside `_handle_response()`,
   re-run, and note the actual API path Shopee calls.
4. Update `MATCH_PATTERNS` and the field lookups in `_parse_payload()` to
   match the real JSON shape you see.

This is a one-time calibration — once confirmed, it should keep working
until Shopee changes their front-end/API.

Everything else (Excel reading, parent/child grouping, comparison logic,
report generation, error handling, and the hardened partial-parse logic)
**was tested locally** against synthetic files and confirmed working
correctly, including catching deliberate mismatches and missing-column
errors, and confirming core fields survive even when a non-core field
throws an error.

## Adding a new marketplace (e.g. Lazada)

1. Create `marketplaces/lazada.py`.
2. Follow the same pattern as `shopee.py`: use Playwright to load the page,
   intercept the internal API response (or parse embedded JSON if the
   marketplace doesn't use an XHR API), and map the result into the
   standard product model from `modules/utils.py`.
3. Add `"Lazada"` to `IMPLEMENTED_MARKETPLACES` in `config.py`.
4. Nothing in `comparator.py`, `report_generator.py`, or `app.py` needs to change.
