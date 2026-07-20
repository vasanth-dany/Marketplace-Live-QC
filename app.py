import importlib
import os
import subprocess

import streamlit as st

from config import MARKETPLACES, IMPLEMENTED_MARKETPLACES, UPLOADS_DIR, SCREENSHOTS_DIR
from modules.excel_reader import load_source_file, get_unique_products, ExcelStructureError
from modules.comparator import compare_product
from modules.report_generator import generate_report
from modules.utils import init_session_state, render_qc_field_checkboxes
from modules.logger import get_logger

logger = get_logger("app")


@st.cache_resource
def _ensure_playwright_browser_installed():
    """Streamlit Community Cloud (and similar hosts) only run `pip install
    -r requirements.txt` — there's no separate step for `playwright install
    chromium`. This runs it once per deployment (cached so it doesn't re-run
    on every rerun) so Playwright has a browser binary to launch. Locally,
    if you've already run `playwright install chromium` yourself, this is a
    fast no-op."""
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True, capture_output=True, timeout=300)
    except Exception as e:
        logger.warning(f"Playwright browser install step failed or was skipped: {e}")


_ensure_playwright_browser_installed()

st.set_page_config(page_title="Marketplace Live QC", layout="wide")
init_session_state()

st.title("🔍 Marketplace Live QC Automation")
st.caption("Verifies live marketplace listings match your source Excel file — no manual QC needed.")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# ── Sidebar: marketplace + QC field selection ──────────────────
with st.sidebar:
    st.header("Configuration")

    marketplace = st.selectbox(
        "Marketplace",
        options=list(MARKETPLACES.keys()),
        index=list(MARKETPLACES.keys()).index(st.session_state.selected_marketplace),
    )
    st.session_state.selected_marketplace = marketplace

    if marketplace not in IMPLEMENTED_MARKETPLACES:
        st.warning(f"⚠️ {marketplace} is registered but not yet implemented. Selecting it will report an error per product instead of scraping.")

    enabled_fields = render_qc_field_checkboxes()

    st.divider()
    capture_screenshots = st.checkbox("Capture screenshot on FAIL", value=True)

    st.divider()
    st.subheader("V1.0 Test Mode")
    test_mode = st.checkbox(
        "Limit to first N products", value=True,
        help="Recommended while calibrating a new marketplace extractor — "
             "validate against a small batch before running the full catalog."
    )
    test_limit = st.number_input("N", min_value=1, max_value=1000, value=1, disabled=not test_mode)

# ── Main: upload + run ──────────────────────────────────────────
uploaded_file = st.file_uploader("Upload source Excel file", type=["xlsx"])

if uploaded_file is None:
    st.info("Upload your source Excel file (Main sheet, headers on row 2, data from row 4) to begin.")
    st.stop()

try:
    df = load_source_file(uploaded_file)
    unique_products = get_unique_products(df)
except ExcelStructureError as e:
    st.error(f"❌ {e}")
    st.stop()

st.success(f"Loaded {len(unique_products)} product(s) with {len(df) - len(unique_products)} variation row(s).")

run_clicked = st.button("▶️ Run Live QC", type="primary")

if not run_clicked and st.session_state.last_results is None:
    st.stop()

if run_clicked:
    module_path = MARKETPLACES[marketplace]
    try:
        mp_module = importlib.import_module(module_path)
    except ImportError as e:
        st.error(f"Could not load marketplace module '{module_path}': {e}")
        st.stop()

    progress = st.progress(0, text="Starting QC run...")
    metric_cols = st.columns(3)
    loaded_metric = metric_cols[0].empty()
    passed_metric = metric_cols[1].empty()
    failed_metric = metric_cols[2].empty()

    run_products = unique_products.head(test_limit) if test_mode else unique_products
    if test_mode:
        st.info(f"🧪 Test mode: checking only the first {len(run_products)} of {len(unique_products)} product(s).")

    results = []
    passed_count = failed_count = 0
    total = len(run_products)

    for i, (_, parent_row) in enumerate(run_products.iterrows(), 1):
        group_id = parent_row["group_id"]
        group = df[df["group_id"] == group_id]
        url = parent_row.get("mp_live_url")
        sku = parent_row.get("seller_sku") or parent_row.get("product_name") or f"row_{i}"

        progress.progress(i / total, text=f"Checking {i}/{total}: {sku}")

        if not url or not str(url).strip():
            live = {"error": "MP Live URL is blank for this product"}
        else:
            screenshot_path = os.path.join(SCREENSHOTS_DIR, f"{sku}.png") if capture_screenshots else None
            live = mp_module.scrape_product(str(url).strip(), screenshot_path=screenshot_path)

        result = compare_product(group, live, enabled_fields)
        if capture_screenshots and result["overall_status"] == "FAIL":
            result["screenshot_path"] = os.path.join(SCREENSHOTS_DIR, f"{sku}.png")

        results.append(result)

        if result["overall_status"] == "PASS":
            passed_count += 1
        else:
            failed_count += 1

        loaded_metric.metric("Products Loaded", f"{i}/{total}")
        passed_metric.metric("Products Passed", passed_count)
        failed_metric.metric("Products Failed", failed_count)

    progress.progress(1.0, text="Done.")
    st.session_state.last_results = results

    report_path = generate_report(results, marketplace)
    st.session_state.last_report_path = report_path

# ── Results ──────────────────────────────────────────────────────
results = st.session_state.last_results
if results:
    st.divider()
    st.subheader("Results")

    total = len(results)
    passed = sum(1 for r in results if r["overall_status"] == "PASS")
    failed = total - passed

    m1, m2, m3 = st.columns(3)
    m1.metric("Products Loaded", total)
    m2.metric("Products Passed", passed)
    m3.metric("Products Failed", failed)

    status_filter = st.multiselect("Filter by status", ["PASS", "FAIL"], default=["FAIL"])
    for r in results:
        if r["overall_status"] not in status_filter:
            continue
        with st.expander(f"{'✅' if r['overall_status'] == 'PASS' else '❌'} {r['sku']} — {r['overall_status']}"):
            if r["fail_reasons"]:
                st.write("**Fail reasons:**", "; ".join(r["fail_reasons"]))
            st.dataframe(
                [{"Row": fr["row_type"], "Field": fr["field"], "Expected": fr["expected"],
                  "Live": fr["live"], "Status": fr["status"]} for fr in r["field_results"]],
                use_container_width=True,
            )
            if r.get("screenshot_path") and os.path.exists(r["screenshot_path"]):
                st.image(r["screenshot_path"], caption="Failure screenshot", width=300)

    if st.session_state.last_report_path and os.path.exists(st.session_state.last_report_path):
        with open(st.session_state.last_report_path, "rb") as f:
            st.download_button(
                "📥 Export Report",
                data=f.read(),
                file_name=os.path.basename(st.session_state.last_report_path),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
