"""GIII results display and download panels."""
from __future__ import annotations
import io
import streamlit as st
import pandas as pd
from po_extractor.ui_helpers import (
    write_excel_header_row as _write_excel_header_row,
    generate_color_plan_excel as _generate_color_plan_excel_impl,
    generate_po_summary_excel as _generate_po_summary_excel_impl,
    generate_kl_format_excel as _generate_kl_format_excel_impl,
)
from ui.i18n import t
from ui.shared import build_thumbnail_data_urls as _build_thumbnail_data_urls
from ui.shared import persisted_download
from ui.shared import ZIP_MIME, HTML_MIME, CSV_MIME
from auth.companies import COMPANY_SKY_EAST
from ui.stores import get_store, get_sky_east_store
from ui.giii._shared import _XLSX_MIME, live_label


def _excel_header_row(ws, cols, fill_hex="4472C4"):
    _write_excel_header_row(ws, cols, fill_hex)


def _generate_color_plan_excel(po_numbers: list, store) -> bytes:
    """Pivot size rows into a color plan: one row per (PO, Style, Color), sizes as columns."""
    df = store.load_size_rows(po_numbers)
    return _generate_color_plan_excel_impl(df)


def _generate_po_summary_excel(
    df_pos: "pd.DataFrame",
    df_sizes: "pd.DataFrame | None" = None,
) -> bytes:
    """Rich two-sheet PO Summary with header block, size pivot, and Size Breakdown."""
    return _generate_po_summary_excel_impl(df_pos, df_sizes=df_sizes, label_for=live_label)


def _generate_kl_format_excel_bytes(
    df_meta: "pd.DataFrame",
    df_sizes: "pd.DataFrame",
) -> bytes:
    """KL-format two-sheet summary (PO Detail + Summary) matching KL reference layout."""
    return _generate_kl_format_excel_impl(df_meta, df_sizes)


@st.cache_data(ttl=60, show_spinner=False)
def _build_master_display_df() -> pd.DataFrame:
    """Master PO rows (all clients, unfiltered) with the base64 Photo column.

    Cached with a short TTL: st.tabs re-renders this admin table on every
    rerun, and re-reading both full tables plus re-encoding every photo to
    base64 each time dominated the Contract History render cost.
    """
    po_store = get_store()
    se_store = get_sky_east_store()

    rows: list[dict] = []

    # ── Regular POs ───────────────────────────────────────────────────────────
    df_po = po_store.list_pos()
    if not df_po.empty:
        for _, r in df_po.iterrows():
            rows.append({
                "Company":    str(r.get("company", "") or ""),
                "Style":      str(r.get("style", "") or ""),
                "COO":        str(r.get("country_of_origin", "") or ""),
                "X-Fty Date": str(r.get("xport_date", "") or ""),
                "Total Units": int(r.get("total_units", 0) or 0),
                "_pid":       "",
            })

    # ── Sky East items — aggregate by (brand, style) ──────────────────────────
    df_se = se_store.list_items()
    if not df_se.empty:
        grp = df_se.groupby(["brand", "style"], sort=False).agg(
            total_units=("total_qty",   "sum"),
            xfty       =("ex_fty_date", "first"),
            picture_id =("picture_id",  "first"),
        ).reset_index()
        for _, r in grp.iterrows():
            rows.append({
                "Company":    str(r.get("brand", COMPANY_SKY_EAST) or COMPANY_SKY_EAST),
                "Style":      str(r.get("style", "") or ""),
                "COO":        "",
                "X-Fty Date": str(r.get("xfty", "") or ""),
                "Total Units": int(r.get("total_units", 0) or 0),
                "_pid":       str(r.get("picture_id", "") or ""),
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # ── Load photos from disk / session cache ─────────────────────────────────
    all_pids = [p for p in df["_pid"].unique() if p]
    pid_to_b64 = _build_thumbnail_data_urls(all_pids)

    display_df = df[["Company", "Style", "COO", "X-Fty Date", "Total Units"]].copy()
    photo_col  = df["_pid"].map(lambda p: pid_to_b64.get(p, None))
    display_df.insert(2, "Photo", photo_col)
    return display_df


def _show_master_po_table():
    """Admin-only interactive table: all POs across all clients, with style photos."""
    st.subheader(t("🗂 Master PO View — All Clients"))

    display_df = _build_master_display_df()
    if display_df.empty:
        st.info(t("No POs saved yet."))
        return

    st.caption(t("{n} row(s) across all clients").format(n=f"{len(display_df):,}"))

    col_cfg = {"Photo": st.column_config.ImageColumn("Photo", width="small")}

    # Optional company filter
    companies = sorted(display_df["Company"].dropna().unique().tolist())
    sel_cos = st.multiselect(t("Filter by Company:"), companies, key="master_co_filter")
    if sel_cos:
        mask = display_df["Company"].isin(sel_cos)
        display_df = display_df[mask].reset_index(drop=True)

    st.dataframe(display_df, width="stretch", hide_index=True, column_config=col_cfg)

    # Download master table as Excel.  Bytes are stashed in session state
    # (persisted_download convention) — a download_button nested inside the
    # build-button's `if` vanished on the next rerun, forcing two clicks and
    # losing the button after any widget interaction.
    if st.button(t("⬇ Download Master Table"), key="master_dl_btn"):
        from openpyxl import Workbook
        dl_df = display_df.drop(columns=["Photo"])
        wb = Workbook(); ws = wb.active; ws.title = "Master PO"
        _excel_header_row(ws, list(dl_df.columns))
        for ri, row in enumerate(dl_df.itertuples(index=False), start=2):
            for ci, val in enumerate(row, start=1):
                ws.cell(row=ri, column=ci, value=val)
        buf = io.BytesIO(); wb.save(buf)
        st.session_state["master_dl_bytes"] = buf.getvalue()
        st.session_state["master_dl_fname"] = "Master_PO_All_Clients.xlsx"
    persisted_download("master_dl", default_fname="Master_PO_All_Clients.xlsx",
                       fixed_mime=_XLSX_MIME, label="⬇ Save Excel")


def _show_downloads(outputs: dict, key_prefix: str = "dl"):
    st.divider()
    st.subheader(t("📥 Downloads"))


    row1 = st.columns(3)
    with row1[0]:
        st.download_button(
            label=t("📋 Buy Plan (生产计划单) (.xlsx)"),
            data=outputs["buyplan_bytes"],
            file_name=outputs["buyplan_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            type="primary",
            key=f"{key_prefix}_buyplan",
        )
        st.caption(t("One sheet per style + 汇总 summaries + UPC + fabric/artwork"))

    with row1[1]:
        st.download_button(
            label=t("🎨 Color Plan (.xlsx)"),
            data=outputs["color_plan_bytes"],
            file_name=outputs["color_plan_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            key=f"{key_prefix}_colorplan",
        )
        st.caption(t("Color × Size totals per style (one tab per style)"))

    with row1[2]:
        st.download_button(
            label=t("📋 PO Summary (.xlsx)"),
            data=outputs["po_summary_bytes"],
            file_name=outputs["po_summary_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            key=f"{key_prefix}_posummary",
        )
        st.caption(t("One row per Style+PO with sizes, Total, COO, X-Factory Date"))

    row2 = st.columns(3)
    with row2[0]:
        st.download_button(
            label=t("✅ Cross Check (.xlsx)"),
            data=outputs["cross_check_bytes"],
            file_name=outputs["cross_check_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            key=f"{key_prefix}_crosscheck",
        )
        st.caption(t("Verifies unit totals match across all three outputs"))

    with row2[1]:
        st.download_button(
            label=t("📁 Extracted Data (.zip)"),
            data=outputs["csvs_zip"],
            file_name="extracted_data.zip",
            mime=ZIP_MIME,
            use_container_width=True,
            key=f"{key_prefix}_csvzip",
        )
        st.caption(t("3 CSVs: by size/color, style-color totals, metadata"))

    if "masked_zip" in outputs:
        with row2[2]:
            st.download_button(
                label=t("🔒 Masked PDFs (.zip)"),
                data=outputs["masked_zip"],
                file_name="masked_pdfs.zip",
                mime=ZIP_MIME,
                use_container_width=True,
                key=f"{key_prefix}_masked",
            )
            st.caption(t("Price-redacted copies of all uploaded PDFs"))

    _show_requirements_download(outputs, key_prefix)


def _show_requirements_download(outputs: dict, key_prefix: str) -> None:
    """CPRS requirements document — generated automatically at upload time.

    Warnings render even when NO document was produced (e.g. every brand
    unknown to CPRS, or CPRS unreachable) — a silently missing download was
    the review's main finding."""
    for w in outputs.get("requirements_warns", []):
        st.warning(f"🧭 {w}")
    if not outputs.get("requirements_bytes"):
        return
    st.download_button(
        label="🧭 " + t("PO Requirements 要求文档 (.xlsx)"),
        data=outputs["requirements_bytes"],
        file_name="PO_Requirements.xlsx",
        mime=_XLSX_MIME,
        use_container_width=True,
        key=f"{key_prefix}_reqdoc",
    )
    st.caption(t("Client requirements per PO from the CPRS knowledge base — "
                 "labels, hangtags, packaging, carton marking, testing"))
    _show_requirements_api_section(outputs, key_prefix)


def _show_requirements_api_section(outputs: dict, key_prefix: str) -> None:
    """CPRS API document generation — the full doc suite (POST
    /export/doc-suite, CPRS ≥1.6.15) or a single requirements doc
    (/export/requirements-doc, ≥1.6.14), generated on demand.

    The app sends the decoded order context + PO register and saves what
    CPRS returns verbatim. The suite ZIP already contains BOTH variants
    (factory + internal) plus packing cards, the trim list and a manifest,
    so the variant picker only applies to the single-doc mode. One
    file/pack per order context; several become one download zip.
    """
    reqs = outputs.get("requirements_api_reqs") or []
    if not reqs:
        return
    with st.expander("🧭 " + t("API documents (CPRS)"), expanded=False):
        for w in outputs.get("requirements_api_warns", []):
            st.warning(w)
        mode = st.radio(
            t("What to generate"), ["suite", "single"], horizontal=True,
            format_func=lambda m: {
                "suite": t("📦 Full doc suite (factory + packing + trim list + internal)"),
                "single": t("Single requirements doc (HTML)"),
            }[m],
            key=f"{key_prefix}_api_mode",
        )
        if mode == "suite":
            st.caption(t("One ZIP per order context, built entirely by CPRS: "
                         "factory requirements (no prices), bilingual packing "
                         "cards with per-carton panels, the rules-driven trim "
                         "list (.xlsx) with order-quantity formulas, the "
                         "internal priced variant, and a manifest."))
        else:
            st.caption(t("Generated by CPRS itself — a self-contained bilingual "
                         "HTML pack, one per order context. The factory variant "
                         "strips prices; internal keeps everything."))
        variant = "factory"
        include_images = True
        if mode == "single":
            variant = st.radio(
                t("Variant"), ["factory", "internal"], horizontal=True,
                format_func=lambda v: {"factory": t("工厂 Factory (no prices)"),
                                       "internal": t("Internal (full)")}[v],
                key=f"{key_prefix}_api_variant",
            )
            include_images = st.checkbox(
                t("Embed manual images"), value=True,
                key=f"{key_prefix}_api_imgs",
                help=t("Base64-embeds requirement artwork (can add several MB)."),
            )
        notes_raw = st.text_area(
            t("Confirmed notes (one per line, optional)"),
            key=f"{key_prefix}_api_notes",
            placeholder=t("e.g. buyer confirmed grey cartons by email 07-20"),
            height=80,
        )

        # ── Optional buyer DSP file → dspTrims[] (CPRS ≥1.6.16) ─────────────
        # CPRS never reads mailboxes/files itself — structuring the DSP is
        # the caller's job. Parsed rows are previewed here and routed to the
        # matching order context at generation time.
        dsp_trims: list[dict] = []
        dsp_file = st.file_uploader(
            t("Buyer DSP file (optional, PDF or Excel) — makes the trim list DSP-first"),
            type=["pdf", "xlsx", "xlsm"], key=f"{key_prefix}_api_dsp",
            help=t("Per-trim rows (style, material, supplier, placement, "
                   "qty/pc…) are extracted and sent as dspTrims[] — DSP rows "
                   "become the trim list's A section with quantity formulas; "
                   "CPRS rule rows follow, marked 以 DSP 为准 where they differ."),
        )
        if dsp_file is not None:
            from po_extractor.parsers.dsp_trims import parse_dsp_trims
            _dsp_cache_key = f"{key_prefix}_api_dsp_cache"
            _sig = (dsp_file.name, dsp_file.size)
            _cached = st.session_state.get(_dsp_cache_key)
            if not _cached or _cached[0] != _sig:
                try:
                    parsed = parse_dsp_trims(dsp_file.getvalue())
                    _cached = (_sig, parsed, "")
                except Exception as exc:   # any parse failure → shown, not raised
                    _cached = (_sig, None, str(exc))
                st.session_state[_dsp_cache_key] = _cached
            _, _parsed, _err = _cached
            if _err:
                st.error(t("DSP file could not be read:") + f" {_err}")
            elif _parsed:
                dsp_trims = _parsed["trims"]
                for iss in _parsed["issues"][:8]:
                    st.warning(f"📎 {iss}")
                n_styles = len({tr.get("style") for tr in dsp_trims
                                if tr.get("style")})
                st.caption(
                    f"📎 {len(dsp_trims)} {t('trim row(s) from sheet')} "
                    f"“{_parsed['sheet']}”"
                    + (f" · {n_styles} {t('style(s)')}" if n_styles else ""))

        docs_key = f"{key_prefix}_api_docs"
        if st.button("🧭 " + t("Generate via CPRS API")
                     + f" ({len(reqs)} {t('document(s)')})",
                     key=f"{key_prefix}_api_go", type="primary"):
            from ui.stores import get_cprs_client
            cprs = get_cprs_client()
            needed = ("export_doc_suite" if mode == "suite"
                      else "export_requirements_doc")
            if cprs is None or not hasattr(cprs, needed):
                st.error(t("CPRS is not configured — set it up in Admin → "
                           "Settings first."))
                return
            notes = [ln.strip() for ln in (notes_raw or "").splitlines()
                     if ln.strip()]
            files, failed = [], []
            from po_extractor.ui_helpers.giii_requirements import (
                export_body_from_decoded,
            )
            with st.spinner(t("Asking CPRS to build the document(s)…")):
                for rq in reqs:
                    # Both export endpoints take the /evaluate context — let
                    # CPRS decode the raw PO itself (cached since upload) and
                    # pass its decoded context through verbatim.
                    ev = cprs.evaluate_po(dict(rq["raw"])) or {}
                    body = export_body_from_decoded(ev.get("decoded") or {})
                    if not body.get("clientId"):
                        failed.append(rq["label"])
                        continue
                    body["pos"] = rq["pos"]
                    if notes:
                        body["notes"] = notes
                    if dsp_trims:
                        from po_extractor.parsers.dsp_trims import (
                            trims_for_request,
                        )
                        routed = (dsp_trims if len(reqs) == 1
                                  else trims_for_request(dsp_trims, rq))
                        if routed:
                            body["dspTrims"] = routed
                    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_"
                                   for ch in rq["label"])[:60] or "doc"
                    if mode == "suite":
                        res = cprs.export_doc_suite(body)
                        if res and res.get("zip"):
                            files.append((f"DocSuite_{safe}.zip",
                                          res["zip"], res, ZIP_MIME))
                        else:
                            failed.append(rq["label"])
                    else:
                        body["variant"] = variant
                        body["includeImages"] = bool(include_images)
                        res = cprs.export_requirements_doc(body)
                        if res and res.get("html"):
                            files.append((f"Requirements_{safe}_{variant}.html",
                                          res["html"], res, HTML_MIME))
                        else:
                            failed.append(rq["label"])
            if failed:
                st.error(t("CPRS returned no document for:") + " "
                         + ", ".join(failed))
            if files:
                st.session_state[docs_key] = files
            elif not failed:
                st.info(t("Nothing to generate."))

        files = st.session_state.get(docs_key) or []
        if files:
            # The suite endpoint reports its counts inside manifest.json, not
            # response headers — show counts only when the API sent them.
            parts = []
            for f in files:
                meta = f[2]
                if meta.get("card_count"):
                    parts.append(f"{f[0]} — {meta['card_count']} {t('card(s)')}, "
                                 f"{meta.get('image_count') or '0'} {t('image(s)')}")
                else:
                    parts.append(f[0])
            st.caption(" · ".join(parts))
            if len(files) == 1:
                fname, data, _meta, mime = files[0]
                st.download_button(
                    "⬇️ " + fname, data=data, file_name=fname,
                    mime=mime, use_container_width=True,
                    key=f"{key_prefix}_api_dl",
                )
            else:
                import io as _io
                import zipfile as _zipfile
                buf = _io.BytesIO()
                with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
                    for fname, data, _meta, _mime in files:
                        zf.writestr(fname, data)
                st.download_button(
                    "⬇️ " + t("Requirements pack (.zip)")
                    + f" — {len(files)} {t('file(s)')}",
                    data=buf.getvalue(),
                    file_name="CPRS_Documents.zip",
                    mime=ZIP_MIME, use_container_width=True,
                    key=f"{key_prefix}_api_dl",
                )


def _show_excel_downloads(outputs: dict):
    st.divider()
    st.subheader(t("📥 Downloads"))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            label=t("📊 Zalando Buy Plan (.xlsx)"),
            data=outputs["buyplan_bytes"],
            file_name=outputs["buyplan_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            type="primary",
            key="excel_dl_buyplan",
        )
        st.caption(t("One sheet per style — fabric, photos, PO rows, size grid"))

    with col2:
        if outputs.get("template_p_zip"):
            st.download_button(
                label=t("🎨 Template_P — {n} workbook(s) (.zip)").format(n=outputs.get('template_p_count', 0)),
                data=outputs["template_p_zip"],
                file_name="Zalando_面料_by_Fabric.zip",
                mime=ZIP_MIME,
                use_container_width=True,
                key="excel_dl_templatep",
            )
            st.caption(t("Color × Size pivot grouped by Fabric1_Code"))

    if "repeat_csv" in outputs:
        with col3:
            st.download_button(
                label=t("↩ Repeat Orders Report ({n} group(s))").format(n=outputs['repeat_count']),
                data=outputs["repeat_csv"],
                file_name="repeat_orders.csv",
                mime=CSV_MIME,
                use_container_width=True,
                key="excel_dl_repeats",
            )
            st.caption(t("Styles with same color appearing in multiple POs"))

    if "masked_zip" in outputs:
        st.download_button(
            label=t("🔒 Download Masked Files (.zip)"),
            data=outputs["masked_zip"],
            file_name="zalando_masked.zip",
            mime=ZIP_MIME,
            use_container_width=True,
            key="excel_dl_masked",
        )

    if outputs.get("conflict_count", 0):
        st.warning(t(
            "{n} quantity conflict(s) found across files — see processing log "
            "for details."
        ).format(n=outputs['conflict_count']))


def _show_smart_downloads(outputs: dict):
    st.divider()
    st.subheader(t("📥 Downloads"))
    groups: dict = outputs.get("groups", {})

    if not groups:
        st.warning(t("No output was generated."))
        return

    for company, grp in groups.items():
        pipeline = grp.get("pipeline", "unknown")
        st.markdown(f"#### {company}")

        if pipeline == "pdf":
            cols = st.columns(3)
            for i, (label, key, cap) in enumerate([
                ("📋 Buy Plan (生产计划单)", "buyplan",
                 "One sheet per style + 汇总 summaries + UPC + fabric/artwork"),
                ("🎨 Color Plan",  "color_plan",  "Color × Size per style"),
                ("📋 PO Summary",  "po_summary",  "One row per Style+PO"),
            ]):
                with cols[i % 3]:
                    st.download_button(
                        label=f"{label} (.xlsx)",
                        data=grp[f"{key}_bytes"],
                        file_name=grp[f"{key}_name"],
                        mime=_XLSX_MIME,
                        use_container_width=True,
                        key=f"dl_{company}_{key}",
                    )
                    st.caption(cap)
            cols2 = st.columns(3)
            with cols2[0]:
                st.download_button(
                    t("✅ Cross Check (.xlsx)"), grp["cross_check_bytes"],
                    file_name=grp["cross_check_name"], mime=_XLSX_MIME,
                    use_container_width=True, key=f"dl_{company}_cc",
                )
            with cols2[1]:
                st.download_button(
                    t("📁 Extracted Data (.zip)"), grp["csvs_zip"],
                    file_name=f"{company}_data.zip", mime=ZIP_MIME,
                    use_container_width=True, key=f"dl_{company}_csv",
                )
            if "masked_zip" in grp:
                with cols2[2]:
                    st.download_button(
                        t("🔒 Masked PDFs (.zip)"), grp["masked_zip"],
                        file_name=f"{company}_masked.zip", mime=ZIP_MIME,
                        use_container_width=True, key=f"dl_{company}_mask",
                    )
            elif grp.get("mask_failed"):
                st.error(
                    "🔒 Price masking produced no files — no masked download. "
                    + " · ".join(grp["mask_failed"][:5])
                )
            _show_requirements_download(grp, key_prefix=f"dl_{company}")

        elif pipeline == "excel":
            cols = st.columns(3)
            with cols[0]:
                st.download_button(
                    t("📊 Buy Plan (.xlsx)"), grp["buyplan_bytes"],
                    file_name=grp["buyplan_name"], mime=_XLSX_MIME,
                    use_container_width=True, type="primary",
                    key=f"dl_{company}_bp",
                )
                st.caption(t("Fabric, photos, PO rows, size grid per style"))
            with cols[1]:
                st.download_button(
                    t("🎨 Template_P — {n} workbook(s) (.zip)").format(n=grp['template_p_count']),
                    grp["template_p_zip"],
                    file_name=f"{company}_面料_workbooks.zip", mime=ZIP_MIME,
                    use_container_width=True,
                    key=f"dl_{company}_tp",
                )
                st.caption(t("Color × Size pivot grouped by Fabric code"))
            repeats = grp.get("repeat_orders", {})
            if repeats:
                import csv as _csv
                rows = [{"Style": s, "PO Number": p}
                        for s, pos in repeats.items() for p in pos]
                rbuf = io.StringIO()
                w = _csv.DictWriter(rbuf, fieldnames=["Style", "PO Number"])
                w.writeheader(); w.writerows(rows)
                with cols[2]:
                    st.download_button(
                        t("↩ Repeat Orders ({n} group(s))").format(n=len(repeats)),
                        rbuf.getvalue().encode(),
                        file_name=f"{company}_repeat_orders.csv",
                        mime=CSV_MIME, use_container_width=True,
                        key=f"dl_{company}_rep",
                    )
                    st.caption(t("Styles appearing in multiple POs"))
            if "masked_zip" in grp:
                st.download_button(
                    t("🔒 Masked Files (.zip)"), grp["masked_zip"],
                    file_name=f"{company}_masked.zip", mime=ZIP_MIME,
                    use_container_width=True,
                    key=f"dl_{company}_mask",
                )
            if grp.get("conflicts"):
                st.warning(t("{n} quantity conflict(s) — see log.").format(n=len(grp['conflicts'])))
