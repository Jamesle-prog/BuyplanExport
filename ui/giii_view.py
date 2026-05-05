"""GIII Smart Upload tab — shell entry point.

Implementation is split across the ui/giii/ sub-package:
  _shared.py      — MIME aliases, badge map, live_label(), schema cache
  extraction.py        — PDF extraction pipeline + smart processing
  excel_extraction.py  — Excel/HHP extraction pipeline
  results.py      — download buttons and report generators
  reference.py    — fabric mapping import / missing-data helpers
  history.py      — PO history tab (_show_history)
  missing_view.py — Missing-fields editor (_show_giii_missing_fields_section)
"""
from __future__ import annotations

import io
import os
import tempfile

import pandas as pd
import streamlit as st

from po_extractor.detectors import detect_files
from po_extractor.utils.client_template import CLIENT_ALIASES

from auth.users import get_user_companies

from ui.shared import (
    show_image_folder_expander as _show_image_folder_expander,
)
from ui.stores import get_store

from ui.giii._shared import _XLSX_MIME, _CONF_BADGE
from ui.giii.extraction import _run_smart_processing
from ui.giii.excel_extraction import _run_excel_extraction
from ui.giii.results import _show_smart_downloads, _show_excel_downloads
from ui.giii.reference import _show_giii_reference_section, _compute_giii_missing_df
from ui.giii.history import _show_history
from ui.giii.missing_view import _show_giii_missing_fields_section


# ---------------------------------------------------------------------------
# Excel client tab
# ---------------------------------------------------------------------------

def _show_excel_tab():
    st.subheader("Zalando Buy Plan")
    st.caption(
        "Upload one or more client Excel files (each with a **1.1.PO_Client** sheet). "
        "The system merges them, detects repeat orders, and generates the buy plan + Template_P files."
    )

    for key, default in [
        ("excel_results", None),
        ("excel_log", []),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    col_up, col_opt = st.columns([2, 1])
    with col_up:
        uploaded_excels = st.file_uploader(
            "Upload client Excel file(s)",
            type=["xlsx", "xlsm", "xls"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            help="Each file must contain a sheet named '1.1.PO_Client' with the two-row header mapping.",
            key="excel_uploader",
        )
        if uploaded_excels:
            st.caption(f"{len(uploaded_excels)} file(s) selected")

    with col_opt:
        st.markdown("**Options**")

        sheet_name = st.text_input(
            "Source sheet name",
            value="1.1.PO_Client",
            help="Name of the mapping sheet inside each Excel file.",
            key="excel_sheet_name",
        )

        pass  # photo folder is shown below as a separate expander

        client_profile = st.selectbox(
            "Client profile",
            ["(auto-detect)"] + list(CLIENT_ALIASES.keys()),
            help="Pre-loads known column aliases for the selected client.",
            key="excel_client_profile",
        )

    st.divider()

    # ── Template download (moved to Admin > Templates) ────────────────────────
    st.caption(
        "💡 Need a blank mapping template? Get it from **Admin → 📄 Templates → "
        "Client PO Mapping Template (1.1.PO_Client)**."
    )

    _show_image_folder_expander("excel_images_dir", "excel_images_dir_apply")

    if not uploaded_excels:
        st.info("Upload one or more client Excel files to get started.")
        return

    excel_mask = st.checkbox(
        "Mask prices in output files",
        value=False,
        key="excel_mask_prices",
        help="Replace FOB / cost / price columns with *** before download.",
    )

    if st.button("▶  Process Excel Files", type="primary", use_container_width=True, key="run_excel"):
        st.session_state.excel_results = None
        st.session_state.excel_log = []
        _run_excel_extraction(
            uploaded_excels,
            sheet_name=sheet_name,
            mask_prices=excel_mask,
        )

    if st.session_state.excel_log:
        with st.expander("Processing log", expanded=False):
            for line in st.session_state.excel_log:
                st.markdown(line, unsafe_allow_html=True)

    if st.session_state.excel_results:
        _show_excel_downloads(st.session_state.excel_results)


# ---------------------------------------------------------------------------
# GIII upload section (inner tab of Smart Upload)
# ---------------------------------------------------------------------------

def _show_giii_upload_section():
    """Upload + process panel (inner tab of GIII)."""
    st.markdown("**PO Files** (PDF · XLSX · XLSM · XLS)")
    uploaded = st.file_uploader(
        "Upload PO files",
        type=["pdf", "xlsx", "xlsm", "xls"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="smart_uploader",
    )
    if uploaded:
        st.caption(f"{len(uploaded)} file(s) selected")

    with st.expander("➕ Reference files (Fabric Mapping)"):
        _show_giii_reference_section()

    _show_image_folder_expander("giii_images_dir", "giii_images_dir_apply")

    mask_prices = st.checkbox(
        "🔒 Mask prices",
        value=False,
        key="smart_mask_prices",
        help="Replace FOB / cost / price values with *** in all output files.",
    )

    st.divider()

    if not uploaded:
        st.info("Upload one or more PO files (PDF or Excel) to begin.")
        return

    # ── Auto-detect ───────────────────────────────────────────────────────────
    tmpdir = tempfile.mkdtemp()
    saved_paths: dict[str, str] = {}
    for uf in uploaded:
        p = os.path.join(tmpdir, uf.name)
        with open(p, "wb") as f:
            f.write(uf.getbuffer())
        saved_paths[uf.name] = p

    detections = detect_files(list(saved_paths.values()))
    st.session_state.smart_detections = detections

    # ── Detection summary table ───────────────────────────────────────────────
    table_rows = []
    for d in detections:
        primary = d.companies[0] if d.companies else "Unknown"
        badge   = _CONF_BADGE.get(d.confidence, "⚪")
        table_rows.append({
            "File":       d.filename,
            "Type":       d.file_type.upper(),
            "Client":     primary,
            "Format":     d.format_id,
            "Confidence": f"{badge} {d.confidence}",
            "Detail":     d.detail or d.error or "",
        })
    st.dataframe(pd.DataFrame(table_rows), width="stretch", hide_index=True)

    st.divider()

    if st.button("▶  Process all files", type="primary",
                 use_container_width=True, key="smart_run"):
        st.session_state.smart_results = None
        st.session_state.smart_log = []
        _run_smart_processing(detections, saved_paths, mask_prices)

    if st.session_state.smart_log:
        with st.expander("Processing log", expanded=False):
            for line in st.session_state.smart_log:
                st.markdown(line, unsafe_allow_html=True)

    if st.session_state.smart_results:
        _show_smart_downloads(st.session_state.smart_results)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def show_smart_upload_tab():
    """Unified upload: accepts PDF + Excel, auto-detects client/format per file."""

    for key, default in [
        ("smart_detections", None),
        ("smart_results",    None),
        ("smart_log",        []),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    st.subheader("📦 GIII PO Processing")
    st.caption(
        "Upload PDF or Excel PO files — client and format are auto-detected per file. "
        "PDFs produce Buy Plan · Color Plan · PO Summary · Cross-Check. "
        "Excel files produce HHP Buy Plan · Template_P workbooks."
    )

    # Badge counts
    _store    = get_store()
    _user_cos = get_user_companies(st.session_state.username)
    _exc_df   = _store.list_exceptions(companies=_user_cos if _user_cos else None)
    _exc_count = (len(_exc_df[_exc_df["status"] == "pending"])
                  if not _exc_df.empty and "status" in _exc_df.columns else 0)
    history_label = "📚 PO History" + (f"  🔴 {_exc_count}" if _exc_count else "")

    _missing_df    = _compute_giii_missing_df()
    _missing_count = len(_missing_df)
    missing_label  = (
        f"✏️ Missing Fields  🔴 {_missing_count}" if _missing_count else "✏️ Missing Fields"
    )

    tab_upload, tab_history, tab_missing = st.tabs(
        ["📤 Upload", history_label, missing_label]
    )

    with tab_upload:
        _show_giii_upload_section()

    with tab_history:
        _show_history(exc_df=_exc_df)

    with tab_missing:
        _show_giii_missing_fields_section(_missing_df)
