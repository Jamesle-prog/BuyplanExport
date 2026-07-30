"""Fabric Condition (面料情况) — the shop-floor width/weight/shrinkage log.

Import replaces the whole table: this is a single running log from one
sheet, not several client-years in one workbook, so there is no partition to
preserve across an upload (unlike Settlement).

Every column is shown as the sheet's own text, unrounded and unconverted —
see the parser for why: this log is full of ranges, approximations and notes
("176-178", "100层左右", "无", "同上") that a numeric column would silently
truncate.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.i18n import t
from ui.session_keys import SK
from ui.shared import _th, _tr, fragment_rerun, guard_multiselect_state, lazy_sections
from ui.stores import get_fabric_condition_store

_COLUMN_RENAME = {
    "row_no": "Row", "seq": "Seq", "test_date": "Date",
    "fabric_no": "Fabric No.", "style": "Style", "body_part": "Body Part",
    "color": "Color", "width_net": "Net Width (cm)",
    "width_gross": "Gross Width (cm)", "weight_gsm": "Weight (g)",
    "shrink_fabric_warp": "Shrink Warp (fabric)",
    "shrink_fabric_weft": "Shrink Weft (fabric)",
    "shrink_pattern_warp": "Shrink Warp (pattern)",
    "shrink_pattern_weft": "Shrink Weft (pattern)",
    "over_cut_pct": "Over-cut %", "max_plies": "Max Plies",
    "max_cut_length": "Max Cut Length", "cut_direction": "Cut Direction",
    "consumption_purchase_body": "Purchase /unit — Body",
    "consumption_purchase_binding": "Purchase /unit — Binding",
    "consumption_layout_body": "Layout /unit — Body",
    "consumption_layout_binding": "Layout /unit — Binding",
    "remaining_rolls": "Remaining (rolls)", "remaining_kg": "Remaining (kg)",
    "remaining_m": "Remaining (m)",
}
_DISPLAY_COLS = [c for c in _COLUMN_RENAME if c != "row_no"]


def show_fabric_condition_tab() -> None:
    st.subheader(f"📏 {t('Fabric Condition')}")
    st.caption(t(
        "The 面料情况 shop-floor log, read into the system: measured width "
        "and weight against nominal, shrinkage test results, cutting "
        "requirements, and remaining stock. Every value is shown exactly as "
        "written — this log runs on ranges, approximations and notes "
        "('176-178', '100层左右', '无', '同上'), and rounding any of them "
        "would silently lose the part that didn't fit a number."))

    flash = st.session_state.pop(SK.FC_FLASH, None)
    if flash:
        getattr(st, flash[0], st.info)(flash[1])

    lazy_sections([
        (f"📥 {t('Import')}", _render_import),
        (f"📋 {t('Browse')}", _render_browse),
    ], key=SK.FC_NAV)


def _render_import() -> None:
    store = get_fabric_condition_store()
    st.markdown(f"#### {t('Import the fabric condition workbook')}")
    st.caption(t(
        "Reads the **1.面料情况** sheet. Importing replaces the whole table "
        "— this is one running log, not several years in one file, so "
        "there is nothing to preserve selectively across an upload."))

    up = st.file_uploader(t("面料情况 workbook (.xlsx)"), type=["xlsx"],
                          key="fc_upload")
    if up is not None:
        sig = f"{up.name}:{up.size}"
        if st.session_state.get(SK.FC_PARSE_SIG) != sig:
            with st.spinner(t("Reading the workbook…")):
                st.session_state[SK.FC_PARSED] = _parse(up)
                st.session_state[SK.FC_PARSE_SIG] = sig

    parsed = st.session_state.get(SK.FC_PARSED)
    if parsed and parsed.get("error"):
        st.error(parsed["error"])
    elif parsed:
        n = len(parsed["records"])
        st.info(f"{t('Found')} **{n}** {t('record(s)')}, "
                f"**{parsed['n_cols']}** {t('column(s)')} " + t("recognised."))
        held = store.count()
        if held:
            st.warning(
                f"⚠️ {t('This replaces the')} **{held}** "
                f"{t('record(s) currently held.')}")
        if st.button(f"📥 {t('Import into the system')}", type="primary",
                     key="fc_do_import", use_container_width=True):
            res = store.import_parsed(
                parsed, source_file=parsed.get("source_file", ""),
                file_bytes=parsed.get("file_bytes"),
                imported_by=st.session_state.get(SK.USERNAME, ""))
            st.session_state[SK.FC_FLASH] = (
                "success",
                f"{t('Imported')} {res['n_records']} {t('record(s).')}")
            st.session_state[SK.FC_PARSED] = None
            st.session_state[SK.FC_PARSE_SIG] = None
            fragment_rerun()

    held = store.count()
    st.divider()
    st.caption(f"{t('Currently held')}: **{held}** {t('record(s).')}")
    imports = store.list_imports()
    if not imports.empty:
        with st.expander(f"🕘 {t('Import history')}"):
            st.dataframe(
                imports[["imported_at", "imported_by", "source_file",
                         "n_records"]].rename(columns=_tr({
                             "imported_at": "When", "imported_by": "By",
                             "source_file": "File", "n_records": "Records"})),
                use_container_width=True, hide_index=True)


def _parse(upload) -> dict:
    """Parse an upload, returning ``{"error": ...}`` instead of raising."""
    from io import BytesIO
    from po_extractor.parsers.fabric_condition import parse_fabric_condition
    data = upload.getbuffer().tobytes()
    try:
        parsed = parse_fabric_condition(BytesIO(data))
    except Exception as exc:                                # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
    parsed["source_file"] = upload.name
    parsed["file_bytes"] = data
    return parsed


def _render_browse() -> None:
    store = get_fabric_condition_store()
    if store.count() == 0:
        st.info(t("No fabric condition data — import the workbook first."))
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    style_opts = store.distinct("style")
    guard_multiselect_state("fc_browse_style", style_opts)
    styles = c1.multiselect(t("Style"), style_opts, key="fc_browse_style")
    color_opts = store.distinct("color")
    guard_multiselect_state("fc_browse_color", color_opts)
    colors = c2.multiselect(t("Color"), color_opts, key="fc_browse_color")
    search = c3.text_input(
        t("Search"), key="fc_browse_search",
        placeholder=t("Style, color or fabric no."))

    df = store.list_records(styles=styles, colors=colors, search=search)
    if df.empty:
        st.warning(t("No records match."))
        return

    show = df[_DISPLAY_COLS]
    st.dataframe(
        show.rename(columns=_tr(_COLUMN_RENAME)),
        use_container_width=True, hide_index=True)
    st.caption(f"{len(show)} {t('record(s)')} · "
              f"{df['style'].replace('', pd.NA).nunique()} {t('style(s)')}")
