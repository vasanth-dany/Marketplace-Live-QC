"""
Shopee scraper.

Strategy: rather than parsing rendered HTML/DOM (fragile — breaks on any
front-end change), we let a real headless browser load the page and
INTERCEPT the internal JSON API call the page itself makes to fetch
product data. This is far more stable across Shopee's frequent UI updates.

⚠️ CALIBRATION NEEDED ON FIRST REAL RUN
This sandbox environment has no network access to shopee.com, so this
could not be tested against a real live page. Shopee's internal endpoint
is commonly something like `/api/v4/pdp/get_pc` or `/api/v4/item/get`,
but the exact path/version and JSON shape can differ by country domain
and change over time. On your first real run:
  1. Temporarily uncomment the `print(response.url)` line in
     `_handle_response` below.
  2. Run a check against one real Shopee URL.
  3. Confirm/update MATCH_PATTERNS and the field paths in
     `_parse_payload()` to match what you actually see.
This is a one-time calibration, not ongoing maintenance.
"""

import re
from playwright.sync_api import sync_playwright

from modules.utils import empty_result
from modules.logger import get_logger

logger = get_logger("shopee")

MATCH_PATTERNS = [
    "/api/v4/pdp/get_pc",
    "/api/v4/item/get",
    "/api/v4/pdp/get",
]


def _looks_like_pdp_api(url: str) -> bool:
    return any(p in url for p in MATCH_PATTERNS)


def scrape_product(url: str, screenshot_path: str | None = None, timeout_ms: int = 20000) -> dict:
    captured = {"payload": None, "url": None}

    def _handle_response(response):
        try:
            # print(response.url)  # uncomment for first-run calibration
            if _looks_like_pdp_api(response.url) and response.status == 200:
                if "json" in response.headers.get("content-type", ""):
                    captured["payload"] = response.json()
                    captured["url"] = response.url
        except Exception:
            pass

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("response", _handle_response)
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            page.wait_for_timeout(2000)  # let late XHR calls settle

            if screenshot_path:
                try:
                    page.screenshot(path=screenshot_path, full_page=True)
                except Exception as e:
                    logger.warning(f"Screenshot failed for {url}: {e}")

            browser.close()
    except Exception as e:
        logger.error(f"Page load failed for {url}: {e}")
        return empty_result(f"page load failed: {e}")

    if not captured["payload"]:
        logger.warning(f"No PDP API response captured for {url}")
        return empty_result("no PDP API response captured — check MATCH_PATTERNS in shopee.py")

    return _parse_payload(captured["payload"])


def _parse_payload(payload: dict) -> dict:
    """
    TODO — CALIBRATE AFTER FIRST REAL RUN.
    Best-guess shape based on Shopee's commonly seen get_pc response:
    payload["data"]["item"] with name/description/images/models(variations).

    Each field is extracted independently (its own try/except) so that a
    V1.0 run — which only needs product_name + price — isn't blanked out
    entirely if a more speculative field (variations, dimensions,
    attributes) doesn't parse cleanly. This is deliberately more
    defensive than a single big try/except around the whole function.
    """
    item = payload.get("data", {}).get("item", {}) or {}
    result = empty_result(None)
    field_errors = []

    def safe(field_name, fn):
        try:
            return fn()
        except Exception as e:
            field_errors.append(f"{field_name}: {e}")
            return None

    # ── Core V1.0 fields — product_name and price ──
    result["product_name"] = safe("product_name", lambda: item.get("name"))
    result["price"] = safe("price", lambda: _to_price(item.get("price_max") or item.get("price")))
    result["sale_price"] = safe("sale_price", lambda: _to_price(item.get("price_min") or item.get("price")))

    if result["product_name"] is None and result["price"] is None:
        # Both core fields failed — this is a genuine extraction failure worth surfacing.
        return empty_result(f"could not extract product_name or price from payload: {field_errors}")

    # ── Everything else: best-effort, won't block V1.0's core comparison ──
    result["description"] = safe("description", lambda: item.get("description"))
    result["images"] = safe("images", lambda: item.get("images", []) or []) or []
    result["brand"] = safe("brand", lambda: item.get("brand"))
    result["category"] = safe("category", lambda: item.get("category_name") or item.get("categories"))
    result["stock"] = safe("stock", lambda: item.get("stock"))
    result["weight"] = safe("weight", lambda: item.get("weight"))
    result["dimensions"] = safe("dimensions", lambda: {
        "length": item.get("dimension", {}).get("package_length"),
        "width": item.get("dimension", {}).get("package_width"),
        "height": item.get("dimension", {}).get("package_height"),
    }) or {"length": None, "width": None, "height": None}
    result["attributes"] = safe("attributes", lambda: {
        a.get("name"): a.get("value") for a in item.get("attributes", []) if a.get("name")
    }) or {}
    result["variations"] = safe("variations", lambda: _extract_variations(item)) or []

    if field_errors:
        logger.warning(f"Partial parse — some non-core fields failed: {field_errors}")

    return result


def _extract_variations(item: dict) -> list:
    variations = []
    for model in item.get("models", []):
        tier_names = model.get("name", "").split(",") if model.get("name") else []
        variations.append({
            "seller_sku": model.get("extinfo", {}).get("sku") or model.get("sku") or "",
            "variation_1": tier_names[0].strip() if len(tier_names) > 0 else "",
            "variation_2": tier_names[1].strip() if len(tier_names) > 1 else "",
            "variation_3": tier_names[2].strip() if len(tier_names) > 2 else "",
            "stock": model.get("stock"),
            "price": _to_price(model.get("price")),
            "sale_price": _to_price(model.get("price_before_discount") or model.get("price")),
            "variant_image": model.get("image"),
        })
    return variations


def _to_price(val):
    # Shopee prices are commonly returned in the smallest currency unit * 100000
    try:
        return float(val) / 100000
    except (ValueError, TypeError):
        return None
