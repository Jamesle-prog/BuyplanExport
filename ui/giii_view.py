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
import shutil
import tempfile

import pandas as pd
import streamlit as st

from po_extractor.detectors import detect_files
from po_extractor.utils.client_template import CLIENT_ALIASES
from po_extractor.store.app_settings_store import (
    KEY_EXTRACTION_METHOD, KEY_DEEPSEEK_API_KEY, KEY_DEEPSEEK_MODEL,
)

from auth.users import get_user_companies, is_admin

from ui.shared import (
    show_image_folder_expander as _show_image_folder_expander,
    show_processing_log as _show_processing_log,
)
from ui.i18n import t
from ui.stores import get_store, get_app_settings_store

from ui.giii._shared import _XLSX_MIME, _CONF_BADGE
from ui.giii.extraction import _run_smart_processing
from ui.giii.excel_extraction import _run_excel_extraction
from ui.giii.results import _show_smart_downloads, _show_excel_downloads
from ui.giii.reference import _show_giii_reference_section, _compute_giii_missing_df
from ui.giii.history import _show_history
from ui.giii.missing_view import _show_giii_missing_fields_section
from ui.giii.reports_tab import _show_reports_tab
from ui.giii.msg_extraction import show_msg_upload_section as _show_msg_upload_section
from ui.giii.kl_extraction import show_kl_upload_section as _show_kl_upload_section
from ui.giii.infornexus_extraction import show_infornexus_upload_section as _show_infornexus_upload_section
from ui.giii.tk_eu_extraction import show_tk_eu_upload_section as _show_tk_eu_upload_section


# ---------------------------------------------------------------------------
# Excel client tab
# ---------------------------------------------------------------------------

def _show_excel_tab():
    st.subheader(t("Zalando Buy Plan"))
    st.caption(t(
        "Upload one or more client Excel files (each with a **1.1.PO_Client** sheet). "
        "The system merges them, detects repeat orders, and generates the buy plan + Template_P files."
    ))

    for key, default in [
        ("excel_results", None),
        ("excel_log", []),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    col_up, col_opt = st.columns([2, 1])
    with col_up:
        uploaded_excels = st.file_uploader(
            t("Upload client Excel file(s)"),
            type=["xlsx", "xlsm", "xls"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            help="Each file must contain a sheet named '1.1.PO_Client' with the two-row header mapping.",
            key="excel_uploader",
        )
        if uploaded_excels:
            st.caption(f"{len(uploaded_excels)} " + t("file(s) selected"))

    with col_opt:
        st.markdown(f"**{t('Options')}**")

        sheet_name = st.text_input(
            t("Source sheet name"),
            value="1.1.PO_Client",
            help="Name of the mapping sheet inside each Excel file.",
            key="excel_sheet_name",
        )

        pass  # photo folder is shown below as a separate expander

        client_profile = st.selectbox(
            t("Client profile"),
            ["(auto-detect)"] + list(CLIENT_ALIASES.keys()),
            help="Pre-loads known column aliases for the selected client.",
            key="excel_client_profile",
        )

    st.divider()

    # ── Template download (moved to Admin > Templates) ────────────────────────
    st.caption(t(
        "💡 Need a blank mapping template? Get it from **Admin → 📄 Templates → "
        "Client PO Mapping Template (1.1.PO_Client)**."
    ))

    _show_image_folder_expander("excel_images_dir", "excel_images_dir_apply")

    with st.expander("📊 " + t("大货进度表 (contract number lookup)"), expanded=False):
        st.caption(t(
            "Upload the production-progress Excel (大货进度表) to auto-fill **合同号** "
            "in the buy plan.  Leave blank to skip."
        ))
        progress_file = st.file_uploader(
            "大货进度表 Excel",
            type=["xlsx", "xlsm", "xls"],
            key="excel_progress_file",
            label_visibility="collapsed",
        )
        if progress_file:
            st.caption(f"✅ {progress_file.name}")

    if not uploaded_excels:
        st.info(t("Upload one or more client Excel files to get started."))
        return

    excel_mask = st.checkbox(
        t("Mask prices in output files"),
        value=False,
        key="excel_mask_prices",
        help="Replace FOB / cost / price columns with *** before download.",
    )

    if st.button("▶  " + t("Process Excel Files"), type="primary", use_container_width=True, key="run_excel"):
        st.session_state.excel_results = None
        st.session_state.excel_log = []
        _run_excel_extraction(
            uploaded_excels,
            sheet_name=sheet_name,
            mask_prices=excel_mask,
            progress_file=progress_file,
        )

    if st.session_state.excel_log:
        _show_processing_log(st.session_state.excel_log)

    if st.session_state.excel_results:
        _show_excel_downloads(st.session_state.excel_results)


# ---------------------------------------------------------------------------
# GIII upload section (inner tab of Smart Upload)
# ---------------------------------------------------------------------------

def _show_giii_upload_section():
    """Upload + process panel (inner tab of GIII)."""
    st.markdown(f"**{t('PO Files')}** (PDF · XLSX · XLSM · XLS)")
    uploaded = st.file_uploader(
        t("Upload PO files"),
        type=["pdf", "xlsx", "xlsm", "xls"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="smart_uploader",
    )
    if uploaded:
        st.caption(f"{len(uploaded)} " + t("file(s) selected"))

    with st.expander("➕ " + t("Reference files (Fabric Mapping)")):
        _show_giii_reference_section()

    _show_image_folder_expander("giii_images_dir", "giii_images_dir_apply")

    mask_prices = st.checkbox(
        "🔒 " + t("Mask prices"),
        value=False,
        key="smart_mask_prices",
        help="Replace FOB / cost / price values with *** in all output files.",
    )

    # ── AI Extraction toggle ──────────────────────────────────────────────────
    _settings = get_app_settings_store()
    _default_method = _settings.get(KEY_EXTRACTION_METHOD, "regex")
    _api_key        = _settings.get(KEY_DEEPSEEK_API_KEY, "")
    _ds_model       = _settings.get(KEY_DEEPSEEK_MODEL, "deepseek-chat")

    with st.expander("🤖 " + t("AI Extraction (DeepSeek)"), expanded=(_default_method == "deepseek")):
        st.caption(t(
            "Use the DeepSeek API to extract PO fields instead of the built-in regex parser.  "
            "Useful for non-standard layouts or when you want AI-assisted field recognition."
        ))
        use_ai = st.toggle(
            t("Use DeepSeek AI extraction"),
            value=(_default_method == "deepseek"),
            key="smart_use_ai",
        )
        if use_ai:
            session_key = st.text_input(
                t("API Key (leave blank to use admin-configured key)"),
                value="",
                type="password",
                placeholder="sk-… (optional override)",
                key="smart_ds_api_key_override",
            )
            effective_key = session_key.strip() or _api_key
            if not effective_key:
                st.warning("⚠️ " + t("No DeepSeek API key configured. Set one in Admin → Settings or enter above."))
            else:
                st.caption(f"{t('Model')}: `{_ds_model}` · " + t("key ending") + f" …{effective_key[-4:]}")
        else:
            effective_key = ""

    st.divider()

    if not uploaded:
        st.info(t("Upload one or more PO files (PDF or Excel) to begin."))
        return

    # ── Auto-detect ───────────────────────────────────────────────────────────
    tmpdir = tempfile.mkdtemp()
    try:
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

        if st.button("▶  " + t("Process all files"), type="primary",
                     use_container_width=True, key="smart_run"):
            st.session_state.smart_results = None
            st.session_state.smart_log = []
            _use_ai   = st.session_state.get("smart_use_ai", False)
            _eff_key  = st.session_state.get("smart_ds_api_key_override", "").strip() or _api_key
            _run_smart_processing(
                detections, saved_paths, mask_prices,
                use_ai=_use_ai, deepseek_api_key=_eff_key, deepseek_model=_ds_model,
            )
    finally:
        # Files have been read into memory (detection + processing) — temp dir no longer needed
        shutil.rmtree(tmpdir, ignore_errors=True)

    if st.session_state.smart_log:
        _show_processing_log(st.session_state.smart_log)

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
        ("rpt_all_results",  None),
        ("rpt_cp_bytes",     None),
        ("rpt_ps_bytes",     None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    st.subheader("📦 " + t("GIII PO Processing"))
    st.caption(t(
        "Upload PDF or Excel PO files — client and format are auto-detected per file. "
        "PDFs produce Buy Plan · Color Plan · PO Summary · Cross-Check. "
        "Excel files produce HHP Buy Plan · Template_P workbooks."
    ))

    # Badge counts.  An unassigned non-admin gets an empty frame — passing the
    # empty list through would hit the store's falsy check and count EVERY
    # company's exceptions.
    _store    = get_store()
    _user_cos = get_user_companies(st.session_state.username)
    if _user_cos or is_admin(st.session_state.username):
        _exc_df = _store.list_exceptions(companies=_user_cos if _user_cos else None)
    else:
        _exc_df = pd.DataFrame()
    _exc_count = (len(_exc_df[_exc_df["status"] == "pending"])
                  if not _exc_df.empty and "status" in _exc_df.columns else 0)
    history_label = f"📚 {t('PO History')}" + (f"  🔴 {_exc_count}" if _exc_count else "")

    _missing_df    = _compute_giii_missing_df()
    _missing_count = len(_missing_df)
    missing_label  = f"✏️ {t('Missing Fields')}" + (
        f"  🔴 {_missing_count}" if _missing_count else ""
    )

    # "Generate / Export" (not "Reports") — same name as Sky East's output tab,
    # since both regenerate downloadable files from stored data. 📦 is the
    # output emoji app-wide; 📤 stays reserved for uploads.
    tab_upload, tab_history, tab_reports, tab_missing = st.tabs(
        [f"📤 {t('Upload')}", history_label,
         f"📦 {t('Generate / Export')}", missing_label]
    )

    with tab_upload:
        _show_giii_upload_section()
        _show_msg_upload_section()
        _show_kl_upload_section()
        _show_infornexus_upload_section()
        _show_tk_eu_upload_section()

    with tab_history:
        _show_history(exc_df=_exc_df)

    with tab_reports:
        _show_reports_tab()

    with tab_missing:
        _show_giii_missing_fields_section(_missing_df)
