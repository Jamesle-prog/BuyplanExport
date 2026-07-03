"""GIII Reports tab — regenerate outputs from stored PO history + PO Tracker."""
from __future__ import annotations

import streamlit as st
import pandas as pd

from auth.users import get_user_companies, is_admin
from ui.session_keys import SK
from ui.stores import get_store
from ui.giii._shared import _XLSX_MIME, live_label
from ui.giii.extraction import _run_from_history, _create_buyplan_bytes
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

def _show_reports_tab() -> None:
    """Reports tab: generate Excel outputs + PO Tracker."""
    store    = get_store()
    username = st.session_state.get(SK.USERNAME, "")
    user_cos = get_user_companies(username)
    admin    = is_admin(username)
    # Non-admin with no assigned companies must see nothing — an empty list
    # falls through the store's falsy check to an unfiltered query.
    if not admin and not user_cos:
        st.info(
            "No companies assigned to your account. "
            "Contact an administrator to be granted access."
        )
        return
    df       = store.list_pos(companies=user_cos if user_cos else None)

    sub_gen, sub_tracker = st.tabs(["📥 Generate Outputs", "📋 PO Tracker"])

    with sub_gen:
        _show_generate_section(df, store)

    with sub_tracker:
        _show_tracker_section(df, user_cos, admin)


# ---------------------------------------------------------------------------
# Generate Outputs sub-tab
# ---------------------------------------------------------------------------

def _show_generate_section(df: pd.DataFrame, store) -> None:
    st.markdown("**Generate Excel outputs from stored PO data**")
    st.caption(
        "Filter and select POs below, then click **Generate All Outputs** to rebuild "
        "Buy Plan · Color Plan · PO Summary · Cross-Check from the stored data — "
        "no re-upload required."
    )

    if df.empty:
        st.info("No POs stored yet. Upload PDFs via the **Upload** tab to get started.")
        return

    # ── Filters ──────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        companies = sorted(df["company"].dropna().unique().tolist()) if "company" in df.columns else []
        sel_co = st.multiselect("Company", companies, key="rpt_co_filter")
    with fc2:
        seasons = sorted(df["season"].dropna().unique().tolist()) if "season" in df.columns else []
        sel_season = st.multiselect("Season", seasons, key="rpt_season_filter")
    with fc3:
        divs = sorted(df["division_name"].dropna().unique().tolist()) if "division_name" in df.columns else []
        sel_div = st.multiselect("Division", divs, key="rpt_div_filter")

    filt_df = df.copy()
    if sel_co:
        filt_df = filt_df[filt_df["company"].isin(sel_co)]
    if sel_season:
        filt_df = filt_df[filt_df["season"].isin(sel_season)]
    if sel_div:
        filt_df = filt_df[filt_df["division_name"].isin(sel_div)]

    # ── PO selector ───────────────────────────────────────────────────────────
    po_opts = filt_df["po_number"].tolist()
    selected = st.multiselect(
        f"Select POs ({len(po_opts)} available after filters):",
        options=po_opts,
        default=po_opts,          # pre-select all visible POs
        placeholder="Select one or more PO numbers…",
        key="rpt_po_select",
    )
    if not po_opts:
        st.warning("No POs match the current filters.")
        return
    st.caption(f"**{len(selected)}** PO(s) selected")

    st.divider()

    # ── Action buttons — row 1 ────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        if st.button(
            "📊 Generate All Outputs",
            type="primary",
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_all_btn",
        ):
            st.session_state.pop("rpt_all_results", None)
            _run_from_history(selected, result_key="rpt_all_results")

    with c2:
        if st.button(
            "🎨 Color Plan Only",
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_cp_btn",
        ):
            st.session_state.pop("rpt_cp_bytes", None)
            with st.spinner("Building color plan…"):
                cp_bytes = _generate_color_plan_excel(selected, store)
            if cp_bytes:
                st.session_state["rpt_cp_bytes"] = cp_bytes
            else:
                st.warning("No size data found for selected POs.")

    with c3:
        if st.button(
            "📋 PO Summary Only",
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_ps_btn",
        ):
            st.session_state.pop("rpt_ps_bytes", None)
            ps_df = filt_df[filt_df["po_number"].isin(selected)]
            with st.spinner("Building PO summary…"):
                df_sizes = store.load_size_rows(selected)
                ps_bytes = _generate_po_summary_excel(ps_df, df_sizes=df_sizes)
            st.session_state["rpt_ps_bytes"] = ps_bytes

    with c4:
        if st.button(
            "📐 KL Format Summary",
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_kl_btn",
            help="Two-sheet Excel: PO Detail + Summary (KL-reference format)",
        ):
            st.session_state.pop("rpt_kl_bytes", None)
            kl_df = filt_df[filt_df["po_number"].isin(selected)]
            with st.spinner("Building KL-format summary…"):
                df_sizes = store.load_size_rows(selected)
                kl_bytes = _generate_kl_format_excel_bytes(kl_df, df_sizes)
            if kl_bytes:
                # Consistency check — warn in UI but don't block the download
                issues = _check_kl_excel(kl_df, df_sizes, kl_bytes, verbose=False)
                if issues:
                    st.warning(
                        "**KL summary consistency check failed** — "
                        "the file may have missing rows:\n\n"
                        + "\n".join(f"- {i}" for i in issues)
                    )
                st.session_state["rpt_kl_bytes"] = kl_bytes
            else:
                st.warning("No size data found for selected POs.")

    # ── Action buttons — row 2 ────────────────────────────────────────────────
    c5, _c6, _c7, _c8 = st.columns(4)
    with c5:
        if st.button(
            "📋 Create Buy Plan (生产计划单)",
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_bp_btn",
            help=(
                "Generate a GIII production plan (生产计划单) in the standard "
                "factory buy plan format — one sheet per style, with size breakdown, "
                "Chinese colours, and merged rows."
            ),
        ):
            st.session_state.pop("rpt_bp_bytes", None)
            with st.spinner("Building production plan…"):
                try:
                    bp_bytes = generate_giii_production_plan(selected, store)
                    if bp_bytes:
                        st.session_state["rpt_bp_bytes"] = bp_bytes
                    else:
                        st.warning("No size data found for the selected POs.")
                except Exception as exc:
                    st.error(f"Production plan generation failed: {exc}")

    # ── Download area ─────────────────────────────────────────────────────────
    if st.session_state.get("rpt_all_results"):
        _show_downloads(st.session_state["rpt_all_results"], key_prefix="rpt")

    if st.session_state.get("rpt_cp_bytes"):
        st.download_button(
            "⬇️ Download Color Plan (.xlsx)",
            data=st.session_state["rpt_cp_bytes"],
            file_name="Color_Plan.xlsx",
            mime=_XLSX_MIME,
            key="rpt_cp_dl",
        )

    if st.session_state.get("rpt_ps_bytes"):
        st.download_button(
            "⬇️ Download PO Summary (.xlsx)",
            data=st.session_state["rpt_ps_bytes"],
            file_name="PO_Summary.xlsx",
            mime=_XLSX_MIME,
            key="rpt_ps_dl",
        )

    if st.session_state.get("rpt_kl_bytes"):
        st.download_button(
            "⬇️ Download KL Format Summary (.xlsx)",
            data=st.session_state["rpt_kl_bytes"],
            file_name="PO_Summary_KL.xlsx",
            mime=_XLSX_MIME,
            key="rpt_kl_dl",
        )

    if st.session_state.get("rpt_bp_bytes"):
        st.download_button(
            "⬇️ Download Buy Plan — 生产计划单 (.xlsx)",
            data=st.session_state["rpt_bp_bytes"],
            file_name="GIII_Production_Plan.xlsx",
            mime=_XLSX_MIME,
            key="rpt_bp_dl",
        )


# ---------------------------------------------------------------------------
# PO Tracker sub-tab
# ---------------------------------------------------------------------------

def _show_tracker_section(df: pd.DataFrame, user_cos: list, admin: bool) -> None:
    st.markdown("**PO Tracker — commercial detail view**")
    st.caption("One row per PO with all extracted commercial fields. Filter, pick columns, and download.")

    if df.empty:
        st.info("No POs stored yet. Upload PDFs via the **Upload** tab.")
        return

    # ── Filters ──────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        seasons = sorted(df["season"].dropna().unique().tolist()) if "season" in df.columns else []
        sel_s = st.multiselect("Season", seasons, key="trk_season")
    with fc2:
        divs = sorted(df["division_name"].dropna().unique().tolist()) if "division_name" in df.columns else []
        sel_d = st.multiselect("Division", divs, key="trk_div")
    with fc3:
        buyers = sorted(df["buyer"].dropna().unique().tolist()) if "buyer" in df.columns else []
        sel_b = st.multiselect("Buyer", buyers, key="trk_buyer")

    view = df.copy()
    if sel_s:
        view = view[view["season"].isin(sel_s)]
    if sel_d:
        view = view[view["division_name"].isin(sel_d)]
    if sel_b:
        view = view[view["buyer"].isin(sel_b)]

    # ── Column selector ───────────────────────────────────────────────────────
    avail   = [k for k in _TRACKER_COLS if k in view.columns]
    default = [k for k in _DEFAULT_COLS  if k in avail]
    picked  = st.multiselect(
        "Columns",
        options=avail,
        default=default,
        format_func=lambda k: _TRACKER_COLS.get(k, k),
        key="trk_cols",
    )
    show_cols  = picked or default
    display_df = view[show_cols].rename(columns=_TRACKER_COLS)

    st.caption(f"**{len(display_df):,}** PO(s)")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Download ──────────────────────────────────────────────────────────────
    xlsx = _build_tracker_excel(display_df)
    st.download_button(
        "⬇️ Download PO Tracker (.xlsx)",
        data=xlsx,
        file_name="po_tracker.xlsx",
        mime=_XLSX_MIME,
        key="trk_dl",
    )
