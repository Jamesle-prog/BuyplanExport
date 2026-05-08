"""Sky East history section — contract browser, downloads, buy plan generation."""
from __future__ import annotations
import base64
import io
import os
import tempfile
import zipfile
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
    XLSX_MIME, ZIP_MIME,
    _th, _tr,
    build_image_cache_for_ids,
    persisted_download,
)
from ui.stores import get_store, get_sky_east_store, get_color_translation_store, get_fabric_master_store, IMAGES_DIR_DEFAULT
from ui.sky_east._shared import (
    live_label, _get_dual_header, _write_dual_header_excel, _write_wash_label_excel,
    show_color_source_radio,
)
from ui.sky_east.items_view import _enrich_items_df, _build_items_display_df


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Excel file extensions accepted by uploaders in this module.  Centralised so
# adding (e.g.) ``"xlsm"`` only needs one edit.
_EXCEL_FILE_TYPES   = ["xlsx", "xls"]
_DEFAULT_XLSX_EXT   = ".xlsx"

# 大货进度表 uploader UI strings — kept inline below so they remain searchable
# alongside the widget that renders them; no constants extracted unless reused.


# ---------------------------------------------------------------------------
# History section helpers
# ---------------------------------------------------------------------------


def _build_buyplan_color_lookups() -> tuple[dict, dict | None, dict | None, dict | None]:
    """Build ``(cn_lookup, label_lookup, cn_code_lookup, cn_by_pc_lookup)``
    honoring the user's color-source choice.

    Always starts from the canonical Color-Translation DB.  When the user has
    chosen ``COLOR_SOURCE_PROGRESS`` *and* a 大货进度表 is loaded in this session,
    its entries are merged in on top (progress data wins) for all lookups.

    Returns
    -------
    cn_lookup : dict
        ``{(client, brand, en_color): cn_color}``
    label_lookup : dict | None
        ``None`` → exporter auto-fetches from DB.
    cn_code_lookup : dict | None
        ``{(client, brand, en_color): color_code}`` (中文颜色代码, e.g. "52#").
        ``None`` → exporter auto-fetches from DB.
    cn_by_pc_lookup : dict | None
        ``{(pc_no_norm, style_norm, en_color_norm): (cn_color, color_code)}`` —
        used by the exporter for per-row PC-No.-prioritised lookup of both
        the Chinese color name and code simultaneously.
        ``None`` when not using progress source (exporter skips this tier).
    """
    color_source  = st.session_state.get(SK.SE_COLOR_SOURCE)
    progress_lkup = st.session_state.get(SK.SE_PROGRESS_LKUP)
    cn_store      = get_color_translation_store()
    cn_lookup     = cn_store.build_lookup_dict()

    if color_source != COLOR_SOURCE_PROGRESS:
        return cn_lookup, None, None, None

    if progress_lkup is None:
        # The buyplan section shows an inline uploader when this happens,
        # so no extra warning needed here — just fall back silently.
        return cn_lookup, None, None, None

    # Primary-only: build the PC No. + style + color keyed lookup.
    # Flat brand-keyed data from the progress file is intentionally NOT merged
    # so that only an exact (PC No · 款式 · 颜色) match returns a value —
    # no looser fallback keys from the progress sheet bleed into the result.
    # The Internal DB is still used as fallback for colours that have no PC match.
    cn_by_pc_lookup = progress_lkup.build_pc_style_color_lookups()
    st.caption("🗂 Chinese colors sourced from 大货进度表 (PC No. · style · color match only).")
    return cn_lookup, None, None, cn_by_pc_lookup


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
            "seller": "Seller", "total_styles": "Styles",
            "total_qty": "Total Qty", "currency": "Currency",
            "trade_term": "Trade Term", "extracted_at": "Extracted At",
            "source_file": "Source File",
        })),
        width="stretch",
        hide_index=True,
    )


def _se_hist_multi_pc_download(store, pc_options: list[str]) -> None:
    """Multi-PC items download section (Excel or CSV)."""
    st.markdown(f"**{t('Download items by PC No.')}**")
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
            pcs_label = "_".join(sel_dl_pcs) if len(sel_dl_pcs) <= 3 else f"{len(sel_dl_pcs)}PCs"
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


def _warn_missing_color_translations(df_items: pd.DataFrame) -> None:
    """Surface (brand, en_color) pairs in the buy plan that have no Chinese
    translation or label colour in the DB.

    ``cn_color`` empty → BODY COLOR-CN cell will be blank.
    ``label_color`` empty → 主标颜色 falls through to the light/dark heuristic,
    which often picks the wrong shade. Either is a data-quality issue worth
    surfacing so the user can fix it in the Color Translation tab.
    """
    if df_items is None or df_items.empty:
        return
    if "color_name" not in df_items.columns:
        return
    from po_extractor.store.color_translation_store import _normalize_color_name

    cn_map    = get_color_translation_store().build_lookup_dict()
    label_map = get_color_translation_store().build_label_lookup_dict()

    missing_cn:    set[tuple[str, str]] = set()
    missing_label: set[tuple[str, str]] = set()
    for _, row in df_items[["brand", "color_name"]].drop_duplicates().iterrows():
        brand = str(row.get("brand", "") or "").strip()
        en    = str(row.get("color_name", "") or "").strip()
        if not en:
            continue
        norm = _normalize_color_name(en)
        cn = cn_map.get((COMPANY_SKY_EAST, brand, norm)) or cn_map.get((COMPANY_SKY_EAST, "", norm))
        lb = label_map.get((COMPANY_SKY_EAST, brand, norm)) or label_map.get((COMPANY_SKY_EAST, "", norm))
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


def _se_hist_wash_label_download(store, pc_options: list[str]) -> None:
    """Wash-label download section — select by PC No., stored Fabric Mapping, or uploaded file."""
    st.markdown(f"**{t('Download Wash Label Content')}**")
    st.caption("Style · Photo · Seq · Body Part · Fabric Code · Composition — up to 4 rows per style")

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
        wl_col1, wl_col2 = st.columns([3, 1])
        with wl_col1:
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
        has_selection = bool(sel_wl_pcs)

    elif sel_mode == "Style (Fabric Mapping)":
        # Styles come from the stored Fabric Mapping DB (Sky East source).
        # Composition is sourced from fabric_master at generation time.
        mapped_styles = _wl_mapped_styles(SOURCE_SKY_EAST)
        if not mapped_styles:
            st.warning(
                "No styles found in the Fabric Mapping database for Sky East. "
                "Go to the **📐 Fabric Mapping** tab to import a mapping first."
            )
            has_selection = False
        else:
            wl_col1, wl_col2 = st.columns([3, 1])
            with wl_col1:
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
        st.caption(
            "Upload a fabric mapping file to generate wash labels for all styles in that file. "
            "This file is used only for this download and is **not** saved to the database."
        )
        wl_upload_file = st.file_uploader(
            "Fabric mapping file (.xlsx / .xls)",
            type=["xlsx", "xls"],
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
                import pandas as _pd

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
                    "_".join(label_parts) if len(label_parts) <= 3
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
                    st.rerun()
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
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
                st.rerun()

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
            st.rerun()

    with c_cancel:
        if st.button("❌ Cancel", key="se_wl_val_cancel", use_container_width=True):
            st.session_state[SK.SE_WL_PENDING] = None
            st.rerun()

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
        df_hist = (pd.concat([f for f in hist_frames if not f.empty], ignore_index=True)
                   if hist_frames else pd.DataFrame())
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
        st.success(f"Deleted {n} contract(s).")
        st.rerun()


def _se_hist_buyplan_section(store, pc_options: list[str],
                              df_contracts=None) -> None:
    """Generate Sky East buy plan + 核料 workbooks for selected contracts."""
    st.markdown(f"**{t('Create Buy Plan')}**")
    st.caption(
        "Generates the main buy plan (Template) and fabric 核料 workbooks (Template_P) "
        "from the selected contracts, matching the VBA output format."
    )
    sel = st.multiselect(
        t("PC No.(s) to include:"),
        pc_options,
        key="se_bp_sel",
        placeholder="Select one or more PC Nos...",
    )

    # ── Total units summary for selection ─────────────────────────────────────
    if sel and df_contracts is not None and not df_contracts.empty:
        _sel_df = df_contracts[df_contracts["pc_no"].isin(sel)]
        _total_units  = int(_sel_df["total_qty"].sum())    if "total_qty"    in _sel_df.columns else 0
        _total_styles = int(_sel_df["total_styles"].sum()) if "total_styles" in _sel_df.columns else 0
        _m1, _m2, _m3 = st.columns(3)
        _m1.metric(t("PCs selected"),   len(sel))
        _m2.metric(t("Total Styles"),   _total_styles)
        _m3.metric(t("Total Units"),    f"{_total_units:,}")

    # ── Color mapping source ──────────────────────────────────────────────────
    show_color_source_radio("se_bp_color_src_radio")

    # ── 大货进度表 uploader (shown whenever progress source is selected) ───────
    if st.session_state.get(SK.SE_COLOR_SOURCE) == COLOR_SOURCE_PROGRESS:
        _prog_lkup = st.session_state.get(SK.SE_PROGRESS_LKUP)
        if _prog_lkup is not None:
            st.caption(f"✅ 大货进度表 loaded ({len(_prog_lkup)} records).")
        _prog_upload = st.file_uploader(
            "📂 Upload 大货进度表 (HHN Contract No. file)",
            type=_EXCEL_FILE_TYPES,
            key="se_bp_progress_uploader",
            help="Upload or replace the 大货进度表 to use as the Chinese color source.",
        )
        if _prog_upload is not None:
            try:
                import tempfile as _tf2
                from po_extractor.lookups import ProgressLookup as _PL
                _tmp_fd, _tmp_path = _tf2.mkstemp(
                    suffix=os.path.splitext(_prog_upload.name)[1] or _DEFAULT_XLSX_EXT
                )
                with os.fdopen(_tmp_fd, "wb") as _fh:
                    _fh.write(_prog_upload.getbuffer())
                _new_lkup = _PL(_tmp_path)
                len(_new_lkup)  # trigger lazy load while file exists
                st.session_state[SK.SE_PROGRESS_LKUP] = _new_lkup
                st.success(
                    f"✅ 大货进度表 loaded: {len(_new_lkup)} records from "
                    f"**{_prog_upload.name}**."
                )
                st.rerun()
            except Exception as _exc:
                st.error(f"Could not parse progress file: {_exc}")

    if st.button(t("Generate Buy Plan + 核料"), type="primary",
                 disabled=not sel, key="se_bp_btn"):

        df_items = store.list_items(pc_nos=sel)
        if df_items.empty:
            st.warning(t("No data found for the selected contracts."))
        else:
            cn_lookup, label_lookup, cn_code_lookup, cn_by_pc_lookup = _build_buyplan_color_lookups()
            out_dir = tempfile.mkdtemp()

            # ── Auto-register new brands in 船样要求 admin ──────────────────────
            # Any brand that appears in the loaded data but isn't yet in the
            # boat_sample_req table is added with empty req_text, so it shows up
            # in Admin → 船样要求 ready for the user to fill in.
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
                            "Open that admin panel to fill in the boat-sample "
                            "requirement text — until then column **P** will be "
                            "blank for these brands.",
                            icon="🚢",
                        )

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
                def _fill_fabric_no(row):
                    existing = str(row.get("fabric_item_no", "") or "").strip()
                    if existing and existing.lower() not in ("none", "nan"):
                        return existing
                    parts = fabric_parts_by_style.get(
                        str(row.get("style", "")).strip(), [])
                    return parts[0].hhn_no if parts else existing
                df_items = df_items.copy()
                df_items["fabric_item_no"] = df_items.apply(_fill_fabric_no, axis=1)

            # ── Build style → [front_bytes, back_bytes] image map ────────────
            # Used for: Index sheet thumbnail (front) + Photo1/Photo2 in each
            # style sheet.  Looks for {style}_front.png / {style}_back.png on
            # disk first (saved by save_images_to_disk during processing), then
            # falls back to the session picture_id cache for front-only.
            import re as _re2
            _img_folder = (st.session_state.get(SK.SE_IMAGES_DIR) or "").strip() \
                          or IMAGES_DIR_DEFAULT
            style_image_map: dict = {}
            for _style in styles:
                _safe = _re2.sub(r'[\\/:*?"<>|]', '_', _style)
                _pair: list = []
                for _pos in ("front", "back"):
                    _disk_path = os.path.join(_img_folder, f"{_safe}_{_pos}.png")
                    try:
                        _pair.append(open(_disk_path, "rb").read()
                                     if os.path.exists(_disk_path) else None)
                    except Exception:
                        _pair.append(None)
                if any(_pair):
                    style_image_map[_style] = _pair

            # Fallback: session picture_id cache (front only) for styles
            # whose on-disk files were not found.
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

            with st.status("Generating...", expanded=True) as _status:

                st.write("Building main buy plan (Template)...")
                try:
                    bp_path, style_totals = export_sky_east_buyplan(
                        df_items, cn_lookup, out_dir,
                        fabric_parts_by_style=fabric_parts_by_style,
                        style_image_map=style_image_map or None,
                        label_lookup=label_lookup,
                        cn_code_lookup=cn_code_lookup,
                        cn_by_pc_lookup=cn_by_pc_lookup,
                    )
                    with open(bp_path, "rb") as f:
                        st.session_state[SK.SE_BP_BYTES] = f.read()
                    # Filename: SkyEast_HHPPC040_HHPPC041_BuyPlan.xlsx
                    _pc_tag = "_".join(sel) if len(sel) <= 4 else f"{len(sel)}PCs"
                    st.session_state[SK.SE_BP_NAME] = f"SkyEast_{_pc_tag}_BuyPlan.xlsx"
                except Exception as exc:
                    st.error(f"Buy plan failed: {exc}")
                    style_totals = {}

                st.write("Building 核料 workbooks (Template_P)...")
                try:
                    nk_paths = export_sky_east_nukuryou(
                        df_items, cn_lookup, out_dir,
                        cn_code_lookup=cn_code_lookup,
                        cn_by_pc_lookup=cn_by_pc_lookup,
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
                except Exception as exc:
                    st.warning(f"核料 workbooks skipped: {exc}")
                    st.session_state[SK.SE_NK_BYTES] = None
                    st.session_state[SK.SE_NK_COUNT] = 0
                    st.session_state[SK.SE_NK_REASON] = str(exc)

                if style_totals:
                    st.write("Running cross-comparison...")
                    try:
                        cmp_df = build_cross_comparison(style_totals, df_items)
                        st.session_state[SK.SE_BP_CMP] = cmp_df
                    except Exception:
                        st.session_state[SK.SE_BP_CMP] = None
                else:
                    st.session_state[SK.SE_BP_CMP] = None

                _warn_missing_color_translations(df_items)

                _status.update(label="Done!", state="complete")

    if st.session_state.get(SK.SE_BP_BYTES) or st.session_state.get(SK.SE_NK_BYTES):
        st.divider()
        dl_cols = st.columns(2)

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
                st.caption("Main buy plan -- one sheet per style + Index")

        with dl_cols[1]:
            if st.session_state.get(SK.SE_NK_BYTES):
                n = st.session_state.get(SK.SE_NK_COUNT, 0)
                st.download_button(
                    f"核料 Workbooks (.zip) -- {n} file(s)",
                    data=st.session_state[SK.SE_NK_BYTES],
                    file_name="Sky_East_核料.zip",
                    mime=ZIP_MIME,
                    key="se_nk_dl",
                    use_container_width=True,
                )
                st.caption("One workbook per fabric -- Color x Size per style")
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
        mismatches = (cmp_df["Match"] == "❌ Mismatch").sum()  # BUG-30: was "Mismatch"
        if mismatches:
            st.warning(f"{mismatches} style(s) have unit-total mismatches between buy plan and 核料 data.")
        else:
            st.success("All style totals match between buy plan and 核料 workbooks.")
        with st.expander("Cross-comparison detail"):
            st.dataframe(cmp_df, width="stretch", hide_index=True)

    _se_hist_email_section()


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

    subject = f"Sky East Buy Plan — {bp_name}"
    body = (
        f"Hi,\n\n"
        f"Attached are the generated files from PO Extractor:\n"
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

    total = len(df_contracts)
    st.subheader(f"{t('Saved Contracts')} — {total} PC No.(s)")

    if df_contracts.empty:
        st.info(t("No Sky East contracts saved yet."))
        return

    _se_hist_summary_table(df_contracts)
    st.divider()
    pc_options = df_contracts["pc_no"].tolist()

    _se_hist_multi_pc_download(store, pc_options)
    st.divider()
    _se_hist_wash_label_download(store, pc_options)
    st.divider()
    _se_hist_item_browser(store, pc_options)
    st.divider()
    _se_hist_buyplan_section(store, pc_options, df_contracts)
    st.divider()
    _se_hist_delete_section(store, pc_options)
