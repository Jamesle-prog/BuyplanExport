"""Sky East history section — contract browser, downloads, buy plan generation."""
from __future__ import annotations
import base64
import io
import os
import tempfile
import time
import warnings as _warnings
import zipfile
from datetime import datetime
from typing import NamedTuple
import pandas as pd
import streamlit as st
from ui.i18n import t
from auth.companies import SOURCE_SKY_EAST, COMPANY_SKY_EAST
from po_extractor.exporters import (
    export_sky_east_buyplan, export_sky_east_nukuryou,
    check_nukuryou_ready, build_cross_comparison,
)
from ui.session_keys import SK, COLOR_SOURCE_PROGRESS
from ui.shared import (
    XLSX_MIME, ZIP_MIME, CSV_MIME,
    EXCEL_FILE_TYPES as _EXCEL_FILE_TYPES,
    DEFAULT_XLSX_EXT as _DEFAULT_XLSX_EXT,
    _th, _tr,
    build_image_cache_for_ids,
    fragment_rerun,
    load_style_photo_pair,
    load_style_photo_map,
    persisted_download,
    guard_multiselect_state,
)
from ui.stores import get_store, get_sky_east_store, get_color_translation_store, get_fabric_master_store, IMAGES_DIR_DEFAULT
from ui.sky_east._shared import (
    live_label, _get_dual_header, _write_dual_header_excel, _write_wash_label_excel,
    show_color_source_radio,
)
from ui.sky_east.items_view import _enrich_items_df, _build_items_display_df


# ---------------------------------------------------------------------------
# History section helpers
# ---------------------------------------------------------------------------


class BuyplanColorLookups(NamedTuple):
    """Bundle of all color lookups passed into the buyplan / 核料 exporters.

    Fields
    ------
    cn : dict
        ``{(client, brand, en_color): cn_color}`` — canonical Chinese name map.
    label : dict | None
        ``{(client, brand, en_color): label_color}`` — 主标颜色 map.
        ``None`` tells the exporter to auto-fetch from the Internal DB.
    cn_code : dict | None
        ``{(client, brand, en_color): color_code}`` — 中文颜色代码 (e.g. "52#").
        ``None`` tells the exporter to auto-fetch from the Internal DB.
    by_pc : dict | None
        ``{(pc_no_norm, style_norm, en_color_norm): PCColorMatch}`` — populated
        only when the user selects 大货进度表 as the color source AND a file is
        loaded.  ``None`` skips the PC-keyed tier inside the exporter.
    brand_by_pc : dict | None
        ``{(pc_no_norm, style_norm): brand, style_norm: brand}`` — populated
        whenever a 大货进度表 is loaded (independent of the colour source), so
        the buy plan's 品牌 comes from the progress table.  ``None`` → the
        exporter uses the order file's own brand.
    """
    cn:      dict
    label:   dict | None
    cn_code: dict | None
    by_pc:   dict | None
    brand_by_pc: dict | None


def _build_buyplan_color_lookups() -> BuyplanColorLookups:
    """Build the bundle of color lookups honoring the user's source choice.

    Always starts from the canonical Color-Translation DB.  When the user has
    chosen ``COLOR_SOURCE_PROGRESS`` *and* a 大货进度表 is loaded in this session,
    the PC-No.-keyed lookup from the progress file is added on top.  Flat
    brand-keyed data from the progress file is intentionally NOT merged so
    that only an exact (PC No · 款式 · 颜色) match returns a progress value —
    no looser fallback keys bleed into the result.  The Internal DB is still
    used as fallback for colours that have no PC match.
    """
    from ui.sky_east._shared import get_progress_lookup

    color_source  = st.session_state.get(SK.SE_COLOR_SOURCE)
    progress_lkup = get_progress_lookup(SOURCE_SKY_EAST)
    cn_lookup     = get_color_translation_store().build_lookup_dict()

    # 品牌 comes from 大货进度表 (its BRAND column) whenever the progress file is
    # loaded — independent of the colour-source choice.
    brand_by_pc = (progress_lkup.build_brand_lookup()
                   if progress_lkup is not None else None)

    if color_source == COLOR_SOURCE_PROGRESS and progress_lkup is None:
        # User picked 大货进度表 but neither an ad-hoc upload this session nor
        # any saved data exists — make the silent fallback to the Internal DB
        # explicit so they don't think they got progress-sourced data.
        st.warning(
            "⚠ **大货进度表 not loaded** — falling back to the Internal DB "
            "for all Chinese colours. Upload it via **📐 Reference Data → "
            "HHN Contract Progress**.",
            icon="⚠️",
        )
        return BuyplanColorLookups(cn=cn_lookup, label=None, cn_code=None,
                                   by_pc=None, brand_by_pc=brand_by_pc)

    if color_source != COLOR_SOURCE_PROGRESS:
        return BuyplanColorLookups(cn=cn_lookup, label=None, cn_code=None,
                                   by_pc=None, brand_by_pc=brand_by_pc)

    by_pc = progress_lkup.build_pc_style_color_lookups()
    st.caption(t("🗂 Chinese colors sourced from 大货进度表 (PC No. · style · color match only)."))
    return BuyplanColorLookups(cn=cn_lookup, label=None, cn_code=None,
                               by_pc=by_pc, brand_by_pc=brand_by_pc)


def _se_hist_summary_table(df_contracts) -> None:
    """Render the contract-summary dataframe (sorted by PC No.)."""
    display_cols = [c for c in
                    ["pc_no", "pc_date", "buyer", "seller", "total_styles",
                     "total_qty", "currency", "trade_term", "extracted_at",
                     "source_file"]
                    if c in df_contracts.columns]
    df_view = df_contracts[display_cols]
    if "pc_no" in df_view.columns:
        df_view = df_view.sort_values("pc_no", kind="stable").reset_index(drop=True)
    st.dataframe(
        df_view.rename(columns=_tr({
            "pc_no": "PC No.", "pc_date": "PC Date", "buyer": "Buyer",
            "seller": "Seller", "total_styles": "Style·Colours",
            "total_qty": "Total Qty", "currency": "Currency",
            "trade_term": "Trade Term", "extracted_at": "Extracted At",
            "source_file": "Source File",
        })),
        width="stretch",
        hide_index=True,
    )


def _se_hist_multi_pc_download(store, pc_options: list[str],
                               sel_pcs: list | None = None) -> None:
    """Multi-PC items download section (Excel or CSV).

    ``sel_pcs`` — when provided, the Generate/Export screen has already
    rendered a shared PC selector; use it directly instead of rendering a
    section-local multiselect. ``None`` keeps the legacy standalone selector.
    """
    st.markdown(f"**{t('Download items by PC No.')}**")
    if sel_pcs is not None:
        sel_dl_pcs = sel_pcs
    else:
        dl_col1, dl_col2 = st.columns([3, 1])
        with dl_col1:
            sel_dl_pcs = st.multiselect(
                t("Select PC No.(s) to download:"),
                pc_options,
                placeholder="Choose one or more PC No.(s)...",
                key="se_dl_pcs",
            )
        with dl_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button(
                t("Select all"), key="se_dl_all",
                on_click=lambda: st.session_state.update({"se_dl_pcs": pc_options}),
            )

    if not sel_dl_pcs:
        st.info(t("Select one or more PC Nos. above, then click Generate."))

    if sel_dl_pcs:
        fmt_col, btn_col = st.columns([1, 2])
        with fmt_col:
            dl_fmt = st.radio(
                t("Format"), ["Excel (.xlsx)", "CSV (.csv)"],
                horizontal=True, key="se_dl_fmt",
            )
        with btn_col:
            st.markdown("<br>", unsafe_allow_html=True)
            generate = st.button(t("Generate"), type="primary", key="se_dl_gen")

        if generate:
            pcs_label = "_".join(sel_dl_pcs) if len(sel_dl_pcs) <= 4 else f"{len(sel_dl_pcs)}PCs"
            with st.spinner("Building file..."):
                df_all_items = store.list_items(pc_nos=sel_dl_pcs)
                df_enriched_all = _enrich_items_df(df_all_items)

                if dl_fmt == "Excel (.xlsx)":
                    from openpyxl import Workbook
                    xlsx_buf = io.BytesIO()
                    wb = Workbook()
                    wb.remove(wb.active)

                    class _FakeWriter:
                        def __init__(self, book): self.book = book

                    writer = _FakeWriter(wb)
                    all_pids = (
                        df_enriched_all["picture_id"].dropna().unique().tolist()
                        if "picture_id" in df_enriched_all.columns else []
                    )
                    dl_img_cache = build_image_cache_for_ids(all_pids)
                    _write_dual_header_excel(df_enriched_all, "All", writer, dl_img_cache)
                    if "pc_no" in df_enriched_all.columns:
                        for pc in sel_dl_pcs:
                            df_pc_enriched = df_enriched_all[df_enriched_all["pc_no"] == pc]
                            if not df_pc_enriched.empty:
                                _write_dual_header_excel(df_pc_enriched, pc[:31], writer, dl_img_cache)
                    wb.save(xlsx_buf)
                    st.session_state[SK.SE_DL_BYTES] = xlsx_buf.getvalue()
                    st.session_state[SK.SE_DL_FNAME] = f"SkyEast_{pcs_label}_items.xlsx"
                    st.session_state[SK.SE_DL_MIME]  = XLSX_MIME
                else:
                    present = set(df_enriched_all.columns)
                    cols_csv = [(db, r2) for db, _, r2 in _get_dual_header() if db in present]
                    if cols_csv:
                        db_cols = [c[0] for c in cols_csv]
                        final_names = [c[1] for c in cols_csv]
                        csv_df = df_enriched_all[db_cols].copy()
                        csv_df.columns = final_names
                    else:
                        csv_df = df_enriched_all
                    csv_buf = io.StringIO()
                    csv_df.to_csv(csv_buf, index=False, encoding="utf-8-sig")
                    st.session_state[SK.SE_DL_BYTES] = csv_buf.getvalue().encode("utf-8-sig")
                    st.session_state[SK.SE_DL_FNAME] = f"SkyEast_{pcs_label}_items.csv"
                    st.session_state[SK.SE_DL_MIME]  = CSV_MIME

    persisted_download("se_dl", default_fname="SkyEast_items")


def _wl_mapped_styles(source: str = SOURCE_SKY_EAST) -> list[str]:
    """Return sorted list of styles that have stored fabric mapping for *source*."""
    po = get_store()
    if hasattr(po, "list_mapped_styles"):
        return sorted(po.list_mapped_styles(source))
    with po._conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT style FROM style_fabric_parts WHERE source=?", (source,)
        ).fetchall()
    return sorted(r["style"] for r in rows)


def _warn_missing_color_translations(
    df_items: pd.DataFrame,
    cn_map: dict | None = None,
    label_map: dict | None = None,
) -> None:
    """Surface (brand, en_color) pairs in the buy plan that have no Chinese
    translation or label colour in the DB.

    ``cn_color`` empty → BODY COLOR-CN cell will be blank.
    ``label_color`` empty → 主标颜色 falls through to the light/dark heuristic,
    which often picks the wrong shade. Either is a data-quality issue worth
    surfacing so the user can fix it in the Color Translation tab.

    Pass *cn_map* / *label_map* when the caller has already built them — the
    function falls back to the canonical store only when omitted, so the buy
    plan path doesn't query the color_translation table twice.
    """
    if df_items is None or df_items.empty:
        return
    if "color_name" not in df_items.columns:
        return
    from po_extractor.store.color_translation_store import _normalize_color_name

    if cn_map is None:
        cn_map = get_color_translation_store().build_lookup_dict()
    if label_map is None:
        label_map = get_color_translation_store().build_label_lookup_dict()

    missing_cn:    set[tuple[str, str]] = set()
    missing_label: set[tuple[str, str]] = set()
    for _, row in df_items[["brand", "color_name"]].drop_duplicates().iterrows():
        brand = str(row.get("brand", "") or "").strip()
        en    = str(row.get("color_name", "") or "").strip()
        if not en:
            continue
        norm = _normalize_color_name(en)
        # Brand-specific only — matches the exporter's primary-only lookup.
        cn = cn_map.get((COMPANY_SKY_EAST, brand, norm))
        lb = label_map.get((COMPANY_SKY_EAST, brand, norm))
        if not (cn or "").strip():
            missing_cn.add((brand, en))
        if not (lb or "").strip():
            missing_label.add((brand, en))

    if not (missing_cn or missing_label):
        return
    lines = []
    if missing_cn:
        lines.append(f"**{len(missing_cn)}** colour(s) missing Chinese translation (BODY COLOR-CN will be blank):")
        for brand, en in sorted(missing_cn)[:10]:
            lines.append(f"  - `{brand}` / `{en}`")
        if len(missing_cn) > 10:
            lines.append(f"  - …and {len(missing_cn) - 10} more")
    if missing_label:
        lines.append(f"**{len(missing_label)}** colour(s) missing label colour (主标颜色 will use light/dark heuristic):")
        for brand, en in sorted(missing_label)[:10]:
            lines.append(f"  - `{brand}` / `{en}`")
        if len(missing_label) > 10:
            lines.append(f"  - …and {len(missing_label) - 10} more")
    lines.append("")
    lines.append("Fill these in the **🎨 Colors** tab to improve future buy plans.")
    st.warning("\n".join(lines))


def _enrich_parts_from_fabric_master(fabric_parts_by_style: dict) -> dict:
    """Fill / overwrite composition on each FabricPart from fabric_master (by HHN code).

    Uses the composition_en field from the fabric statistics database, which is
    the authoritative source for wash-label composition text.  Updates in-place.

    Returns
    -------
    dict
        The raw ``{hhn_no: record}`` cache from the DB.  Callers can use this to
        distinguish "not in DB" from "in DB but no composition".  Returns an empty
        dict when the lookup fails or there are no HHN codes.
    """
    all_hhns = [
        p.hhn_no
        for parts in fabric_parts_by_style.values()
        for p in parts
        if getattr(p, "hhn_no", "")
    ]
    if not all_hhns:
        return {}
    try:
        fm_cache = get_fabric_master_store().get_batch_enrichment(all_hhns)
    except Exception:
        return {}
    for parts in fabric_parts_by_style.values():
        for p in parts:
            hhn = getattr(p, "hhn_no", "") or ""
            if hhn and hhn in fm_cache:
                comp = str(fm_cache[hhn].get("composition_en") or "").strip()
                if comp:
                    p.composition = comp
    return fm_cache


def _se_hist_wash_label_download(store, pc_options: list[str],
                                 sel_pcs: list | None = None) -> None:
    """Wash-label download section — select by PC No., stored Fabric Mapping, or uploaded file.

    ``sel_pcs`` — shared PC selection from the Generate/Export screen; used
    only by the "PC No." select-mode (Style / Upload modes select their own
    inputs). ``None`` keeps the legacy section-local PC multiselect.
    """
    st.markdown(f"**{t('Download Wash Label Content')}**")
    st.caption(t("Style · Photo · Seq · Body Part · Fabric Code · Composition — up to 4 rows per style"))

    # ── Selection mode toggle ─────────────────────────────────────────────────
    sel_mode = st.radio(
        t("Select by"),
        ["PC No.", "Style (Fabric Mapping)", "Upload Mapping File"],
        horizontal=True,
        key="se_wl_sel_mode",
    )

    sel_wl_pcs: list[str] = []
    sel_wl_styles: list[str] = []
    upload_fabric_map: dict = {}   # {style: [FabricPart]} from ad-hoc upload

    if sel_mode == "PC No.":
        if sel_pcs is not None:
            sel_wl_pcs = sel_pcs
        else:
            wl_col1, wl_col2 = st.columns([3, 1])
            with wl_col1:
                # Guard against options changing under a live selection (a
                # fabric-mapping re-import) — stale values crash 1.57 / wipe 1.58.
                guard_multiselect_state("se_wl_pcs", pc_options)
                sel_wl_pcs = st.multiselect(
                    t("Select PC No.(s) for wash label:"),
                    pc_options,
                    placeholder="Choose one or more PC No.(s)...",
                    key="se_wl_pcs",
                )
            with wl_col2:
                st.markdown("<br>", unsafe_allow_html=True)
                st.button(
                    t("Select all"), key="se_wl_all",
                    on_click=lambda: st.session_state.update({"se_wl_pcs": pc_options}),
                )
        if not sel_wl_pcs:
            st.info(t("Select one or more PC Nos. above, then click Generate."))
        has_selection = bool(sel_wl_pcs)

    elif sel_mode == "Style (Fabric Mapping)":
        if sel_pcs is not None:
            st.caption(t("ℹ️ The PC selection above is not used in this mode — pick styles below."))
        # Styles come from the stored Fabric Mapping DB (Sky East source).
        # Composition is sourced from fabric_master at generation time.
        mapped_styles = _wl_mapped_styles(SOURCE_SKY_EAST)
        if not mapped_styles:
            st.warning(
                "No styles found in the Fabric Mapping database for Sky East. "
                "Go to the **📐 Reference Data** tab to import a mapping first, "
                "or switch to **PC No.** mode to download by contract."
            )
            has_selection = False
        else:
            wl_col1, wl_col2 = st.columns([3, 1])
            with wl_col1:
                guard_multiselect_state("se_wl_styles", mapped_styles)
                sel_wl_styles = st.multiselect(
                    t("Select Style(s) for wash label:"),
                    mapped_styles,
                    placeholder="Choose one or more styles...",
                    key="se_wl_styles",
                )
            with wl_col2:
                st.markdown("<br>", unsafe_allow_html=True)
                st.button(
                    t("Select all"), key="se_wl_styles_all",
                    on_click=lambda: st.session_state.update(
                        {"se_wl_styles": mapped_styles}
                    ),
                )
            st.caption(
                f"{len(mapped_styles)} style(s) available from stored fabric mapping. "
                "Composition will be sourced from the **Fabric DB** (面料统计表)."
            )
            has_selection = bool(sel_wl_styles)

    else:  # "Upload Mapping File"
        if sel_pcs is not None:
            st.caption(t("ℹ️ The PC selection above is not used in this mode — the uploaded file decides the styles."))
        st.caption(t(
            "Upload a fabric mapping file to generate wash labels for all styles in that file. "
            "This file is used only for this download and is **not** saved to the database."
        ))
        wl_upload_file = st.file_uploader(
            "Fabric mapping file (.xlsx / .xls)",
            type=_EXCEL_FILE_TYPES,
            key="se_wl_upload_map",
            label_visibility="collapsed",
        )
        if wl_upload_file:
            try:
                from ui.sky_east._shared import _parse_fabric_mapping_bytes
                upload_fabric_map = _parse_fabric_mapping_bytes(wl_upload_file.getvalue())
            except Exception as exc:
                st.error(f"Could not parse file: {exc}")
                upload_fabric_map = {}

            if upload_fabric_map:
                n_styles = len(upload_fabric_map)
                st.info(
                    f"**{wl_upload_file.name}** — {n_styles} style(s) found. "
                    "Composition will be sourced from the **Fabric DB** (面料统计表)."
                )
            else:
                st.warning("No valid styles found in the uploaded file.")
        has_selection = bool(upload_fabric_map)

    # ── Pending validation — show correction UI before generating ─────────────
    pending = st.session_state.get(SK.SE_WL_PENDING)
    if pending:
        _show_wl_validation_ui(pending)
        return  # Don't show generate button while correction is pending

    if has_selection:
        if st.button(t("Generate Wash Label"), type="primary", key="se_wl_gen"):
            with st.spinner("Building wash label file..."):
                if sel_mode == "PC No.":
                    df_wl_items = store.list_items(pc_nos=sel_wl_pcs)
                    label_parts = sel_wl_pcs
                    df_wl_enriched = _enrich_items_df(df_wl_items)
                    wl_styles = df_wl_enriched["style"].dropna().unique().tolist() \
                        if "style" in df_wl_enriched.columns else []
                    wl_fabric_parts = get_store().load_fabric_parts_for_styles(
                        wl_styles, source=SOURCE_SKY_EAST
                    ) if wl_styles else {}
                    if not wl_fabric_parts and wl_styles:
                        wl_fabric_parts = get_store().load_fabric_parts_for_styles(wl_styles)
                    if wl_fabric_parts:
                        fm_cache = _enrich_parts_from_fabric_master(wl_fabric_parts)
                    else:
                        fm_cache = {}
                    explicit_styles = None

                elif sel_mode == "Style (Fabric Mapping)":
                    df_wl_items = store.list_items_by_styles(sel_wl_styles)
                    label_parts = sel_wl_styles
                    df_wl_enriched = _enrich_items_df(df_wl_items)
                    wl_fabric_parts = get_store().load_fabric_parts_for_styles(
                        sel_wl_styles, source=SOURCE_SKY_EAST
                    )
                    if not wl_fabric_parts:
                        wl_fabric_parts = get_store().load_fabric_parts_for_styles(sel_wl_styles)
                    fm_cache = _enrich_parts_from_fabric_master(wl_fabric_parts)
                    explicit_styles = sel_wl_styles

                else:  # Upload Mapping File
                    file_styles = list(upload_fabric_map.keys())
                    df_wl_items = store.list_items_by_styles(file_styles)
                    label_parts = file_styles
                    df_wl_enriched = _enrich_items_df(df_wl_items)
                    wl_fabric_parts = upload_fabric_map
                    fm_cache = _enrich_parts_from_fabric_master(wl_fabric_parts)
                    explicit_styles = file_styles

                all_wl_pids = (
                    df_wl_enriched["picture_id"].dropna().unique().tolist()
                    if "picture_id" in df_wl_enriched.columns else []
                )
                wl_img_cache = build_image_cache_for_ids(all_wl_pids)
                safe_label = (
                    "_".join(label_parts) if len(label_parts) <= 4
                    else f"{len(label_parts)}items"
                )

                # ── Composition validation ────────────────────────────────────
                from po_extractor.ui_helpers.composition_validator import (
                    validate_fabric_parts as _validate_fabric_parts,
                )
                val_errors = _validate_fabric_parts(wl_fabric_parts, fm_cache=fm_cache)
                if val_errors:
                    st.session_state[SK.SE_WL_PENDING] = {
                        "df_enriched":    df_wl_enriched,
                        "fabric_parts":   wl_fabric_parts,
                        "img_cache":      wl_img_cache,
                        "explicit_styles": explicit_styles,
                        "label":          safe_label,
                        "errors":         val_errors,
                    }
                    fragment_rerun()
                else:
                    wl_bytes = _write_wash_label_excel(
                        df_wl_enriched, wl_img_cache,
                        fabric_parts_by_style=wl_fabric_parts,
                        styles=explicit_styles,
                    )
                    st.session_state[SK.SE_WL_BYTES] = wl_bytes
                    st.session_state[SK.SE_WL_FNAME] = f"WashLabel_{safe_label}.xlsx"

    persisted_download("se_wl", default_fname="WashLabel.xlsx", fixed_mime=XLSX_MIME)


def _show_wl_validation_ui(pending: dict) -> None:
    """Render the composition validation / correction UI."""
    import pandas as _pd
    from po_extractor.utils.composition_check import (
        validate_composition as _vc,
        get_all_fibers        as _get_fibers,
    )

    errors: list[dict] = pending["errors"]
    n = len(errors)

    # ── Summary header ────────────────────────────────────────────────────────
    hdr_col, dl_col = st.columns([3, 1])
    with hdr_col:
        st.warning(
            f"⚠️ **{n} composition issue{'s' if n != 1 else ''} found.** "
            "Review the table, edit the **Composition** column where needed, "
            "then click **Apply & Generate**."
        )
    with dl_col:
        # Build Excel bytes for the error table so user can fix offline
        _err_df = _pd.DataFrame(errors, columns=[
            "style", "combo_idx", "seq", "body_part", "hhn_no",
            "composition", "issue", "suggestion",
        ]).rename(columns={
            "style":       "Style",
            "combo_idx":   "Combo",
            "seq":         "Seq",
            "body_part":   "Body Part",
            "hhn_no":      "Fabric Code",
            "composition": "Composition",
            "issue":       "Issue",
            "suggestion":  "Suggestion",
        })
        import io as _io
        _buf = _io.BytesIO()
        with _pd.ExcelWriter(_buf, engine="openpyxl") as _xw:
            _err_df.to_excel(_xw, index=False, sheet_name="Composition Errors")
            # Auto-fit column widths
            _ws = _xw.sheets["Composition Errors"]
            for _col in _ws.columns:
                _max_w = max(len(str(_cell.value or "")) for _cell in _col)
                _ws.column_dimensions[_col[0].column_letter].width = min(_max_w + 4, 60)
        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            "📥 Download errors (.xlsx)",
            data=_buf.getvalue(),
            file_name="WashLabel_CompositionErrors.xlsx",
            mime=XLSX_MIME,
            key="se_wl_err_dl",
            use_container_width=True,
        )

    # ── Issue-type legend ─────────────────────────────────────────────────────
    with st.expander("ℹ️ Issue types explained", expanded=False):
        st.markdown(
            "| Type | Meaning |\n"
            "|------|---------|\n"
            "| **[Sum ≠ 100%]** | Fiber percentages don't add up to 100 |\n"
            "| **[Cannot parse]** | No valid `{pct}%{Fiber}` tokens found |\n"
            "| **[Unknown fiber]** | Fiber name not in the dictionary — check spelling |\n"
            "| **[Wrong capitalization]** | Fiber name must start with a capital letter |\n"
            "| **Missing composition** | No composition value at all |\n\n"
            "**Format:** `85%Polyester 15%Elastane` · "
            "**Tip:** fix compositions in the **🧵 Fabric DB** tab to skip this step next time."
        )

    # ── Editable error table ──────────────────────────────────────────────────
    # Build DataFrame with all columns including Suggestion
    df_err = _pd.DataFrame(
        errors,
        columns=["style", "combo_idx", "seq", "body_part", "hhn_no",
                 "composition", "issue", "suggestion"],
    ).rename(columns={
        "style":       "Style",
        "combo_idx":   "Combo",
        "seq":         "Seq",
        "body_part":   "Body Part",
        "hhn_no":      "Fabric Code",
        "composition": "Composition",
        "issue":       "Issue",
        "suggestion":  "Suggestion",
    })

    edited = st.data_editor(
        df_err,
        width="stretch",
        hide_index=True,
        column_config={
            "Style":       st.column_config.TextColumn("Style",       disabled=True, width="small"),
            "Combo":       st.column_config.NumberColumn("Combo",     disabled=True, width="small",
                               help="Fabric combination row index (0 = first row for this style)"),
            "Seq":         st.column_config.NumberColumn("Seq",       disabled=True, width="small"),
            "Body Part":   st.column_config.TextColumn("Body Part",   disabled=True, width="medium"),
            "Fabric Code": st.column_config.TextColumn("Fabric Code", disabled=True, width="medium"),
            "Composition": st.column_config.TextColumn(
                "Composition ✏️",
                disabled=False,
                width="large",
                help=(
                    "Edit directly. Format: '85%Polyester 15%Elastane' — must sum to 100%. "
                    "Fiber names must start with a capital letter and be in the fiber dictionary."
                ),
            ),
            "Issue":       st.column_config.TextColumn("Issue",       disabled=True, width="large"),
            "Suggestion":  st.column_config.TextColumn(
                "Suggestion",
                disabled=True,
                width="medium",
                help="Best-guess correction from the fiber dictionary (copy into Composition if correct).",
            ),
        },
        key="se_wl_validation_editor",
    )

    st.divider()
    c_apply, c_skip, c_cancel = st.columns([2, 2, 1])

    with c_apply:
        if st.button("✅ Apply corrections & Generate", type="primary",
                     key="se_wl_val_apply", use_container_width=True):
            # Re-validate every edited row with the full validator
            all_fibers = _get_fibers()
            still_bad: list[str] = []
            for _, row in edited.iterrows():
                comp_val = str(row.get("Composition") or "").strip()
                issues   = _vc(comp_val, all_fibers=all_fibers) if comp_val else []
                missing  = not comp_val
                if missing:
                    still_bad.append(
                        f"**{row['Style']}** · seq {int(row['Seq'])}: Missing composition"
                    )
                elif issues:
                    msgs = "; ".join(iss.detail for iss in issues)
                    still_bad.append(
                        f"**{row['Style']}** · seq {int(row['Seq'])}: {msgs}"
                    )

            if still_bad:
                st.error(
                    f"{len(still_bad)} issue(s) still remain — please fix before generating:\n\n"
                    + "\n\n".join(f"• {m}" for m in still_bad[:15])
                )
            else:
                # Apply edited compositions back onto the FabricPart objects
                fabric_parts: dict = pending["fabric_parts"]
                for _, row in edited.iterrows():
                    style    = row["Style"]
                    cidx     = int(row["Combo"])
                    seq      = int(row["Seq"])
                    new_comp = str(row["Composition"]).strip()
                    for p in fabric_parts.get(style, []):
                        if (getattr(p, "combo_idx", 0) == cidx
                                and getattr(p, "seq", 0) == seq):
                            p.composition = new_comp
                            break

                wl_bytes = _write_wash_label_excel(
                    pending["df_enriched"],
                    pending["img_cache"],
                    fabric_parts_by_style=fabric_parts,
                    styles=pending["explicit_styles"],
                )
                st.session_state[SK.SE_WL_BYTES]   = wl_bytes
                st.session_state[SK.SE_WL_FNAME]   = f"WashLabel_{pending['label']}.xlsx"
                st.session_state[SK.SE_WL_PENDING] = None
                fragment_rerun()

    with c_skip:
        if st.button("⚠️ Generate anyway (keep errors)", key="se_wl_val_skip",
                     use_container_width=True):
            fabric_parts: dict = pending["fabric_parts"]
            wl_bytes = _write_wash_label_excel(
                pending["df_enriched"],
                pending["img_cache"],
                fabric_parts_by_style=fabric_parts,
                styles=pending["explicit_styles"],
            )
            st.session_state[SK.SE_WL_BYTES]   = wl_bytes
            st.session_state[SK.SE_WL_FNAME]   = f"WashLabel_{pending['label']}.xlsx"
            st.session_state[SK.SE_WL_PENDING] = None
            fragment_rerun()

    with c_cancel:
        if st.button("❌ Cancel", key="se_wl_val_cancel", use_container_width=True):
            st.session_state[SK.SE_WL_PENDING] = None
            fragment_rerun()

    # Show the previously generated file (if any) below the correction panel
    persisted_download("se_wl", default_fname="WashLabel.xlsx", fixed_mime=XLSX_MIME)


def _se_hist_inject_photo_col(display_df, col_cfg, df_items) -> None:
    """Insert a Photo column (as base64 image) after Style if picture_ids exist."""
    _style_col = _th("Style")
    _photo_col = _th("Photo")
    if "picture_id" not in df_items.columns or _style_col not in display_df.columns:
        return
    style_to_pid: dict[str, str] = {}
    for _, r in df_items.iterrows():
        s   = str(r.get("style", "")).strip()
        pid = str(r.get("picture_id", "")).strip()
        if s and pid and s not in style_to_pid:
            style_to_pid[s] = pid
    all_pids = list(set(style_to_pid.values()))
    loaded   = build_image_cache_for_ids(all_pids)
    pid_to_b64 = {
        pid: f"data:image/png;base64,{base64.b64encode(b).decode()}"
        for pid, b in loaded.items()
    }
    if not pid_to_b64:
        return
    photo_vals = display_df[_style_col].map(
        lambda s: pid_to_b64.get(style_to_pid.get(str(s).strip(), ""), None)
    )
    sn_idx = display_df.columns.get_loc(_style_col)
    display_df.insert(sn_idx + 1, _photo_col, photo_vals)
    col_cfg[_photo_col] = st.column_config.ImageColumn(_th("Photo"), width="small")


def _se_hist_amendment_history(store, df_items, sel_pcs: list[str]) -> None:
    """Amendment-history expander for a single style."""
    with st.expander(t("View amendment history for a style")):
        styles_in_pc = df_items["style"].dropna().unique().tolist() if not df_items.empty else []
        sel_style = st.selectbox("Style:", [""] + styles_in_pc, key="se_hist_style")
        if not sel_style:
            return
        hist_frames = [store.list_item_history(pc, style=sel_style) for pc in sel_pcs]
        non_empty_frames = [f for f in hist_frames if not f.empty]
        df_hist = pd.concat(non_empty_frames, ignore_index=True) if non_empty_frames else pd.DataFrame()
        if df_hist.empty:
            st.info(f"No amendment history for {sel_style} in PC(s) {', '.join(sel_pcs)}.")
            return
        st.caption(f"{len(df_hist)} archived version(s)")
        size_cols_h = [c for c in ["xs", "s", "m", "l", "xl", "xxl"] if c in df_hist.columns]
        show_h = [c for c in
                  ["archived_at", "color_name", "zalando_po", "total_qty",
                   *size_cols_h, "revision_reason"]
                  if c in df_hist.columns]
        st.dataframe(
            df_hist[show_h].rename(columns={
                "archived_at": "Archived At",
                "color_name": "Color",
                "zalando_po": "Zalando PO",
                "total_qty": "Total Qty",
                "xs": "XS", "s": "S", "m": "M", "l": "L", "xl": "XL", "xxl": "2XL",
                "revision_reason": "Reason",
            }),
            width="stretch", hide_index=True,
        )


def _se_hist_item_browser(store, pc_options: list[str]) -> None:
    """Multi-PC items browser with optional photo column and amendment history."""
    # Guard: remove any stale pc_nos from session state that no longer exist
    # in pc_options (e.g. after a delete + rerun).  Without this Streamlit
    # raises StreamlitAPIException: "The selection contains invalid values."
    _pc_set = set(pc_options)
    _current = st.session_state.get("se_hist_pc", [])
    if isinstance(_current, list) and any(v not in _pc_set for v in _current):
        st.session_state["se_hist_pc"] = [v for v in _current if v in _pc_set]

    sel_pcs = st.multiselect(t("Browse items for PC No.:"), pc_options,
                             key="se_hist_pc",
                             placeholder="Select one or more PC Nos.")
    if not sel_pcs:
        return
    df_items = store.list_items(pc_nos=sel_pcs)
    if not df_items.empty:
        display_df, col_cfg = _build_items_display_df(df_items)
        _pc_col = _th("PC No.")
        if len(sel_pcs) == 1 and _pc_col in display_df.columns:
            display_df = display_df.drop(columns=[_pc_col])
        _se_hist_inject_photo_col(display_df, col_cfg, df_items)
        st.dataframe(display_df, width="stretch", hide_index=True,
                     column_config=col_cfg)
    _se_hist_amendment_history(store, df_items, sel_pcs)


def _se_hist_delete_section(store, pc_options: list[str]) -> None:
    """Delete-contracts controls."""
    st.markdown(f"**{t('Delete contracts from history')}**")
    to_del = st.multiselect(t("Select PC No.(s) to delete:"), pc_options,
                            placeholder="Select PC No.(s) to remove...",
                            key="se_del_pcs")
    if st.button(t("Delete selected"), disabled=not to_del, key="se_del_btn"):
        n = store.delete_contracts(to_del)
        from ui.sky_east._missing_compute import _compute_se_missing_df
        _compute_se_missing_df.clear()
        _se_buyplan_fabric_preflight.clear()
        # Clear multiselect session state BEFORE rerun so Streamlit doesn't
        # raise StreamlitAPIException when deleted pc_nos are no longer in
        # pc_options on the next render pass.
        for _key in ("se_del_pcs", "se_hist_pc"):
            st.session_state.pop(_key, None)
        st.toast(f"✅ Deleted {n} contract(s).", icon="🗑️")
        st.rerun()


@st.cache_data(ttl=30, show_spinner=False)
def _se_buyplan_fabric_preflight(pc_nos: tuple[str, ...]) -> tuple[int, list[str]]:
    """Distinct-style count + styles with no fabric code on file, for a PC
    selection. Cached (keyed by *pc_nos*) so touching an unrelated widget on
    the Generate/Export screen (colour-source radio, fabric-version selector,
    …) doesn't re-scan items + re-run the fabric-mapping lookup/groupby with
    the SAME selection every time -- only an actual selection change, an
    upload, or the short TTL trigger a redo. Read-only display data (an
    informational banner, not an editable form), so a brief staleness window
    is an acceptable trade for not re-querying on every unrelated interaction.
    """
    from ui.stores import get_sky_east_store, get_store as _get_po_store
    sel_items = get_sky_east_store().list_items(pc_nos=list(pc_nos))
    if "style" not in sel_items.columns:
        return 0, []

    sty_series = sel_items["style"].fillna("").astype(str).str.strip()
    distinct_styles = int(sty_series[sty_series != ""].nunique())

    styles_set = sorted({s for s in sty_series if s})
    try:
        fab_map = (_get_po_store().load_fabric_parts_for_styles(
            styles_set, source=SOURCE_SKY_EAST) if styles_set else {})
    except Exception:
        fab_map = {}
    mapped = {
        s for s, parts in (fab_map or {}).items()
        if parts and str(getattr(parts[0], "hhn_no", "") or "").strip()
    }
    tmp = sel_items.assign(
        _sty=sty_series,
        _fab=(sel_items.get("fabric_item_no", pd.Series("", index=sel_items.index))
              .fillna("").astype(str).str.strip().str.lower()),
    )
    tmp = tmp[tmp["_sty"] != ""]
    has_code = tmp.groupby("_sty")["_fab"].apply(
        lambda s: any(v not in ("", "none", "nan") for v in s)
    )
    uncovered = sorted(s for s, ok in has_code.items() if not ok and s not in mapped)
    return distinct_styles, uncovered


def _se_hist_buyplan_section(store, pc_options: list[str],
                              df_contracts=None,
                              sel_pcs: list | None = None) -> None:
    """Generate Sky East buy plan + 核料 workbooks for selected contracts.

    ``sel_pcs`` — when provided, the Generate/Export screen has already
    rendered a shared PC selector; use it directly instead of rendering a
    section-local multiselect. ``None`` keeps the legacy standalone selector.
    """
    st.markdown(f"**{t('Create Buy Plan')}**")
    st.caption(t(
        "Generates the main buy plan (Template) and fabric 核料 workbooks (Template_P) "
        "from the selected contracts, matching the VBA output format."
    ))
    if sel_pcs is not None:
        _effective_sel = sel_pcs
    else:
        # ── PC No. multiselect ────────────────────────────────────────────────
        # Stale-value guard: drop any selected PC Nos that are no longer valid
        # options (e.g. after a contract is deleted in the History tab) BEFORE
        # the widget renders — otherwise st.multiselect raises
        # StreamlitAPIException.
        _pc_set = set(pc_options)
        _cur = st.session_state.get("se_bp_sel", [])
        if isinstance(_cur, list) and any(v not in _pc_set for v in _cur):
            st.session_state["se_bp_sel"] = [v for v in _cur if v in _pc_set]

        _bp_col1, _bp_col2 = st.columns([4, 1])
        with _bp_col1:
            _effective_sel = st.multiselect(
                t("PC No.(s) to include:"),
                pc_options,
                key="se_bp_sel",
                placeholder="Select one or more PC Nos...",
            )
        with _bp_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button(
                t("Select all"), key="se_bp_all",
                on_click=lambda: st.session_state.update({"se_bp_sel": list(pc_options)}),
                use_container_width=True,
            )

    if not _effective_sel:
        st.info(t("Select one or more PC Nos. above, then click Generate."))

    # ── Selection summary + pre-flight checks ──────────────────────────────────
    if _effective_sel and df_contracts is not None and not df_contracts.empty:
        _sel_df = df_contracts[df_contracts["pc_no"].isin(_effective_sel)]
        _total_units = int(_sel_df["total_qty"].sum()) if "total_qty" in _sel_df.columns else 0
        # NOTE: the DB's "total_styles" is COUNT(DISTINCT style|colour) — i.e.
        # style·colour combos, NOT distinct style numbers. Show both, labelled
        # honestly, so "Styles: 8" can't be mistaken for the combo count.
        _combos = int(_sel_df["total_styles"].sum()) if "total_styles" in _sel_df.columns else 0

        # Cached by the PC selection: touching an unrelated widget on this
        # screen (colour-source radio, fabric-version selector, …) reruns this
        # whole function, but the item scan + fabric-mapping lookup + groupby
        # below only need to redo when the SELECTION itself changes.
        _distinct_styles, _uncovered = _se_buyplan_fabric_preflight(
            tuple(sorted(_effective_sel))
        )

        _m1, _m2, _m3, _m4 = st.columns(4)
        _m1.metric(t("PCs selected"), len(_effective_sel))
        _m2.metric(t("Styles"), _distinct_styles,
                   help=t("Distinct style numbers (a style offered in several colours counts once)."))
        _m3.metric(t("Style·Colours"), _combos,
                   help=t("Distinct style·colour combinations — a style in 3 colours counts as 3."))
        _m4.metric(t("Total Units"), f"{_total_units:,}")

        # Pre-flight: 核料 is grouped by fabric code, so a style with no fabric
        # code (and no saved fabric mapping to back-fill it) is silently skipped
        # in 核料. Flag those up-front, accounting for the fabric mapping so we
        # don't false-alarm on styles that will be back-filled at generation.
        if _uncovered:
            _prev = ", ".join(_uncovered[:6]) + (
                f" … +{len(_uncovered) - 6} more" if len(_uncovered) > 6 else "")
            st.info(
                f"ℹ️ {len(_uncovered)} "
                + t("style(s) have **no fabric code** on file")
                + f" ({_prev}) — "
                + t("核料 will skip them. Add the 面料编号 (HHN No.) via the "
                    "**Missing Fields** tab or **📐 Reference Data** first."),
                icon="🧩",
            )

    # ── Color mapping source ──────────────────────────────────────────────────
    show_color_source_radio("se_bp_color_src_radio")

    # ── 大货进度表 status (uploaded via Reference Data → HHN Contract Progress) ─
    # The 大货进度表 is managed centrally in Reference Data, not uploaded here —
    # this panel only reports which saved data the run will use.
    if st.session_state.get(SK.SE_COLOR_SOURCE) == COLOR_SOURCE_PROGRESS:
        _session_lkup = st.session_state.get(SK.SE_PROGRESS_LKUP)
        if _session_lkup is not None:
            st.caption(
                f"✅ {t('大货进度表 loaded for this run')} ({len(_session_lkup)} {t('records')})."
            )
        else:
            from ui.sky_east._shared import get_progress_lookup
            _db_lkup = get_progress_lookup(SOURCE_SKY_EAST)
            if _db_lkup is not None:
                st.caption(
                    f"✅ {t('Using saved 大货进度表 data')} ({len(_db_lkup)} {t('records')}) — "
                    + t("uploaded via **📐 Reference Data → HHN Contract Progress**.")
                )
            else:
                st.caption(t(
                    "ℹ️ No saved 大货进度表 data for Sky East yet — upload it via "
                    "**📐 Reference Data → HHN Contract Progress**."
                ))

    # ── Fabric list version ─────────────────────────────────────────────────
    # Fabric-master enrichment (composition/GSM/width) can be pinned to an
    # older upload instead of the current live table — always defaults to
    # "Latest". See Fabric DB tab → 📜 Version History for what changed
    # between versions.
    from ui.fabric_db.version_history import _fabric_version_options
    _fm_options = _fabric_version_options(get_fabric_master_store())
    _fm_choice = st.selectbox(
        t("Fabric list version"), _fm_options,
        format_func=lambda o: o[0],
        key="se_bp_fabric_version",
        help=t("Which uploaded fabric list to enrich the buy plan against. "
               "Defaults to the latest upload."),
    )
    _fabric_version_id = _fm_choice[1] if _fm_choice else None

    # ── Optional output folder ──────────────────────────────────────────────
    # When set, the generated buy plan + 核料 workbooks are ALSO copied
    # there (in addition to the download buttons). Last-used folders persist
    # across sessions via the same history file the image folder uses.
    from ui.shared import _load_history as _dir_history, _push_history as _push_dir
    if SK.SE_OUTPUT_DIR not in st.session_state:
        _hist = _dir_history("se_output_dir")
        st.session_state[SK.SE_OUTPUT_DIR] = _hist[0] if _hist else ""
    st.text_input(
        t("Output folder (optional)"),
        key=SK.SE_OUTPUT_DIR,
        placeholder=r"e.g. D:\BuyPlans or a network folder — blank = downloads only",
        help=t("When set, the generated files are also saved directly to this "
               "folder (downloads below still work either way)."),
    )

    # Button is always enabled when contracts exist.  Validating selection inside
    # the handler (rather than via disabled=) avoids the Streamlit 1.57.0 bug
    # where a multiselect's session-state desync keeps the button permanently
    # greyed out even though chips are visually shown.
    if st.button(t("Generate Buy Plan + 核料"), type="primary", key="se_bp_btn"):
        if not _effective_sel:
            st.error(t("Please select at least one PC No. above before generating."))
        else:
            # Per-step timing collector — summarised in a table at the end of
            # the status box so any slowness names its own step.
            _step_times: list[tuple[str, float]] = []

            def _mark(label: str, t0: float) -> None:
                _step_times.append((label, time.time() - t0))

            # Live progress from the FIRST moment of the click. Everything
            # below (DB read, colour lookups, brand registration, fabric
            # parts, and especially the photo read from a possibly-network
            # folder) runs BEFORE the st.status box opens -- without this
            # the app looked frozen for that whole stretch.
            _prep = st.empty()

            def _say(msg: str) -> None:
                _prep.info(f"⏳ {msg}")

            _say(t("Loading order data…"))
            _t0 = time.time()
            df_items = store.list_items(pc_nos=_effective_sel)
            _mark("Load order data (DB)", _t0)
            if df_items.empty:
                st.warning(t("No data found for the selected contracts."))
            else:
                _say(t("Building colour lookups…"))
                _t0 = time.time()
                color_lookups = _build_buyplan_color_lookups()
                _mark("Build colour lookups", _t0)
                import shutil as _shutil
                out_dir = tempfile.mkdtemp()
                try:
                    _say(t("Checking brands…"))
                    _t0 = time.time()

                    # ── Auto-register new brands in 船样要求 admin ──────────────────────
                    # Any brand that appears in the loaded data but isn't yet in the
                    # shipping-sample-requirement table is added with empty req_text, so
                    # it shows up in Admin → 船样要求 ready for the user to fill in.
                    if "brand" in df_items.columns:
                        _data_brands = (
                            df_items["brand"].dropna().astype(str).str.strip()
                            .replace({"": None, "nan": None, "None": None}).dropna()
                            .unique().tolist()
                        )
                        if _data_brands:
                            from po_extractor.store import get_boat_sample_store
                            _new_brands = get_boat_sample_store().register_missing_brands(
                                COMPANY_SKY_EAST, _data_brands
                            )
                            if _new_brands:
                                _list = ", ".join(f"**{b}**" for b in _new_brands[:8])
                                if len(_new_brands) > 8:
                                    _list += f" … +{len(_new_brands) - 8} more"
                                st.warning(
                                    f"🆕 {len(_new_brands)} new brand(s) found and added "
                                    f"to **Admin → 🚢 船样要求**: {_list}. "
                                    "Open that admin panel to fill in the shipping-sample "
                                    "requirement text — until then column **P** will be "
                                    "blank for these brands.",
                                    icon="🚢",
                                )

                    _mark("Register new brands", _t0)

                    _say(t("Loading fabric parts…"))
                    _t0 = time.time()
                    styles = (
                        df_items["style"].dropna().unique().tolist()
                        if "style" in df_items.columns else []
                    )
                    fabric_parts_by_style = (
                        get_store().load_fabric_parts_for_styles(styles, source=SOURCE_SKY_EAST)
                        if styles else {}
                    )
                    # Enrich composition / gsm / width from fabric master so
                    # _display_key_for can build the full 综合标识Key (HHN|comp|gsm|width).
                    if fabric_parts_by_style:
                        _enrich_parts_from_fabric_master(fabric_parts_by_style)

                    # ── Back-fill fabric_item_no from fabric_parts_by_style ──────────
                    # The raw DB column may be empty when the HHN was imported via the
                    # fabric_parts table (parsed from column E of the Sky East form).
                    # Both export_sky_east_buyplan and export_sky_east_nukuryou group
                    # by fabric_item_no, so we must fill it before calling either.
                    if fabric_parts_by_style and "style" in df_items.columns:
                        # Vectorised: build a {style: hhn_no} map from the first part of
                        # each style, then fill missing fabric_item_no values via map().
                        _style_to_hhn = {
                            s: (parts[0].hhn_no if parts else "")
                            for s, parts in fabric_parts_by_style.items()
                        }
                        df_items = df_items.copy()
                        _existing = (
                            df_items.get("fabric_item_no", pd.Series("", index=df_items.index))
                            .fillna("").astype(str).str.strip()
                        )
                        _is_blank = _existing.str.lower().isin(("", "none", "nan"))
                        _filled = (
                            df_items["style"].astype(str).str.strip().map(_style_to_hhn)
                            .fillna(_existing)
                        )
                        df_items["fabric_item_no"] = _existing.where(~_is_blank, _filled)
                    _mark("Fabric parts + auto-fill", _t0)

                    # ── Build style → [front_bytes, back_bytes] image map ────────────
                    # Used for: Index sheet thumbnail (front) + Photo1/Photo2 in each
                    # style sheet.  Batch loader: ONE directory listing per folder
                    # instead of per-style existence probes — on a network/Mountain
                    # Duck image folder the per-style probes were network round-trips
                    # and dominated the whole generation (minutes). Falls back to the
                    # persistent extracted-images folder, then the session
                    # picture_id cache below.
                    _img_folder = (st.session_state.get(SK.SE_IMAGES_DIR) or "").strip() \
                                  or IMAGES_DIR_DEFAULT
                    # Session-level photo reuse: regenerating with the same
                    # folder + styles skips re-reading the bytes entirely —
                    # on a network/Mountain Duck image folder that's ~20 MB
                    # of transfer per regeneration. Invalidated by a new
                    # upload run (sky_east_view resets it) or any change of
                    # folder / style selection (part of the key).
                    _photo_key = (_img_folder, tuple(sorted(styles)))
                    _photo_cached = st.session_state.get(SK.SE_PHOTO_CACHE) or {}
                    if _photo_cached.get("key") == _photo_key:
                        style_image_map: dict = _photo_cached["map"]
                        # Replay the load's read errors so the photo-issue log
                        # stays truthful on cached runs too.
                        _bad_photos = _photo_cached.get("errors") or []
                        st.caption(
                            f"🖼 {len(style_image_map)}/{len(styles)} style "
                            f"photo(s) reused from this session (no re-read)"
                        )
                        _step_times.append(("Style photos (session cache)", 0.0))
                    else:
                        _say(t("Reading style photos from") + f" {_img_folder} …")
                        _t_photos = time.time()
                        style_image_map = load_style_photo_map(styles, _img_folder)
                        _photos_secs = time.time() - _t_photos
                        from ui.shared import get_last_photo_errors
                        _bad_photos = get_last_photo_errors()
                        st.session_state[SK.SE_PHOTO_CACHE] = {
                            "key": _photo_key, "map": style_image_map,
                            "errors": _bad_photos,
                        }
                        st.caption(
                            f"🖼 {len(style_image_map)}/{len(styles)} style photo(s) "
                            f"loaded in {_photos_secs:.1f}s"
                            + (f" — folder: {_img_folder}" if _photos_secs > 5 else "")
                        )
                        _step_times.append(("Style photos (load)", _photos_secs))
                        if _bad_photos:
                            st.warning(
                                f"⚠️ {len(_bad_photos)} " + t(
                                    "photo file(s) could not be read and were "
                                    "skipped (a broken file on a network share "
                                    "can stall a whole minute — it will be "
                                    "retried automatically later). Fix or "
                                    "delete these on the share:"
                                ) + "\n\n"
                                + "\n".join(f"- `{p}`" for p in _bad_photos[:10]),
                                icon="⚠️",
                            )

                    # Fallback: session / extracted picture_id cache (front only) for
                    # styles whose {style}_front.png files were not found.
                    if "picture_id" in df_items.columns:
                        _all_pids = df_items["picture_id"].dropna().astype(str).unique().tolist()
                        _pid_cache = build_image_cache_for_ids(_all_pids)
                        for _, _irow in df_items.iterrows():
                            _s   = str(_irow.get("style",      "") or "").strip()
                            _pid = str(_irow.get("picture_id", "") or "").strip()
                            if _s and _pid and _s not in style_image_map:
                                _img = _pid_cache.get(_pid)
                                if _img:
                                    style_image_map[_s] = [_img, None]

                    # Record styles with NO photo so the user is warned (below)
                    # exactly which style pictures are missing from the buy plan.
                    _styles_no_photo = sorted(
                        str(s).strip() for s in styles
                        if str(s).strip() and str(s).strip() not in style_image_map
                    )
                    st.session_state[SK.SE_BP_NOPHOTO] = _styles_no_photo

                    # ── Persist the photo-issue log (replaced per generation) ──
                    # One reviewable table: missing pictures + unreadable files
                    # (see 🖼 Photo issues panel below the downloads).
                    try:
                        _issue_rows = [
                            {"style": _s, "issue": "missing", "detail": ""}
                            for _s in _styles_no_photo
                        ]
                        for _p in (_bad_photos or []):
                            _base = os.path.basename(_p)
                            _sty = _base.replace("_front.png", "").replace("_back.png", "")
                            _issue_rows.append(
                                {"style": _sty, "issue": "error", "detail": _p})
                        store.replace_photo_issues(_issue_rows)
                    except Exception:
                        pass   # the log is diagnostics — never block generation

                    # Timestamp the output filenames so regenerating doesn't
                    # silently overwrite the previous download.
                    _ts = datetime.now().strftime("%Y%m%d-%H%M")

                    # Capture the exporters' diagnostic warnings (missing HHN
                    # codes, 主标颜色 mismatch/missing, …) — otherwise they only
                    # reach the server log.  Surfaced to the user below.
                    _prep.empty()
                    with st.status("Generating...", expanded=True) as _status, \
                            _warnings.catch_warnings(record=True) as _wrec:
                        _warnings.simplefilter("always")

                        # Show which colour source + recognition mode this run uses.
                        _src_label = "大货进度表" if color_lookups.by_pc is not None else "Internal DB"
                        try:
                            from ui.stores import get_app_settings_store
                            from po_extractor.store.app_settings_store import (
                                KEY_COLOR_AI_ENHANCE, KEY_DEEPSEEK_API_KEY,
                            )
                            _asx = get_app_settings_store()
                            _ai_on   = _asx.get(KEY_COLOR_AI_ENHANCE, "local") == "local_ai_enhance"
                            _has_key = bool(_asx.get(KEY_DEEPSEEK_API_KEY, ""))
                        except Exception:
                            _ai_on, _has_key = False, False
                        if _ai_on and _has_key:
                            _reco_label = "Local + AI Enhance"
                        elif _ai_on:
                            _reco_label = "Local (⚠ AI Enhance on, but no API key)"
                        else:
                            _reco_label = "Local only"
                        st.write(
                            f"🎨 {t('Colour source')}: **{_src_label}** · "
                            f"{t('Recognition')}: **{_reco_label}**"
                        )

                        st.write("Building main buy plan (Template)...")
                        _t_bp = time.time()
                        _bp_progress = st.progress(0, text="Starting…")

                        def _bp_on_progress(frac: float, label: str) -> None:
                            try:
                                _bp_progress.progress(min(max(frac, 0.0), 1.0), text=label)
                            except Exception:
                                pass   # a progress-UI hiccup must never fail the export

                        try:
                            bp_path, style_totals = export_sky_east_buyplan(
                                df_items, color_lookups.cn, out_dir,
                                fabric_parts_by_style=fabric_parts_by_style,
                                style_image_map=style_image_map or None,
                                label_lookup=color_lookups.label,
                                cn_code_lookup=color_lookups.cn_code,
                                cn_by_pc_lookup=color_lookups.by_pc,
                                brand_by_pc_lookup=color_lookups.brand_by_pc,
                                fabric_version_id=_fabric_version_id,
                                on_progress=_bp_on_progress,
                            )
                            with open(bp_path, "rb") as f:
                                st.session_state[SK.SE_BP_BYTES] = f.read()
                            # Filename: SkyEast_HHPPC040_HHPPC041_BuyPlan_20260702-1530.xlsx
                            _pc_tag = "_".join(_effective_sel) if len(_effective_sel) <= 4 else f"{len(_effective_sel)}PCs"
                            st.session_state[SK.SE_BP_NAME] = f"SkyEast_{_pc_tag}_BuyPlan_{_ts}.xlsx"
                            st.write(f"✔ Buy plan done in {time.time() - _t_bp:.1f}s")
                            _step_times.append(("Buy plan export", time.time() - _t_bp))
                            _out_folder = (st.session_state.get(SK.SE_OUTPUT_DIR) or "").strip()
                            if _out_folder:
                                # Best-effort direct save -- an unreachable
                                # folder must never fail the generation (the
                                # download buttons still have the bytes).
                                try:
                                    _t_save = time.time()
                                    os.makedirs(_out_folder, exist_ok=True)
                                    _dst = os.path.join(
                                        _out_folder, st.session_state[SK.SE_BP_NAME])
                                    _shutil.copy2(bp_path, _dst)
                                    _mb = os.path.getsize(bp_path) / 1e6
                                    st.write(
                                        f"💾 {t('Saved to')} {_dst} "
                                        f"({_mb:.1f} MB in {time.time() - _t_save:.1f}s"
                                        f" — {t('network folder speed, not generation')})"
                                    )
                                    _step_times.append(("Save buy plan to output folder", time.time() - _t_save))
                                    _push_dir("se_output_dir", _out_folder)
                                except OSError as _exc:
                                    st.warning(
                                        f"⚠️ {t('Could not save to output folder')}: {_exc}")
                        except Exception as exc:
                            st.error(f"Buy plan failed: {exc}")
                            style_totals = {}

                        st.write("Building 核料 workbooks (Template_P)...")
                        _t_nk = time.time()
                        try:
                            nk_paths = export_sky_east_nukuryou(
                                df_items, color_lookups.cn, out_dir,
                                cn_code_lookup=color_lookups.cn_code,
                                cn_by_pc_lookup=color_lookups.by_pc,
                            )
                            if nk_paths:
                                nk_buf = io.BytesIO()
                                with zipfile.ZipFile(nk_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for p in nk_paths:
                                        zf.write(p, os.path.basename(p))
                                st.session_state[SK.SE_NK_BYTES] = nk_buf.getvalue()
                                st.session_state[SK.SE_NK_COUNT] = len(nk_paths)
                                st.session_state[SK.SE_NK_REASON] = None
                            else:
                                st.session_state[SK.SE_NK_BYTES] = None
                                st.session_state[SK.SE_NK_COUNT] = 0
                                st.session_state[SK.SE_NK_REASON] = check_nukuryou_ready(df_items)
                            st.write(f"✔ 核料 done in {time.time() - _t_nk:.1f}s")
                            _step_times.append(("核料 export", time.time() - _t_nk))
                            _out_folder = (st.session_state.get(SK.SE_OUTPUT_DIR) or "").strip()
                            if _out_folder and nk_paths:
                                try:
                                    _t_save = time.time()
                                    os.makedirs(_out_folder, exist_ok=True)
                                    for _p in nk_paths:
                                        _shutil.copy2(
                                            _p, os.path.join(_out_folder, os.path.basename(_p)))
                                    st.write(
                                        f"💾 {len(nk_paths)} {t('核料 workbook(s) saved to')} "
                                        f"{_out_folder} ({time.time() - _t_save:.1f}s)")
                                    _step_times.append(("Save 核料 to output folder", time.time() - _t_save))
                                except OSError as _exc:
                                    st.warning(
                                        f"⚠️ {t('Could not save to output folder')}: {_exc}")
                        except Exception as exc:
                            st.warning(f"核料 workbooks skipped: {exc}")
                            st.session_state[SK.SE_NK_BYTES] = None
                            st.session_state[SK.SE_NK_COUNT] = 0
                            st.session_state[SK.SE_NK_REASON] = str(exc)

                        if style_totals:
                            st.write("Running cross-comparison...")
                            _t_cmp = time.time()
                            try:
                                cmp_df = build_cross_comparison(style_totals, df_items)
                                st.session_state[SK.SE_BP_CMP] = cmp_df
                            except Exception:
                                st.session_state[SK.SE_BP_CMP] = None
                        else:
                            st.session_state[SK.SE_BP_CMP] = None

                        if style_totals:
                            _step_times.append(("Cross-comparison", time.time() - _t_cmp))

                        _warn_missing_color_translations(df_items, cn_map=color_lookups.cn)

                        # Collect the exporters' [sky_east …] diagnostic warnings
                        # so they can be shown in the UI (not just the server log).
                        st.session_state[SK.SE_BP_DIAGS] = [
                            str(w.message) for w in _wrec
                            if str(w.message).startswith("[sky_east")
                        ]

                        # ── Notify subscribers (best-effort, never blocking) ──
                        from po_extractor.utils.notifications import (
                            notify_buyplan_generated, notify_fabric_missing,
                        )
                        _pc_tag_txt = ", ".join(_effective_sel[:5]) + (
                            f" +{len(_effective_sel) - 5}"
                            if len(_effective_sel) > 5 else "")
                        notify_buyplan_generated(
                            "Sky East", _pc_tag_txt, _distinct_styles,
                            [st.session_state.get(SK.SE_BP_NAME, "")],
                        )
                        if _uncovered:
                            notify_fabric_missing(
                                "Sky East", _pc_tag_txt,
                                [f"{s} — no 面料编号 (HHN No.) on file"
                                 for s in _uncovered],
                            )

                        # ── Per-step timing summary ──────────────────────────
                        if _step_times:
                            _total = sum(sec for _, sec in _step_times)
                            _tdf = pd.DataFrame(
                                [(lbl, round(sec, 1)) for lbl, sec in _step_times]
                                + [("TOTAL", round(_total, 1))],
                                columns=[t("Step"), t("Seconds")],
                            )
                            st.write(f"⏱ {t('Time per step')}:")
                            st.dataframe(_tdf, hide_index=True, width="content")

                        _status.update(label="Done!", state="complete")

                finally:
                    # All file bytes are now in session_state — temp dir no longer needed
                    _shutil.rmtree(out_dir, ignore_errors=True)
                    # The image lookup accumulates decoded photos in the session
                    # cache; keep it bounded (misses reload from disk).
                    try:
                        from ui.memory import trim_image_cache
                        trim_image_cache()
                    except Exception:
                        pass

    # ── Diagnostics captured during generation (missing HHN, 主标颜色, …) ──────
    _diags = st.session_state.get(SK.SE_BP_DIAGS) or []
    for _d in _diags:
        # Strip the internal "[sky_east buyplan] " prefix for a cleaner message.
        _msg = _d.split("] ", 1)[1] if "] " in _d else _d
        st.warning(_msg, icon="⚠️")

    # ── Missing style photos — name exactly which styles have no picture ──────
    _nophoto = st.session_state.get(SK.SE_BP_NOPHOTO) or []
    if _nophoto:
        _prev = ", ".join(_nophoto[:10]) + (
            f" … +{len(_nophoto) - 10} more" if len(_nophoto) > 10 else "")
        st.warning(
            f"🖼 {len(_nophoto)} " + t("style(s) have no photo in the buy plan")
            + f": {_prev}. "
            + t("Re-run **Process** on New Contracts to (re)extract images, or drop "
                "`<style>_front.png` into the image folder."),
            icon="🖼",
        )

    _misses_df = None   # deduped colour-miss log, shared with the log section below
    if st.session_state.get(SK.SE_BP_BYTES) or st.session_state.get(SK.SE_NK_BYTES):
        st.divider()
        dl_cols = st.columns(2)

        # Unresolved-colour count (distinct, de-duplicated across re-runs) —
        # reflected in the buy-plan caption so a green download button doesn't
        # hide misses.  Fetched once here and reused by
        # _se_color_miss_log_section so the log isn't queried + deduped twice
        # per rerun.
        try:
            _misses_df = _dedupe_color_misses(get_sky_east_store().list_color_misses())
            _miss_n = len(_misses_df)
        except Exception:
            _misses_df, _miss_n = None, 0

        with dl_cols[0]:
            if st.session_state.get(SK.SE_BP_BYTES):
                st.download_button(
                    "Buy Plan (.xlsx)",
                    data=st.session_state[SK.SE_BP_BYTES],
                    file_name=st.session_state.get(SK.SE_BP_NAME, "Sky_East_BuyPlan.xlsx"),
                    mime=XLSX_MIME,
                    key="se_bp_dl",
                    use_container_width=True,
                    type="primary",
                )
                if _miss_n:
                    st.caption(f"⚠️ {_miss_n} " + t("unresolved colour(s) — see the log below"))
                else:
                    st.caption(t("Main buy plan -- one sheet per style + Index"))

        with dl_cols[1]:
            if st.session_state.get(SK.SE_NK_BYTES):
                n = st.session_state.get(SK.SE_NK_COUNT, 0)
                # Tie the 核料 zip name to the same timestamped buy-plan run.
                _bp_name = st.session_state.get(SK.SE_BP_NAME, "")
                _nk_name = (
                    _bp_name.replace("_BuyPlan_", "_核料_").replace(".xlsx", ".zip")
                    if _bp_name.endswith(".xlsx") and "_BuyPlan_" in _bp_name
                    else "Sky_East_核料.zip"
                )
                st.download_button(
                    f"核料 Workbooks (.zip) -- {n} file(s)",
                    data=st.session_state[SK.SE_NK_BYTES],
                    file_name=_nk_name,
                    mime=ZIP_MIME,
                    key="se_nk_dl",
                    use_container_width=True,
                )
                st.caption(t("One workbook per fabric -- Color x Size per style"))
            elif st.session_state.get(SK.SE_BP_BYTES):
                _nk_reason = st.session_state.get(SK.SE_NK_REASON)
                if _nk_reason:
                    st.info(f"No 核料 workbooks generated — {_nk_reason}", icon="ℹ️")
                else:
                    st.info(
                        "No 核料 workbooks generated -- check that Template_P "
                        "is installed in Admin → Templates.",
                        icon="ℹ️",
                    )

    if st.session_state.get(SK.SE_BP_CMP) is not None:
        cmp_df = st.session_state[SK.SE_BP_CMP]
        # Substring match — robust to the emoji prefix on the "Mismatch" label
        # changing in build_cross_comparison (BUG-30 was an exact-string break).
        mismatches = int(cmp_df["Match"].astype(str).str.contains("Mismatch").sum())
        if mismatches:
            st.warning(f"{mismatches} " + t("style(s) have unit-total mismatches between buy plan and 核料 data."))
            # Most common cause: a style produced no 核料 output because it has
            # no fabric code (核料 is grouped by fabric_item_no).  Surface that
            # concretely and point at where to fix it.
            _nk_col = "Total (核料)"
            if _nk_col in cmp_df.columns:
                _skipped = cmp_df[
                    cmp_df["Match"].astype(str).str.contains("Mismatch")
                    & (pd.to_numeric(cmp_df[_nk_col], errors="coerce").fillna(0) == 0)
                ]["Style"].astype(str).tolist()
                if _skipped:
                    _preview = ", ".join(_skipped[:6]) + (
                        f" … +{len(_skipped) - 6} more" if len(_skipped) > 6 else ""
                    )
                    st.info(
                        f"ℹ️ {len(_skipped)} "
                        + t("of these produced **no 核料 output** — most likely no "
                            "fabric code on file")
                        + f" ({_preview}). "
                        + t("Add the 面料编号 (HHN No.) via the **Missing Fields** tab "
                            "or **📐 Reference Data**, then regenerate."),
                        icon="🧩",
                    )
        else:
            st.success(t("All style totals match between buy plan and 核料 workbooks."))
        with st.expander(t("Cross-comparison detail")):
            st.dataframe(cmp_df, width="stretch", hide_index=True)

    if st.session_state.get(SK.SE_BP_BYTES):
        _se_color_miss_log_section(_misses_df)
        _se_photo_issue_log_section()

    _se_hist_email_section()


def _dedupe_color_misses(df):
    """Collapse the append-only colour-miss log to one row per distinct miss.

    The store appends a fresh row every generation run, so the same
    (PC · contract · style · PO · colour) miss stacks up across re-runs. For
    display we keep only the most recent occurrence of each — the DB stays a
    full audit trail; only the shown table is de-duplicated.
    """
    if df is None or df.empty:
        return df
    _key = [c for c in ("pc_no", "contract_no", "style", "po_no",
                        "client_po_color", "attempted_color", "source")
            if c in df.columns]
    if not _key or "logged_at" not in df.columns:
        return df
    return (df.sort_values("logged_at", ascending=False)
              .drop_duplicates(subset=_key, keep="first")
              .reset_index(drop=True))


def _se_photo_issue_log_section() -> None:
    """Reviewable log of picture problems from the most recent buy-plan
    generation: styles with NO photo anywhere ('missing') and source files
    that failed to read ('error', e.g. a corrupt file on the network share).
    The table is REPLACED on every generation, so fixing a photo makes its
    row disappear on the next run — no manual clearing needed (the Clear
    button just empties it early)."""
    from ui.stores import get_sky_east_store

    store = get_sky_east_store()
    issues = store.list_photo_issues()
    if not issues:
        return

    n_missing = sum(1 for i in issues if i["issue"] == "missing")
    n_error = len(issues) - n_missing
    st.warning(
        "🖼 " + t("Photo issues in the last generation:") + " "
        + f"{n_missing} " + t("missing picture(s)")
        + (f", {n_error} " + t("unreadable file(s)") if n_error else "") + ".",
        icon="🖼",
    )
    with st.expander(f"🖼 {t('Photo issues')} ({len(issues)})", expanded=False):
        st.caption(t(
            "'missing' = no {style}_front.png in the image folder, the "
            "extracted-images fallback, or the upload's embedded pictures — "
            "the buy plan has no photo for that style. 'error' = the source "
            "file exists but could not be read (often a corrupt file on the "
            "network share; it is skipped fast and retried automatically "
            "after a few hours). This list is refreshed on every generation."
        ))
        df = pd.DataFrame([{
            "Style":  i["style"],
            "Issue":  ("缺少照片 missing" if i["issue"] == "missing"
                       else "读取失败 error"),
            "File":   i["detail"] or "—",
            "Logged": i["logged_at"],
        } for i in issues])
        st.dataframe(
            df, width="stretch", hide_index=True,
            height=min(60 + 36 * len(df), 400),
            column_config={
                "Style":  st.column_config.TextColumn(t("Style"), width="small"),
                "Issue":  st.column_config.TextColumn(t("Issue"), width="small"),
                "File":   st.column_config.TextColumn(t("File"), width="large"),
                "Logged": st.column_config.TextColumn(t("Logged At"), width="small"),
            },
        )
        if st.button(f"🗑️ {t('Clear photo issue log')}", key="se_clear_photo_issues"):
            store.clear_photo_issues()
            fragment_rerun()


def _se_color_miss_log_section(misses_df=None) -> None:
    """Show colours that failed to resolve during the most recent buy plan
    generation -- mirrors the "Client's PO colour" comment attached to the
    未找到 cells in the Overview sheet, but as a reviewable table so the
    user doesn't have to hunt through every sheet for them.

    ``misses_df`` — already-deduped log from the caller (avoids re-querying
    the store on the same rerun); ``None`` fetches it here.
    """
    from ui.stores import get_sky_east_store

    store = get_sky_east_store()
    if misses_df is None:
        misses_df = _dedupe_color_misses(store.list_color_misses())
    if misses_df is None or misses_df.empty:
        return

    st.warning(
        f"⚠️ {len(misses_df)} " + t(
            "distinct colour(s) could not be resolved across recent buy plan runs "
            "-- see the cell comments on the Overview sheet's 未找到 cells, or the "
            "detail below."
        ),
        icon="⚠️",
    )
    with st.expander(f"{t('Colour resolution issues')} ({len(misses_df)})", expanded=False):
        _display_df = misses_df.copy()
        _display_df["progress_colors"] = _display_df["progress_colors"].fillna("")
        st.dataframe(
            _display_df[[
                "logged_at", "pc_no", "contract_no", "style", "po_no",
                "client_po_color", "progress_colors", "source",
            ]].rename(columns={
                "logged_at": "Logged At", "pc_no": "PC No.", "contract_no": "Contract No.",
                "style": "Style", "po_no": "PO No.", "client_po_color": "Client's PO Colour",
                "progress_colors": "大货进度表 Colour(s)", "source": "Source",
            }),
            width="stretch", hide_index=True,
        )
        if st.button("🗑️ Clear colour resolution log", key="se_clear_color_miss_log"):
            n = store.clear_color_misses()
            st.success(f"Cleared {n} logged issue(s).")
            fragment_rerun()


def _se_hist_email_section() -> None:
    """Email the generated buy plan / 核料 zip to a recipient.

    Default recipient is the logged-in user's email (set in Admin → Users)
    but the user can override it before sending.
    """
    bp_bytes = st.session_state.get(SK.SE_BP_BYTES)
    nk_bytes = st.session_state.get(SK.SE_NK_BYTES)
    if not (bp_bytes or nk_bytes):
        return

    from po_extractor.utils.email_utils import (
        EmailError, is_email_configured, send_email_with_attachments,
    )
    from auth.users import get_user_email

    st.divider()
    st.markdown("**📧 Send via Email**")

    if not is_email_configured():
        st.info(
            "SMTP is not configured on the server. Set `PO_SMTP_HOST`, "
            "`PO_SMTP_USER`, `PO_SMTP_PASSWORD` (and optionally `PO_SMTP_FROM`, "
            "`PO_SMTP_PORT`) in the environment, then restart the app.",
            icon="ℹ️",
        )
        return

    # Brevo silent-drop guard: warn if the sender address is the @smtp-brevo.com
    # login username.  Brevo accepts the SMTP handshake but never delivers such emails.
    from auth import smtp_settings as _smtp_cfg
    _smtp_s = _smtp_cfg.load()
    _eff_sender = _smtp_cfg.effective_sender(_smtp_s)
    if "brevo" in _smtp_s["host"].lower() and (
        not _eff_sender or _eff_sender.lower().endswith("@smtp-brevo.com")
    ):
        st.warning(
            "⚠️ **Email will not be delivered.** Your Sender address is "
            f"`{_eff_sender}` — Brevo silently drops emails whose From address is "
            "not a verified sender. Go to **⚙️ Admin → 📧 Email** and fill in a "
            "verified Sender address (e.g. `orders@yourdomain.com`), then try again."
        )

    default_to = get_user_email(st.session_state.username)
    c_to, c_send = st.columns([4, 1])
    with c_to:
        recipient = st.text_input(
            "Recipient email",
            value=default_to,
            key="se_email_to",
            placeholder="user@example.com",
            help="Defaults to the email on your user profile (Admin → Users). "
                 "You can override it for one-off sends.",
        )
    with c_send:
        st.write("")  # vertical alignment with text_input
        send_clicked = st.button(
            "Send", type="primary", use_container_width=True,
            key="se_email_send", disabled=not recipient.strip(),
        )

    if not send_clicked:
        return

    bp_name = st.session_state.get(SK.SE_BP_NAME, "Sky_East_BuyPlan.xlsx")
    attachments: list[tuple[str, bytes, str]] = []
    if bp_bytes:
        attachments.append((bp_name, bp_bytes, XLSX_MIME))
    if nk_bytes:
        attachments.append(("Sky_East_核料.zip", nk_bytes, ZIP_MIME))

    from po_extractor.config import APP_NAME
    subject = f"Sky East Buy Plan — {bp_name}"
    body = (
        f"Hi,\n\n"
        f"Attached are the generated files from {APP_NAME}:\n"
        + "".join(f"  • {fn}\n" for fn, _, _ in attachments)
        + f"\nGenerated by: {st.session_state.username}\n"
    )
    try:
        with st.spinner(f"Sending to {recipient}…"):
            send_email_with_attachments(recipient, subject, body, attachments)
        st.success(f"Sent {len(attachments)} attachment(s) to {recipient}.")
    except EmailError as exc:
        from ui.admin_smtp import _smtp_error_hint
        from auth import smtp_settings as _smtp_cfg
        st.error(f"Email failed: {exc}")
        hint = _smtp_error_hint(exc, host=_smtp_cfg.load()["host"])
        if hint:
            st.warning(hint + "\n\nFix settings in **⚙️ Admin → 📧 Email**.")


def _show_se_history_section():
    """Browse saved Sky East contracts and view amendment history."""
    store = get_sky_east_store()
    df_contracts = store.list_contracts()

    # ── Auto-clean orphaned blank-pc_no contracts (left by old parser bugs) ──
    # Files uploaded before the dynamic header fix could save a contract with
    # pc_no = ''.  These show up as invisible items in every multiselect and
    # make the widgets appear broken.  Silently remove them on every load.
    blank_pcs = df_contracts[df_contracts["pc_no"].fillna("").str.strip() == ""]["pc_no"].tolist()
    if blank_pcs:
        store.delete_contracts(blank_pcs)
        from ui.sky_east._missing_compute import _compute_se_missing_df
        _compute_se_missing_df.clear()
        _se_buyplan_fabric_preflight.clear()
        df_contracts = store.list_contracts()   # refresh after cleanup

    total = len(df_contracts)
    st.subheader(f"{t('Saved Contracts')} — {total} PC No.(s)")

    if df_contracts.empty:
        st.info(t("No Sky East contracts saved yet."))
        return

    _se_hist_summary_table(df_contracts)
    st.divider()
    # Filter out any blank / None pc_nos defensively before building options
    pc_options = [pc for pc in df_contracts["pc_no"].tolist() if pc and str(pc).strip()]

    _se_hist_item_browser(store, pc_options)
    st.divider()
    _se_hist_delete_section(store, pc_options)
