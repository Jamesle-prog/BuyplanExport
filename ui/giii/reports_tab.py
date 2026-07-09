"""GIII Reports tab — regenerate outputs from stored PO history + PO Tracker."""
from __future__ import annotations

import streamlit as st
import pandas as pd

from auth.users import get_user_companies, is_admin
from ui.i18n import t
from ui.session_keys import SK
from ui.shared import guard_multiselect_state
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
        st.info(t(
            "No companies assigned to your account. "
            "Contact an administrator to be granted access."
        ))
        return
    df       = store.list_pos(companies=user_cos if user_cos else None)

    sub_gen, sub_tracker = st.tabs([f"📥 {t('Generate Outputs')}", f"📋 {t('PO Tracker')}"])

    with sub_gen:
        _show_generate_section(df, store)

    with sub_tracker:
        _show_tracker_section(df, user_cos, admin)


# ---------------------------------------------------------------------------
# Generate Outputs sub-tab
# ---------------------------------------------------------------------------

def _build_cprs_buyplan(selected: list[str], store, filt_df: pd.DataFrame) -> bytes | None:
    """Assemble and export the CPRS-integrated GIII buy plan for *selected* POs."""
    from po_extractor.exporters import (
        assemble_buyplan_rows, export_giii_buyplan, BuyPlanHeader,
    )
    from po_extractor.ui_helpers.combined_summary import build_contract_maps
    from po_extractor.utils.cprs_client import cprs_from_settings
    from ui.fabric_mapping_view import _company_to_source
    from ui.stores import get_app_settings_store

    df_size = store.load_size_rows(selected)
    if df_size is None or df_size.empty:
        return None
    df_meta = filt_df[filt_df["po_number"].isin(selected)].copy()

    # Contract numbers AND Chinese colours both come from the 大货进度表.
    progress: list[dict] = []
    if "company" in df_meta.columns:
        for comp in df_meta["company"].dropna().unique():
            progress.extend(store.load_progress_records(_company_to_source(str(comp))))
    by_po, by_style = build_contract_maps(progress)

    # 中文颜色 from 进度表: {EN colour (upper) -> CN colour}.
    color_lookup: dict[str, str] = {}
    for rec in progress:
        en = str(rec.get("color", "") or "").strip().upper()
        cn = rec.get("cn_color", "") or ""
        if en and cn:
            color_lookup.setdefault(en, cn)

    rows = assemble_buyplan_rows(df_size, df_meta, contract_by_po=by_po,
                                 contract_by_style=by_style, color_lookup=color_lookup)
    if not rows:
        return None

    brand = ""
    for c in ("division_name", "style_group", "company"):
        if c in df_meta.columns and not df_meta[c].dropna().empty:
            brand = str(df_meta[c].dropna().iloc[0]); break
    supplier = str(df_meta["factory"].dropna().iloc[0]) if "factory" in df_meta.columns and not df_meta["factory"].dropna().empty else ""
    desc = str(df_meta["style_description"].dropna().iloc[0]) if "style_description" in df_meta.columns and not df_meta["style_description"].dropna().empty else ""

    # 面料信息 from 款式面料表格 (style-fabric mapping) for the primary style.
    fabric = ""
    styles = [r.style for r in rows if r.style]
    if styles:
        parts_by_style = store.load_fabric_parts_for_styles(list(dict.fromkeys(styles)))
        primary = styles[0]
        fabric = _format_fabric(parts_by_style.get(primary, []))

    cprs = cprs_from_settings(get_app_settings_store())
    header = BuyPlanHeader(brand=brand, supplier=supplier, description=desc, fabric=fabric)
    return export_giii_buyplan(header, rows, cprs=cprs)


def _format_fabric(parts: list) -> str:
    """Render style-fabric-mapping parts into the 面料/FIBER header line, e.g.
    'HB-XD6786 94%rayon 6%span 200gsm 有效170cm'. Uses the first (main) part."""
    if not parts:
        return ""
    p = parts[0]
    bits = [getattr(p, "hhn_no", "") or "", getattr(p, "composition", "") or ""]
    if getattr(p, "weight_gsm", 0):
        bits.append(f"{p.weight_gsm}gsm")
    if getattr(p, "width_cm", 0):
        bits.append(f"有效{p.width_cm}cm")
    return " ".join(b for b in bits if b).strip()


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
    with c5:
        if st.button(
            "📋 " + t("Create Buy Plan (生产计划单)"),
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
            with st.spinner(t("Building production plan…")):
                try:
                    bp_bytes = generate_giii_production_plan(selected, store)
                    if bp_bytes:
                        st.session_state["rpt_bp_bytes"] = bp_bytes
                    else:
                        st.warning(t("No size data found for the selected POs."))
                except Exception as exc:
                    st.error(t("Production plan generation failed:") + f" {exc}")

    with c6:
        if st.button(
            "🧭 " + t("Buy Plan + Requirements (CPRS)"),
            disabled=not selected,
            use_container_width=True,
            key="rpt_gen_cprs_bp_btn",
            help=t(
                "The full A–W GIII buy plan with client requirements resolved "
                "live from the CPRS knowledge base — red-sticker code, carton "
                "mark, prepack ratio, PCs/box, MSRP and RFID. Configure CPRS in "
                "Admin → Settings; without it those columns are left blank."
            ),
        ):
            st.session_state.pop("rpt_cprs_bp_bytes", None)
            with st.spinner(t("Building buy plan (resolving CPRS requirements)…")):
                try:
                    out = _build_cprs_buyplan(selected, store, filt_df)
                    if out:
                        st.session_state["rpt_cprs_bp_bytes"] = out
                    else:
                        st.warning(t("No size data found for the selected POs."))
                except Exception as exc:
                    st.error(t("Buy plan generation failed:") + f" {exc}")

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

    if st.session_state.get("rpt_cprs_bp_bytes"):
        st.download_button(
            "⬇️ " + t("Download Buy Plan + Requirements (.xlsx)"),
            data=st.session_state["rpt_cprs_bp_bytes"],
            file_name="GIII_Buy_Plan_CPRS.xlsx",
            mime=_XLSX_MIME,
            key="rpt_cprs_bp_dl",
        )


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
