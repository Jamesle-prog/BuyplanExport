"""Shared helpers for the Cutting Plan tab — PO selection and demand matrices."""
from __future__ import annotations

from typing import Any, NamedTuple

import pandas as pd
import streamlit as st

from po_extractor.config import PDF_MIME, XLSX_MIME
from ui.i18n import t
from ui.shared import _th, guard_multiselect_state
from ui.stores import get_sky_east_store

_PAGE_SIZES = ["A4", "A3", "Letter"]
_ORIENTATIONS = {"landscape": "Landscape", "portrait": "Portrait"}

# Canonical Sky East size order — the DB stores one column per bucket.
SIZE_ORDER = ["XS", "S", "M", "L", "XL", "2XL"]
_SIZE_COLS = {"XS": "xs", "S": "s", "M": "m", "L": "l",
              "XL": "xl", "2XL": "xxl"}


def cleanup_color_map(client: str = "") -> dict[str, str]:
    """Colour map for the cut-plan cleanup: ``{english: chinese}`` taken from
    the PO colour translations, so a colour the plan carries in English is
    handed to the cutting room in Chinese.

    Best-effort — if the colour table can't be read the export still builds,
    just with the English colour names it already had.
    """
    from po_extractor.exporters.cutting_plan_clean import build_color_map
    from ui.stores import get_color_translation_store
    try:
        return build_color_map(
            get_color_translation_store().build_lookup_dict(), client)
    except Exception:
        return {}


def fabric_picker(materials: list[dict], key: str) -> list[dict]:
    """Let the user narrow a multi-fabric plan to the fabric(s) they want.

    Shell and lining are separate fabrics at different widths and go to
    different cutting tables, so one fabric's blocks are often all that's
    wanted. A single-fabric plan shows no picker — there is nothing to choose.
    Clearing the selection means "all", rather than producing an empty sheet.
    """
    names = [str(m.get("material") or "—") for m in (materials or [])]
    uniq = list(dict.fromkeys(names))
    if len(uniq) < 2:
        return materials or []

    guard_multiselect_state(key, uniq)          # drop names no longer present
    st.session_state.setdefault(key, uniq)
    picked = st.multiselect(
        t("Fabric(s) to include"), uniq, key=key,
        help=t("Leave all selected to export the whole plan. Each fabric "
               "keeps its own marker, spreading and solution blocks."))
    chosen = set(picked) or set(uniq)
    if chosen != set(uniq):
        st.caption(f"{t('Exporting')} {len(chosen)}/{len(uniq)} {t('fabric(s)')}")
    return [m for m, n in zip(materials, names) if n in chosen]


def output_folder_input(key: str) -> str:
    """Optional folder to drop a copy of the generated file into.

    The download button always works; this is for the shared drive the cutting
    room reads, so the file doesn't have to be downloaded and moved by hand.
    """
    return (st.text_input(
        t("Also save a copy to this folder (optional)"), key=key,
        placeholder=r"D:\CutPlans\2026",
        help=t("Leave blank to just download. The folder must already exist "
               "and be writable from this machine.")) or "").strip()


def save_copy_to_folder(data: bytes, filename: str, folder: str) -> None:
    """Write *data* to ``folder/filename`` and report the outcome inline.

    Best-effort and loud: a bad path tells the user which path failed and why,
    and never takes the download with it. The filename is reduced to its base
    name so a name carrying separators can't write outside *folder*.
    """
    if not folder:
        return
    import os
    safe = os.path.basename(str(filename)) or "output"
    try:
        if not os.path.isdir(folder):
            st.warning(f"{t('Folder not found — nothing saved:')} {folder}")
            return
        path = os.path.join(folder, safe)
        with open(path, "wb") as fh:
            fh.write(data)
        st.success(f"{t('Saved a copy to')} {path}")
    except OSError as exc:
        st.warning(f"{t('Could not save to')} {folder} — {exc}")


def _cleaned_copy(xlsx_bytes: bytes, client: str = "") -> bytes:
    """A cutting-room-cleaned copy of a workbook, for rendering only.

    Works on the bytes in memory — the stored original is never touched. If
    anything goes wrong the untouched bytes come back, so a cleanup problem
    can only cost the translation, never the PDF.
    """
    from io import BytesIO
    try:
        import openpyxl
        from po_extractor.exporters.cutting_plan_clean import clean_workbook
        # data_only=True is essential, not a detail. Marker sheets carry ~70
        # =SUM() cells; openpyxl drops the cached results when it saves, so a
        # copy loaded WITH formulas comes back out with no values behind them
        # and the PDF renderer (which reads values) printed every total blank.
        # Loading values bakes each formula down to its number first.
        wb = openpyxl.load_workbook(BytesIO(xlsx_bytes), data_only=True)
        clean_workbook(wb, cleanup_color_map(client))
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()
    except Exception:
        return xlsx_bytes


def detect_color_conflicts(data: bytes, client: str = "") -> list[dict]:
    """Colours the plan already names in Chinese that disagree with the PO.

    Read-only. Best-effort — a colour-table hiccup just means no conflicts are
    reported, never a failed export.
    """
    from po_extractor.exporters.cutting_plan_clean import (
        build_color_map, build_reverse_color_map, conflicts_from_bytes,
    )
    from ui.stores import get_color_translation_store
    try:
        lookup = get_color_translation_store().build_lookup_dict()
        return conflicts_from_bytes(data, build_color_map(lookup, client),
                                    build_reverse_color_map(lookup))
    except Exception:
        return []


def render_color_conflicts(conflicts: list[dict], bytes_key: str,
                           key_prefix: str) -> None:
    """Warn about plan-vs-PO colour disagreements and offer to apply the PO's.

    Nothing is changed unless the user presses the button — the plan's own
    colour names are left exactly as they arrived until then.
    """
    if not conflicts:
        return
    st.warning(
        f"⚠️ {t('This cut plan names')} {len(conflicts)} "
        f"{t('colour(s) differently from the PO. Nothing has been changed.')}")
    st.dataframe(
        pd.DataFrame([{
            _th("Colour (English)"): c["english"].title(),
            _th("On the cut plan"): c["plan_cn"],
            _th("On the PO"): c["po_cn"],
            _th("First seen"): f"{c['sheet']}!{c['cell']}",
        } for c in conflicts]),
        use_container_width=True, hide_index=True)
    if st.button(f"✅ {t('Use the PO colour names instead')}",
                 key=f"{key_prefix}_apply_cn",
                 help=t("Rewrites only these colour cells in the downloadable "
                        "file. The stored cut plan is not modified.")):
        from po_extractor.exporters.cutting_plan_clean import (
            apply_color_overrides, _norm_color,
        )
        overrides = {_norm_color(c["plan_cn"]): c["po_cn"] for c in conflicts}
        st.session_state[bytes_key] = apply_color_overrides(
            st.session_state[bytes_key], overrides)
        st.success(f"{t('Applied the PO colour names to')} "
                   f"{len(overrides)} {t('colour(s).')}")
        st.rerun()


def po_label(pc_no: str, po_no: str, style: str = "") -> str:
    """Display label for one link — 'PC No. · PO No. · Style'."""
    parts = [p for p in ((pc_no or "").strip(), (po_no or "").strip(),
                         (style or "").strip()) if p]
    return " · ".join(parts) or "—"


def load_sky_east_items(pc_nos: list[str]) -> pd.DataFrame:
    """Sky East items for the given PC No.s (empty frame when none)."""
    if not pc_nos:
        return pd.DataFrame()
    df = get_sky_east_store().list_items(pc_nos)
    return df if df is not None else pd.DataFrame()


class POSelection(NamedTuple):
    """What the PC No. → PO No. → style selector resolved to.

    ``po_nos`` / ``styles`` are empty when the user hasn't narrowed that
    level, meaning *all* of them under the level above.  ``items`` is already
    filtered to the effective selection, so callers can use it directly.
    """
    pc_nos: list[str]
    po_nos: list[str]
    styles: list[str]
    items: pd.DataFrame

    def __bool__(self) -> bool:
        return bool(self.pc_nos)


def select_pos(key_prefix: str, *,
               help_text: str | None = None) -> POSelection:
    """Render the shared PC No. → PO No. → style selector.

    A cut plan usually covers particular styles rather than a whole contract,
    and nothing in the files connects the plan's CAD style names to the PO's
    style codes — so the style has to be chosen here.
    """
    store = get_sky_east_store()
    df_contracts = store.list_contracts()
    if df_contracts is None or df_contracts.empty:
        st.info(t("No Sky East contracts saved yet. Upload files in the "
                  "🛍 Sky East tab first."))
        return POSelection([], [], [], pd.DataFrame())

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
        return POSelection([], [], [], pd.DataFrame())

    items = load_sky_east_items(pc_nos)
    if items.empty:
        st.warning(t("No items found for the selected PC No.(s)."))
        return POSelection(pc_nos, [], [], items)

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

    style_options = sorted({str(s).strip() for s in
                            items.get("style", pd.Series(dtype=str)).tolist()
                            if s and str(s).strip()})
    styles: list[str] = []
    if style_options:
        style_key = f"{key_prefix}_styles"
        guard_multiselect_state(style_key, style_options)
        styles = st.multiselect(
            t("Style(s) inside those PO(s) — leave empty for all styles"),
            style_options, key=style_key,
            placeholder=t("All styles"),
            help=t("The plan's own style names come from the CAD files and "
                   "won't match the PO's style codes — pick the PO styles "
                   "this plan cuts."),
        )
        if styles:
            items = items[items["style"].astype(str).str.strip()
                          .isin(styles)].copy()
        _show_style_summary(items, style_options, styles)
    return POSelection(pc_nos, po_nos, styles, items)


def _show_style_summary(items: pd.DataFrame, all_styles: list[str],
                        picked: list[str]) -> None:
    """One line telling the user how much of the PO the selection covers."""
    if items is None or items.empty:
        return
    qty = int(pd.to_numeric(items.get("total_qty"), errors="coerce")
              .fillna(0).sum())
    n = len(picked) if picked else len(all_styles)
    st.caption(
        t("{n} of {total} style(s) selected · {qty:,} pcs").format(
            n=n, total=len(all_styles), qty=qty))


def link_rows(selection: POSelection) -> list[dict]:
    """Expand a selection into concrete ``{pc_no, po_no, style}`` link rows.

    Always concrete triples — never "the whole PC No." as a wildcard — so a
    later query for one PO number or style finds its plan without having to
    re-expand the contract.  Leaving the style picker empty therefore links
    every style currently in the selection, which is what "all styles" means
    at the moment of linking.
    """
    pc_nos, po_nos, styles, items = selection
    rows: list[dict] = []
    if items is not None and not items.empty and "pc_no" in items.columns:
        seen = set()
        for _, r in items.iterrows():
            pc = str(r.get("pc_no") or "").strip()
            po = str(r.get("zalando_po") or "").strip()
            style = str(r.get("style") or "").strip()
            if not pc and not po:
                continue
            if (pc, po, style) in seen:
                continue
            seen.add((pc, po, style))
            rows.append({"pc_no": pc, "po_no": po, "style": style})
    if rows:
        return rows
    # No item rows (e.g. a contract saved without items) — fall back to the
    # raw selection so the link isn't silently dropped.
    base_pc = pc_nos[0] if len(pc_nos) == 1 else ""
    if po_nos:
        return [{"pc_no": base_pc, "po_no": po, "style": st_}
                for po in po_nos for st_ in (styles or [""])]
    return [{"pc_no": pc, "po_no": "", "style": st_}
            for pc in pc_nos for st_ in (styles or [""])]


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
                     label: str | None = None,
                     allow_clean: bool = False,
                     client: str = "") -> None:
    """PDF options + build/download for a cutting-plan workbook.

    The PDF always fits every column onto one page width with minimal
    margins; page size and orientation are offered because a plan with many
    styles needs A3 to stay comfortably readable.

    *allow_clean* offers the cutting-room cleanup as a PDF option: ticked, the
    workbook is cleaned (Chinese headings, marker names, PO colour names) into
    a throwaway copy before rendering; unticked, the full workbook is rendered
    exactly as it is. Either way the stored file is never modified.
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

        clean = False
        if allow_clean:
            clean = st.checkbox(
                t("Clean for the cutting room (Chinese labels, marker names only)"),
                value=True, key=f"{key}_pdf_clean",
                help=t("Ticked: headings become Chinese, marker paths are "
                       "reduced to the marker name and colours use the PO's "
                       "names. Unticked: the workbook is rendered exactly as "
                       "it is. The stored file is never changed either way."))

        folder = output_folder_input(f"{key}_pdf_dir")

        if st.button(f"📕 {t('Build PDF')}", key=f"{key}_pdf_build",
                     use_container_width=True):
            try:
                src = _cleaned_copy(xlsx_bytes, client) if clean else xlsx_bytes
                data = xlsx_bytes_to_pdf(src, page_size=page_size,
                                         orientation=orientation)
                name = f"{base_name}{'_clean' if clean else ''}.pdf"
                st.session_state[f"{key}_pdf_bytes"] = data
                st.session_state[f"{key}_pdf_name"] = name
                save_copy_to_folder(data, name, folder)
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
