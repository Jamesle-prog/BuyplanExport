"""GIII Reports tab — regenerate outputs from stored PO history + PO Tracker."""
from __future__ import annotations

import streamlit as st
import pandas as pd

from auth.users import get_user_companies, is_admin
from ui.i18n import t
from ui.session_keys import SK
from ui.shared import lazy_sections, guard_multiselect_state
from ui.stores import get_store
from ui.giii._shared import _XLSX_MIME
from ui.giii.extraction import _run_from_history
from ui.giii.results import (
    _show_downloads,
    _generate_color_plan_excel,
    _generate_po_summary_excel,
    _generate_kl_format_excel_bytes,
)
from po_extractor.ui_helpers.kl_consistency import check_kl_excel as _check_kl_excel
from po_extractor.exporters.giii_production_plan import generate_giii_production_plan
from ui.summary_view import _build_tracker_excel, _TRACKER_COLS, _DEFAULT_COLS


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _show_reports_tab(pos_df: pd.DataFrame | None = None) -> None:
    """Reports tab: generate Excel outputs + PO Tracker.

    *pos_df* is the company-scoped list_pos frame fetched once per rerun in
    show_smart_upload_tab; a direct read remains as fallback for other
    callers.
    """
    store    = get_store()
    username = st.session_state.get(SK.USERNAME, "")
    user_cos = get_user_companies(username)
    admin    = is_admin(username)
    # Non-admin with no assigned companies must see nothing — an empty list
    # falls through the store's falsy check to an unfiltered query.
    if not admin and not user_cos:
        st.info(t(
            "No companies assigned to your account. "
            "Contact an administrator to be granted access."
        ))
        return
    df = (pos_df if pos_df is not None
          else store.list_pos(companies=user_cos if user_cos else None))

    lazy_sections([
        (f"📥 {t('Generate Outputs')}",
         lambda: _show_generate_section(df, store)),
        (f"📋 {t('PO Tracker')}",
         lambda: _show_tracker_section(df, user_cos, admin)),
    ], key="giii_reports_section_nav")


# ---------------------------------------------------------------------------
# Generate Outputs sub-tab
# ---------------------------------------------------------------------------

def _resolve_po_requirements(selected: list[str], filt_df: pd.DataFrame,
                             manual: dict | None, translate) -> dict:
    """Resolve CPRS requirements for *selected* POs, stash the preview +
    warnings for the panel below, and return ``{po_number: RowRequirements}``.
    Thin wrapper over the shared builder's resolver (``ui.giii._buyplan``) so the
    "Check requirements only" button and the buy-plan build share one resolver.
    """
    from ui.giii._buyplan import resolve_reqs
    from ui.stores import get_cprs_client

    df = filt_df[filt_df["po_number"].isin(selected)]
    reqs, warns, preview = resolve_reqs(get_cprs_client(), df, manual, translate)
    st.session_state["rpt_cprs_warns"] = warns
    st.session_state["rpt_cprs_preview"] = preview
    return reqs


def _show_generate_section(df: pd.DataFrame, store) -> None:
    st.markdown(f"**{t('Generate Excel outputs from stored PO data')}**")
    st.caption(t(
        "Filter and select POs below, then click **Generate All Outputs** to rebuild "
        "Buy Plan · Color Plan · PO Summary · Cross-Check from the stored data — "
        "no re-upload required."
    ))

    if df.empty:
        st.info(t("No POs stored yet. Upload PDFs via the **Upload** tab to get started."))
        return

    # ── Filters ──────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        companies = sorted(df["company"].dropna().unique().tolist()) if "company" in df.columns else []
        guard_multiselect_state("rpt_co_filter", companies)
        sel_co = st.multiselect(t("Company"), companies, key="rpt_co_filter")
    with fc2:
        seasons = sorted(df["season"].dropna().unique().tolist()) if "season" in df.columns else []
        guard_multiselect_state("rpt_season_filter", seasons)
        sel_season = st.multiselect(t("Season"), seasons, key="rpt_season_filter")
    with fc3:
        divs = sorted(df["division_name"].dropna().unique().tolist()) if "division_name" in df.columns else []
        guard_multiselect_state("rpt_div_filter", divs)
        sel_div = st.multiselect(t("Division"), divs, key="rpt_div_filter")

    filt_df = df.copy()
    if sel_co:
        filt_df = filt_df[filt_df["company"].isin(sel_co)]
    if sel_season:
        filt_df = filt_df[filt_df["season"].isin(sel_season)]
    if sel_div:
        filt_df = filt_df[filt_df["division_name"].isin(sel_div)]

    # ── PO selector ───────────────────────────────────────────────────────────
    # Seed once (pre-select all visible POs), then guard — key= together with
    # default= is the CLAUDE.md-banned desync pattern: the default is ignored
    # once widget state exists, and stale POs silently blank the selection.
    po_opts = filt_df["po_number"].tolist()
    if "rpt_po_select" not in st.session_state:
        st.session_state["rpt_po_select"] = po_opts
    else:
        guard_multiselect_state("rpt_po_select", po_opts)
    selected = st.multiselect(
        f"{t('Select POs')} ({len(po_opts)} {t('available after filters')}):",
        options=po_opts,
        placeholder=t("Select one or more PO numbers…"),
        key="rpt_po_select",
    )
    if not po_opts:
        st.warning(t("No POs match the current filters."))
        return
    st.caption(f"**{len(selected)}** {t('PO(s) selected')}")

    # ── CPRS buy-plan runtime inputs (values CPRS can't provide) ──────────────
    with st.expander("🧭 " + t("Buy Plan requirement inputs (for CPRS buy plan)")):
        st.caption(t(
            "Values CPRS resolves at runtime, not from the PO. The red sticker "
            "is only required for prepack orders — when it is, it must show the "
            "pre-pack DIM code below. Requirement wording from CPRS is in English; "
            "enable translation to render it in Chinese on the buy plan."
        ))
        mc1, mc2 = st.columns(2)
        with mc1:
            st.text_input(t("Red sticker DIM code (pre-pack)"), key="rpt_dim_code",
                          placeholder="e.g. MY",
                          help=t("Default for every PO; override per PO below."))
        with mc2:
            st.text_input(t("PCs per box (factory pack-out)"), key="rpt_pcs_box",
                          placeholder="e.g. 36")
        # Per-PO DIM overrides — POs in one generation can carry different
        # pre-pack codes. Seed from the current selection, keep prior edits.
        prev = {r["PO"]: r["DIM"] for r in st.session_state.get("rpt_dim_rows", [])}
        dim_df = st.data_editor(
            pd.DataFrame({"PO": selected,
                          "DIM": [prev.get(po, "") for po in selected]}),
            hide_index=True, use_container_width=True, key="rpt_dim_editor",
            column_config={"PO": st.column_config.TextColumn(disabled=True)},
        )
        st.session_state["rpt_dim_rows"] = dim_df.to_dict("records")
        st.checkbox(t("Translate CPRS requirement text to Chinese (DeepSeek)"),
                    key="rpt_cprs_translate", value=False)

    st.divider()

    # ── Action buttons — row 1 ────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        if st.button(
            "📊 " + t("Generate All Outputs"),
            type="primary",
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_all_btn",
        ):
            st.session_state.pop("rpt_all_results", None)
            _run_from_history(selected, result_key="rpt_all_results")

    with c2:
        if st.button(
            "🎨 " + t("Color Plan Only"),
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_cp_btn",
        ):
            st.session_state.pop("rpt_cp_bytes", None)
            with st.spinner(t("Building color plan…")):
                cp_bytes = _generate_color_plan_excel(selected, store)
            if cp_bytes:
                st.session_state["rpt_cp_bytes"] = cp_bytes
            else:
                st.warning(t("No size data found for selected POs."))

    with c3:
        if st.button(
            "📋 " + t("PO Summary Only"),
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_ps_btn",
        ):
            st.session_state.pop("rpt_ps_bytes", None)
            ps_df = filt_df[filt_df["po_number"].isin(selected)]
            with st.spinner(t("Building PO summary…")):
                df_sizes = store.load_size_rows(selected)
                ps_bytes = _generate_po_summary_excel(ps_df, df_sizes=df_sizes)
            st.session_state["rpt_ps_bytes"] = ps_bytes

    with c4:
        if st.button(
            "📐 " + t("KL Format Summary"),
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_kl_btn",
            help="Two-sheet Excel: PO Detail + Summary (KL-reference format)",
        ):
            st.session_state.pop("rpt_kl_bytes", None)
            kl_df = filt_df[filt_df["po_number"].isin(selected)]
            with st.spinner(t("Building KL-format summary…")):
                df_sizes = store.load_size_rows(selected)
                kl_bytes = _generate_kl_format_excel_bytes(kl_df, df_sizes)
            if kl_bytes:
                # Consistency check — warn in UI but don't block the download
                issues = _check_kl_excel(kl_df, df_sizes, kl_bytes, verbose=False)
                if issues:
                    st.warning(
                        t("**KL summary consistency check failed** — "
                          "the file may have missing rows:") + "\n\n"
                        + "\n".join(f"- {i}" for i in issues)
                    )
                st.session_state["rpt_kl_bytes"] = kl_bytes
            else:
                st.warning(t("No size data found for selected POs."))

    # ── Action buttons — row 2 ────────────────────────────────────────────────
    c5, c6, _c7, _c8 = st.columns(4)

    def _cprs_manual_inputs() -> dict:
        return {"dim_code": st.session_state.get("rpt_dim_code", ""),
                "pcs_box": st.session_state.get("rpt_pcs_box", ""),
                "dim_codes": {r["PO"]: r["DIM"]
                              for r in st.session_state.get("rpt_dim_rows", [])
                              if str(r.get("DIM", "")).strip()}}

    def _cprs_translator():
        if st.session_state.get("rpt_cprs_translate"):
            from ui.giii._shared import make_en_to_cn_translator
            return make_en_to_cn_translator()
        return None
    with c5:
        if st.button(
            "📋 " + t("Create Buy Plan (生产计划单)"),
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_bp_btn",
            help=t(
                "Generate the GIII production plan (生产计划单) — one sheet per "
                "style with size breakdown, 面料 rows from the style-fabric "
                "table, 合同号 and Chinese colours from the 大货进度表, and "
                "红色箱贴纸 / 主箱唛 (text + artwork) resolved live from CPRS. "
                "Without CPRS configured those cells fall back to blank/无."
            ),
        ):
            st.session_state.pop("rpt_bp_bytes", None)
            with st.spinner(t("Building buy plan (resolving CPRS requirements)…")):
                try:
                    from ui.giii._buyplan import build_giii_production_plan
                    from ui.stores import get_cprs_client
                    bp_bytes, warns, preview = build_giii_production_plan(
                        selected, store, cprs=get_cprs_client(),
                        manual=_cprs_manual_inputs(), translate=_cprs_translator())
                    st.session_state["rpt_cprs_warns"] = warns
                    st.session_state["rpt_cprs_preview"] = preview
                    if bp_bytes:
                        st.session_state["rpt_bp_bytes"] = bp_bytes
                    else:
                        st.warning(t("No size data found for the selected POs."))
                except Exception as exc:
                    st.error(t("Production plan generation failed:") + f" {exc}")

    with c6:
        if st.button(
            "🔍 " + t("Check requirements only"),
            disabled=not selected,
            use_container_width=True,
            key="rpt_check_cprs_btn",
            help=t("Resolve CPRS requirements for the selected POs and show "
                   "the preview below — without generating a workbook."),
        ):
            with st.spinner(t("Resolving CPRS requirements…")):
                try:
                    _resolve_po_requirements(
                        selected, filt_df, _cprs_manual_inputs(), _cprs_translator())
                except Exception as exc:
                    st.error(t("Requirements check failed:") + f" {exc}")

    # ── API requirements document (CPRS /export/requirements-doc) ─────────────
    # Same section as the upload-time results panel, fed from the STORED data
    # for the current selection — request bodies are rebuilt (pure, no CPRS
    # traffic) whenever the selection changes.
    if selected:
        _sig = tuple(sorted(selected))
        _cache = st.session_state.get("rpt_api_reqs_cache")
        if not _cache or _cache[0] != _sig:
            try:
                from po_extractor.ui_helpers.giii_requirements import (
                    api_requests_from_stored,
                )
                _meta = filt_df[filt_df["po_number"].isin(selected)]
                _reqs, _warns = api_requests_from_stored(
                    _meta, store.load_size_rows(selected))
            except Exception as _exc:
                _reqs, _warns = [], [f"API document unavailable: {_exc}"]
            _cache = (_sig, _reqs, _warns)
            st.session_state["rpt_api_reqs_cache"] = _cache
        from ui.giii.results import _show_requirements_api_section
        _show_requirements_api_section(
            {"requirements_api_reqs": _cache[1],
             "requirements_api_warns": _cache[2]},
            key_prefix="rpt",
        )
        if not _cache[1]:
            # The section renders nothing without requests — surface WHY
            # (e.g. no brand decodable on any selected PO).
            for _w in _cache[2]:
                st.warning(f"🧭 {_w}")

    # ── Download area ─────────────────────────────────────────────────────────
    if st.session_state.get("rpt_all_results"):
        _show_downloads(st.session_state["rpt_all_results"], key_prefix="rpt")

    if st.session_state.get("rpt_cp_bytes"):
        st.download_button(
            "⬇️ " + t("Download Color Plan (.xlsx)"),
            data=st.session_state["rpt_cp_bytes"],
            file_name="Color_Plan.xlsx",
            mime=_XLSX_MIME,
            key="rpt_cp_dl",
        )

    if st.session_state.get("rpt_ps_bytes"):
        st.download_button(
            "⬇️ " + t("Download PO Summary (.xlsx)"),
            data=st.session_state["rpt_ps_bytes"],
            file_name="PO_Summary.xlsx",
            mime=_XLSX_MIME,
            key="rpt_ps_dl",
        )

    if st.session_state.get("rpt_kl_bytes"):
        st.download_button(
            "⬇️ " + t("Download KL Format Summary (.xlsx)"),
            data=st.session_state["rpt_kl_bytes"],
            file_name="PO_Summary_KL.xlsx",
            mime=_XLSX_MIME,
            key="rpt_kl_dl",
        )

    if st.session_state.get("rpt_bp_bytes"):
        st.download_button(
            "⬇️ " + t("Download Buy Plan — 生产计划单 (.xlsx)"),
            data=st.session_state["rpt_bp_bytes"],
            file_name="GIII_Production_Plan.xlsx",
            mime=_XLSX_MIME,
            key="rpt_bp_dl",
        )

    # Preview + warnings render for BOTH flows: check-only and generate.
    if st.session_state.get("rpt_cprs_preview") is not None:
        for w in st.session_state.get("rpt_cprs_warns", []):
            st.warning(f"🧭 {w}")
        preview = st.session_state.get("rpt_cprs_preview")
        if preview:
            with st.expander("🧭 " + t("CPRS requirement resolution (verify before sending)"),
                             expanded=not st.session_state.get("rpt_bp_bytes")
                                      or bool(st.session_state.get("rpt_cprs_warns"))):
                st.dataframe(pd.DataFrame(preview), use_container_width=True,
                             hide_index=True)


# ---------------------------------------------------------------------------
# PO Tracker sub-tab
# ---------------------------------------------------------------------------

def _show_tracker_section(df: pd.DataFrame, user_cos: list, admin: bool) -> None:
    st.markdown(f"**{t('PO Tracker — commercial detail view')}**")
    st.caption(t("One row per PO with all extracted commercial fields. Filter, pick columns, and download."))

    if df.empty:
        st.info(t("No POs stored yet. Upload PDFs via the **Upload** tab."))
        return

    # ── Filters ──────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        seasons = sorted(df["season"].dropna().unique().tolist()) if "season" in df.columns else []
        guard_multiselect_state("trk_season", seasons)
        sel_s = st.multiselect(t("Season"), seasons, key="trk_season")
    with fc2:
        divs = sorted(df["division_name"].dropna().unique().tolist()) if "division_name" in df.columns else []
        guard_multiselect_state("trk_div", divs)
        sel_d = st.multiselect(t("Division"), divs, key="trk_div")
    with fc3:
        buyers = sorted(df["buyer"].dropna().unique().tolist()) if "buyer" in df.columns else []
        guard_multiselect_state("trk_buyer", buyers)
        sel_b = st.multiselect(t("Buyer"), buyers, key="trk_buyer")

    view = df.copy()
    if sel_s:
        view = view[view["season"].isin(sel_s)]
    if sel_d:
        view = view[view["division_name"].isin(sel_d)]
    if sel_b:
        view = view[view["buyer"].isin(sel_b)]

    # ── Column selector ───────────────────────────────────────────────────────
    # Seed once + guard instead of key= AND default= (banned desync pattern).
    avail   = [k for k in _TRACKER_COLS if k in view.columns]
    default = [k for k in _DEFAULT_COLS  if k in avail]
    if "trk_cols" not in st.session_state:
        st.session_state["trk_cols"] = default
    else:
        guard_multiselect_state("trk_cols", avail)
    picked  = st.multiselect(
        t("Columns"),
        options=avail,
        format_func=lambda k: _TRACKER_COLS.get(k, k),
        key="trk_cols",
    )
    show_cols  = picked or default
    display_df = view[show_cols].rename(columns=_TRACKER_COLS)

    st.caption(f"**{len(display_df):,}** {t('PO(s)')}")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Download ──────────────────────────────────────────────────────────────
    xlsx = _build_tracker_excel(display_df)
    st.download_button(
        "⬇️ " + t("Download PO Tracker (.xlsx)"),
        data=xlsx,
        file_name="po_tracker.xlsx",
        mime=_XLSX_MIME,
        key="trk_dl",
    )
