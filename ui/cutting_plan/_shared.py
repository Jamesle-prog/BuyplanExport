"""Shared helpers for the Cutting Plan tab — PO selection and demand matrices."""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from po_extractor.config import PDF_MIME, XLSX_MIME
from ui.i18n import t
from ui.shared import guard_multiselect_state
from ui.stores import get_sky_east_store

_PAGE_SIZES = ["A4", "A3", "Letter"]
_ORIENTATIONS = {"landscape": "Landscape", "portrait": "Portrait"}

# Canonical Sky East size order — the DB stores one column per bucket.
SIZE_ORDER = ["XS", "S", "M", "L", "XL", "2XL"]
_SIZE_COLS = {"XS": "xs", "S": "s", "M": "m", "L": "l",
              "XL": "xl", "2XL": "xxl"}


def po_label(pc_no: str, po_no: str) -> str:
    """Display label for one linked PO — 'PC No. · PO No.'."""
    pc_no, po_no = (pc_no or "").strip(), (po_no or "").strip()
    if pc_no and po_no:
        return f"{pc_no} · {po_no}"
    return pc_no or po_no or "—"


def load_sky_east_items(pc_nos: list[str]) -> pd.DataFrame:
    """Sky East items for the given PC No.s (empty frame when none)."""
    if not pc_nos:
        return pd.DataFrame()
    df = get_sky_east_store().list_items(pc_nos)
    return df if df is not None else pd.DataFrame()


def select_pos(key_prefix: str, *,
               help_text: str | None = None) -> tuple[list[str], list[str], pd.DataFrame]:
    """Render the shared PC No. → PO No. selector.

    Returns ``(pc_nos, po_nos, items_df)``.  ``po_nos`` is empty when the user
    hasn't narrowed the selection, which means *every* PO under the chosen
    PC No.s.  ``items_df`` is already filtered to the effective selection.
    """
    store = get_sky_east_store()
    df_contracts = store.list_contracts()
    if df_contracts is None or df_contracts.empty:
        st.info(t("No Sky East contracts saved yet. Upload files in the "
                  "🛍 Sky East tab first."))
        return [], [], pd.DataFrame()

    pc_options = [pc for pc in df_contracts["pc_no"].tolist()
                  if pc and str(pc).strip()]
    pc_key = f"{key_prefix}_pcs"
    guard_multiselect_state(pc_key, pc_options)

    col_sel, col_all = st.columns([4, 1])
    with col_sel:
        pc_nos = st.multiselect(
            t("PC No.(s)"), pc_options, key=pc_key,
            placeholder=t("Select one or more PC Nos..."),
            help=help_text,
        )
    with col_all:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button(t("Select all"), key=f"{key_prefix}_all",
                  on_click=lambda: st.session_state.update(
                      {pc_key: list(pc_options)}),
                  use_container_width=True)

    if not pc_nos:
        return [], [], pd.DataFrame()

    items = load_sky_east_items(pc_nos)
    if items.empty:
        st.warning(t("No items found for the selected PC No.(s)."))
        return pc_nos, [], items

    po_options = sorted({str(p).strip() for p in
                         items.get("zalando_po", pd.Series(dtype=str)).tolist()
                         if p and str(p).strip()})
    po_nos: list[str] = []
    if po_options:
        po_key = f"{key_prefix}_pos"
        guard_multiselect_state(po_key, po_options)
        po_nos = st.multiselect(
            t("PO No.(s) — leave empty for all POs in the selected PC No.(s)"),
            po_options, key=po_key,
            placeholder=t("All POs"),
        )
        if po_nos:
            items = items[items["zalando_po"].astype(str).str.strip()
                          .isin(po_nos)].copy()
    return pc_nos, po_nos, items


def link_rows(pc_nos: list[str], po_nos: list[str],
              items: pd.DataFrame) -> list[dict]:
    """Expand a selection into concrete ``{pc_no, po_no}`` link rows.

    Always concrete pairs — never "the whole PC No." as a wildcard — so a
    later query for one PO number finds its plan without having to re-expand
    the contract.
    """
    rows: list[dict] = []
    if items is not None and not items.empty and "pc_no" in items.columns:
        seen = set()
        for _, r in items.iterrows():
            pc = str(r.get("pc_no") or "").strip()
            po = str(r.get("zalando_po") or "").strip()
            if not pc and not po:
                continue
            if (pc, po) in seen:
                continue
            seen.add((pc, po))
            rows.append({"pc_no": pc, "po_no": po})
    if rows:
        return rows
    # No item rows (e.g. a contract saved without items) — fall back to the
    # raw selection so the link isn't silently dropped.
    if po_nos:
        return [{"pc_no": pc_nos[0] if len(pc_nos) == 1 else "", "po_no": po}
                for po in po_nos]
    return [{"pc_no": pc, "po_no": ""} for pc in pc_nos]


def demand_matrix(items: pd.DataFrame) -> tuple[
        list[tuple[str, list[str]]], list[str], dict[tuple[str, str, str], int]]:
    """Build the Order-demands matrix from Sky East items.

    Returns ``(groups, colors, qty)`` where *groups* is
    ``[(style, [size, ...]), ...]`` limited to sizes that carry quantity,
    *colors* is the ordered colour list, and *qty* maps
    ``(style, colour, size) → quantity``.
    """
    if items is None or items.empty:
        return [], [], {}

    qty: dict[tuple[str, str, str], int] = {}
    styles: list[str] = []
    colors: list[str] = []
    sizes_used: dict[str, list[str]] = {}

    for _, row in items.iterrows():
        style = str(row.get("style") or "").strip() or "—"
        color = str(row.get("color_name") or "").strip() or "—"
        if style not in styles:
            styles.append(style)
            sizes_used[style] = []
        if color not in colors:
            colors.append(color)
        for size in SIZE_ORDER:
            n = int(row.get(_SIZE_COLS[size]) or 0)
            if n <= 0:
                continue
            key = (style, color, size)
            qty[key] = qty.get(key, 0) + n
            if size not in sizes_used[style]:
                sizes_used[style].append(size)

    groups = [
        (style, [s for s in SIZE_ORDER if s in sizes_used.get(style, [])])
        for style in styles
        if sizes_used.get(style)
    ]
    return groups, colors, qty


def demand_frame(groups: list[tuple[str, list[str]]], colors: list[str],
                 qty: dict[tuple[str, str, str], int]) -> pd.DataFrame:
    """The demand matrix as a display DataFrame (one row per style+colour)."""
    rows = []
    for style, sizes in groups:
        for color in colors:
            cells = {s: qty.get((style, color, s), 0) for s in sizes}
            if not any(cells.values()):
                continue
            rows.append({"Style": style, "Color": color, **cells,
                         "Total": sum(cells.values())})
    return pd.DataFrame(rows)


def pdf_export_block(xlsx_bytes: bytes | None, base_name: str, key: str, *,
                     label: str | None = None) -> None:
    """PDF options + build/download for a cutting-plan workbook.

    The PDF always fits every column onto one page width with minimal
    margins; page size and orientation are offered because a plan with many
    styles needs A3 to stay comfortably readable.
    """
    if not xlsx_bytes:
        return
    from po_extractor.exporters.xlsx_to_pdf import PdfRenderError, xlsx_bytes_to_pdf

    with st.expander(f"📕 {label or t('PDF version')}", expanded=False):
        st.caption(t(
            "All columns are fitted onto one page width with minimal page "
            "margins; long sheets continue on further pages."))
        c1, c2 = st.columns(2)
        page_size = c1.selectbox(t("Page size"), _PAGE_SIZES,
                                 key=f"{key}_pdf_page")
        orientation = c2.selectbox(
            t("Orientation"), list(_ORIENTATIONS),
            format_func=lambda o: t(_ORIENTATIONS[o]),
            key=f"{key}_pdf_orient")

        if st.button(f"📕 {t('Build PDF')}", key=f"{key}_pdf_build",
                     use_container_width=True):
            try:
                st.session_state[f"{key}_pdf_bytes"] = xlsx_bytes_to_pdf(
                    xlsx_bytes, page_size=page_size, orientation=orientation)
                st.session_state[f"{key}_pdf_name"] = f"{base_name}.pdf"
            except PdfRenderError as exc:
                st.error(str(exc))
            except Exception as exc:                    # noqa: BLE001
                st.error(f"{type(exc).__name__}: {exc}")

        data = st.session_state.get(f"{key}_pdf_bytes")
        if data:
            st.download_button(
                f"⬇️ {st.session_state.get(f'{key}_pdf_name', 'cut_plan.pdf')}",
                data=data,
                file_name=st.session_state.get(f"{key}_pdf_name",
                                               "cut_plan.pdf"),
                mime=PDF_MIME, use_container_width=True,
                key=f"{key}_pdf_dl")


def safe_filename(name: str, *, fallback: str = "cut_plan") -> str:
    """Strip characters Windows/Excel reject from a download filename."""
    cleaned = "".join(ch for ch in (name or "")
                      if ch not in '\\/:*?"<>|').strip()
    return cleaned or fallback


def plan_caption(plan: dict[str, Any]) -> str:
    """One-line summary of a plan record for list rows and pickers."""
    bits = [str(plan.get("plan_name") or "—")]
    if plan.get("plan_date"):
        bits.append(str(plan["plan_date"]))
    if plan.get("colors"):
        bits.append(str(plan["colors"]))
    qty = int(plan.get("order_qty") or 0)
    if qty:
        bits.append(f"{qty:,} pcs")
    return " · ".join(bits)
