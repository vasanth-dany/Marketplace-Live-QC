"""
Central configuration for Marketplace Live QC.

Column matching is done by HEADER NAME, never by fixed position — the
CANONICAL_COLUMNS map lists acceptable header text variants per field.
Add more variants here if a marketplace's export uses different wording,
rather than touching excel_reader.py itself.
"""

# ── Sheet layout ──────────────────────────────────────────────
SHEET_NAME = "Main"
HEADER_ROW = 2       # Row 2 = actual column headers
DATA_START_ROW = 4   # Row 1 = instructions, Row 3 = required/optional, data from Row 4

# ── Canonical field -> acceptable header text (lowercase) ─────
CANONICAL_COLUMNS = {
    "seller_sku":     ["seller sku", "sellersku"],
    "product_name":   ["product name"],
    "description":    ["product description", "description"],
    "rrp":            ["rrp"],
    "sale_price":     ["sale price", "srp"],
    "stock":          ["stock"],
    "image_url":      ["image url", "image urls", "product image url(s)", "image url(s)"],
    "category_id":    ["category id", "category"],
    "weight":         ["weight"],
    "length":         ["length"],
    "width":          ["width"],
    "height":         ["height"],
    "variation_1":    ["variation 1"],
    "variation_2":    ["variation 2"],
    "variation_3":    ["variation 3"],
    "brand":          ["brand"],
    "mp_live_url":    ["mp live url"],
}

# Fields that live on the PARENT row (apply to the whole product group)
PARENT_FIELDS = [
    "product_name", "description", "image_url", "brand",
    "category_id", "weight", "length", "width", "height", "mp_live_url",
]

# Fields that live on CHILD (variation) rows
CHILD_FIELDS = [
    "seller_sku", "variation_1", "variation_2", "variation_3",
    "stock", "rrp", "sale_price", "image_url",
]

REQUIRED_COLUMNS = ["mp_live_url", "product_name", "seller_sku"]

# ── QC fields toggle-able in the dashboard ─────────────────────
QC_FIELDS = {
    "product_name": "Product Name",
    "description":  "Description",
    "images":       "Images",
    "brand":        "Brand",
    "category":     "Category",
    "price":        "Price",
    "sale_price":   "Sale Price",
    "stock":        "Stock",
    "weight":       "Weight",
    "dimensions":   "Dimensions",
    "variations":   "Variations",
    "attributes":   "Attributes",
}
# V1.0 scope: default to just the two fields we're validating first
# (product name + price). All fields remain toggle-able in the dashboard —
# turn more on once the Shopee extractor is calibrated against real pages.
DEFAULT_ENABLED_QC_FIELDS = ["product_name", "price"]

# ── Marketplace registry ───────────────────────────────────────
# Every entry here must expose a `scrape_product(url) -> dict` function
# returning the STANDARD PRODUCT MODEL (see modules/marketplaces/base.py).
MARKETPLACES = {
    "Shopee":   "marketplaces.shopee",
    "Lazada":   "marketplaces.lazada",
    "TikTok Shop": "marketplaces.tiktok",
    "Shopify":  "marketplaces.shopify",
    "Amazon":   "marketplaces.amazon",
    "Zalora":   "marketplaces.zalora",
}
IMPLEMENTED_MARKETPLACES = ["Shopee"]  # others aren't implemented yet — selecting
# them will show a clear "module not found" error rather than crashing. To add
# one: create marketplaces/<name>.py with a scrape_product() returning the
# standard product model (see modules/utils.py), then add it here.

# ── Paths ───────────────────────────────────────────────────────
UPLOADS_DIR = "uploads"
REPORTS_DIR = "reports"
SCREENSHOTS_DIR = "screenshots"
LOGS_DIR = "logs"

# ── Tolerances ───────────────────────────────────────────────────
PRICE_TOLERANCE = 0.01  # allow float rounding noise
