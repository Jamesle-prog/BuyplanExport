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
from ui.session_keys import SK
from ui.stores import get_store, get_app_settings_store

from ui.giii._shared import _XLSX_MIME, _CONF_BADGE, files_signature
from ui.giii.extraction import _run_smart_processing
from ui.giii.excel_extraction import _run_excel_extraction
from ui.giii.results import _show_smart_downloads, _show_excel_downloads
from ui.giii.reference import _compute_giii_missing_df
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

def _classify_other_pos(files) -> dict[str, list]:
    """Group the combined uploader's files by detected PO type.

    Content-based: each file's PDF text (first pages; .msg unwrapped first)
    goes through the specialized-PO classifier. Cached per uploaded file
    set — classification reads every file, so it must not re-run on every
    Streamlit rerun (same pattern as the main uploader's detection cache).
    """
    sig = files_signature(files)
    if (st.session_state.get(SK.GIII_OTHER_SIG) == sig
            and st.session_state.get(SK.GIII_OTHER_GROUPS) is not None):
        return st.session_state[SK.GIII_OTHER_GROUPS]

    from po_extractor.detectors.specialized_po import classify_giii_po_text
    from po_extractor.utils.pdf_reader import read_pdf_bytes_text
    from ui.giii._shared import iter_pdf_payloads

    cls_by_name: dict[str, str] = {}
    with st.spinner(t("Detecting PO types…")):
        for name, pdf_bytes, _subject in iter_pdf_payloads(files):
            try:
                text = read_pdf_bytes_text(pdf_bytes, max_pages=3)
            except Exception:
                text = ""
            cls_by_name[name] = classify_giii_po_text(text)

    groups: dict[str, list] = {}
    for uf in files:
        # Files iter_pdf_payloads skipped (unreadable .msg, no attachment)
        # fall into "unknown" so they are surfaced, not silently dropped.
        groups.setdefault(cls_by_name.get(uf.name, "unknown"), []).append(uf)

    st.session_state[SK.GIII_OTHER_GROUPS] = groups
    st.session_state[SK.GIII_OTHER_SIG] = sig
    return groups


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

    # Fabric mapping upload used to be duplicated here in an expander; it is
    # managed centrally in the 📐 Reference Data tab (per company, persistent),
    # so this tab only points there now.
    st.caption("💡 " + t(
        "Style-Fabric mapping and HHN contract progress are managed in the "
        "📐 Reference Data tab — upload them once there, every run uses the "
        "saved data."
    ))

    _show_image_folder_expander("giii_images_dir", "giii_images_dir_apply")

    mask_prices = st.checkbox(
        "🔒 " + t("Mask prices"),
        value=False,
        key="smart_mask_prices",
        help="Replace FOB / cost / price values with *** in all output files.",
    )

    # ── AI extraction is an admin-level choice (Admin → Settings) ────────────
    # The per-run toggle + session key override that used to live here was a
    # second place to configure the same thing; the admin setting alone now
    # decides, and this page just shows the active mode.
    _settings = get_app_settings_store()
    _method   = _settings.get(KEY_EXTRACTION_METHOD, "regex")
    _api_key  = _settings.get(KEY_DEEPSEEK_API_KEY, "")
    _ds_model = _settings.get(KEY_DEEPSEEK_MODEL, "deepseek-chat")
    _use_ai   = (_method in ("deepseek", "auto"))
    if _method == "auto" and _api_key:
        st.caption("⚡ " + t(
            "Auto extraction is ON — the instant built-in parser runs first, "
            "and only low-confidence or unparsed files fall back to AI."
        ) + f" `{_ds_model}`")
    elif _method == "deepseek" and _api_key:
        st.caption("🤖 " + t(
            "AI extraction (DeepSeek) is ON — configured by your admin in "
            "Admin → Settings."
        ) + f" `{_ds_model}`")
    elif _use_ai and not _api_key:
        st.warning("⚠️ " + t(
            "AI extraction is enabled but no DeepSeek API key is configured — "
            "files will be processed with the built-in parser. Set the key in "
            "Admin → Settings."
        ))

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

        # Detection reads every PDF — cache it per uploaded file set, or any
        # widget interaction on this tab (a checkbox, an expander) re-parses
        # the whole batch on the rerun. Same signature pattern the results
        # panels use.
        _det_sig = files_signature(uploaded)
        if st.session_state.get(SK.GIII_DETECT_SIG) == _det_sig \
                and st.session_state.get(SK.GIII_DETECTIONS) is not None:
            detections = st.session_state[SK.GIII_DETECTIONS]
        else:
            detections = detect_files(list(saved_paths.values()))
            st.session_state[SK.GIII_DETECTIONS] = detections
            st.session_state[SK.GIII_DETECT_SIG] = _det_sig
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
            # No key → force regex regardless of the configured method, so a
            # deepseek/auto setting without a key still processes files.
            _eff_method = _method if (_method in ("deepseek", "auto") and _api_key) else "regex"
            _run_smart_processing(
                detections, saved_paths, mask_prices,
                method=_eff_method,
                deepseek_api_key=_api_key, deepseek_model=_ds_model,
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
    # Tab bar mirrors the Sky East tab exactly — same order AND the same
    # menu names (New Contracts → Generate/Export → Contract History →
    # Missing Fields; GIII orders carry HHN contract numbers via the
    # 大货进度表, so "contract" applies to this pipeline too). The 🔴 on
    # Contract History is the pending-exception alert and is GIII-specific;
    # it stays.
    history_label = t("Contract History") + (f"  🔴 {_exc_count}" if _exc_count else "")

    # Scope to the user's companies (admin → all); an unassigned non-admin
    # gets an empty frame, never every company's POs.
    if _user_cos or is_admin(st.session_state.username):
        _missing_df = _compute_giii_missing_df(companies=_user_cos or None)
    else:
        _missing_df = pd.DataFrame()
    _missing_count = len(_missing_df)
    _mf = t("Missing Fields")
    missing_label  = (f"{_mf}  {_missing_count}" if _missing_count else _mf)

    tab_upload, tab_reports, tab_history, tab_missing = st.tabs(
        [t("New Contracts"), f"📦 {t('Generate / Export')}",
         history_label, missing_label]
    )

    with tab_upload:
        _show_giii_upload_section()

        # Combined specialized-PO uploader: one drop zone, each file's type
        # detected from its CONTENT (extension is untrustworthy — the same
        # fax documents arrive both inside .msg emails and as bare PDFs) and
        # routed to the right extractor automatically.
        st.divider()
        st.markdown(f"**{t('Other PO types')}**")
        st.caption(t(
            "Drop fax .msg emails or fax/portal PDFs here — each file's PO "
            "type (MSG fax / KL / InforNexus / TK EU) is detected "
            "automatically from its content and routed to the right "
            "extractor below."
        ))
        other_files = st.file_uploader(
            "Other PO files", type=["msg", "pdf"], accept_multiple_files=True,
            label_visibility="collapsed", key="other_po_uploader",
        )
        if other_files:
            groups = _classify_other_pos(other_files)

            unknown = groups.get("unknown", [])
            if unknown:
                st.warning("❓ " + t(
                    "Could not determine the PO type of:"
                ) + " " + ", ".join(uf.name for uf in unknown))

            for cls, icon, label, renderer in [
                ("vendor_fax",  "📧", "MSG / Vendor Fax POs",           _show_msg_upload_section),
                ("kl",          "📄", "KL PO PDFs",                     _show_kl_upload_section),
                ("infor_nexus", "🗂", "InforNexus POs",                 _show_infornexus_upload_section),
                ("tk_eu",       "🇬🇧", "TK EU POs (Kostroma / TJX UK)",  _show_tk_eu_upload_section),
            ]:
                subset = groups.get(cls, [])
                if not subset:
                    continue
                with st.expander(f"{icon} {t(label)} ({len(subset)})", expanded=True):
                    renderer(files=subset)

    with tab_history:
        _show_history(exc_df=_exc_df)

    with tab_reports:
        _show_reports_tab()

    with tab_missing:
        _show_giii_missing_fields_section(_missing_df)
