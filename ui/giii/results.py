"""GIII results display and download panels."""
from __future__ import annotations
import base64
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
from ui.shared import build_image_cache_for_ids as _build_image_cache_for_ids
from ui.shared import persisted_download
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
    loaded   = _build_image_cache_for_ids(all_pids)
    pid_to_b64 = {
        pid: f"data:image/png;base64,{base64.b64encode(b).decode()}"
        for pid, b in loaded.items()
    }

    display_df = df[["Company", "Style", "COO", "X-Fty Date", "Total Units"]].copy()
    photo_col  = df["_pid"].map(lambda p: pid_to_b64.get(p, None))
    display_df.insert(2, "Photo", photo_col)
    return display_df


def _show_master_po_table():
    """Admin-only interactive table: all POs across all clients, with style photos."""
    st.subheader("🗂 Master PO View — All Clients")

    display_df = _build_master_display_df()
    if display_df.empty:
        st.info("No POs saved yet.")
        return

    st.caption(f"{len(display_df):,} row(s) across all clients")

    col_cfg = {"Photo": st.column_config.ImageColumn("Photo", width="small")}

    # Optional company filter
    companies = sorted(display_df["Company"].dropna().unique().tolist())
    sel_cos = st.multiselect("Filter by Company:", companies, key="master_co_filter")
    if sel_cos:
        mask = display_df["Company"].isin(sel_cos)
        display_df = display_df[mask].reset_index(drop=True)

    st.dataframe(display_df, width="stretch", hide_index=True, column_config=col_cfg)

    # Download master table as Excel.  Bytes are stashed in session state
    # (persisted_download convention) — a download_button nested inside the
    # build-button's `if` vanished on the next rerun, forcing two clicks and
    # losing the button after any widget interaction.
    if st.button("⬇ Download Master Table", key="master_dl_btn"):
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
    st.subheader("📥 Downloads")


    row1 = st.columns(3)
    with row1[0]:
        st.download_button(
            label="📋 Buy Plan (生产计划单) (.xlsx)",
            data=outputs["buyplan_bytes"],
            file_name=outputs["buyplan_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            type="primary",
            key=f"{key_prefix}_buyplan",
        )
        st.caption("One sheet per style + 汇总 summaries + UPC + fabric/artwork")

    with row1[1]:
        st.download_button(
            label="🎨 Color Plan (.xlsx)",
            data=outputs["color_plan_bytes"],
            file_name=outputs["color_plan_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            key=f"{key_prefix}_colorplan",
        )
        st.caption("Color × Size totals per style (one tab per style)")

    with row1[2]:
        st.download_button(
            label="📋 PO Summary (.xlsx)",
            data=outputs["po_summary_bytes"],
            file_name=outputs["po_summary_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            key=f"{key_prefix}_posummary",
        )
        st.caption("One row per Style+PO with sizes, Total, COO, X-Factory Date")

    row2 = st.columns(3)
    with row2[0]:
        st.download_button(
            label="✅ Cross Check (.xlsx)",
            data=outputs["cross_check_bytes"],
            file_name=outputs["cross_check_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            key=f"{key_prefix}_crosscheck",
        )
        st.caption("Verifies unit totals match across all three outputs")

    with row2[1]:
        st.download_button(
            label="📁 Extracted Data (.zip)",
            data=outputs["csvs_zip"],
            file_name="extracted_data.zip",
            mime="application/zip",
            use_container_width=True,
            key=f"{key_prefix}_csvzip",
        )
        st.caption("3 CSVs: by size/color, style-color totals, metadata")

    if "masked_zip" in outputs:
        with row2[2]:
            st.download_button(
                label="🔒 Masked PDFs (.zip)",
                data=outputs["masked_zip"],
                file_name="masked_pdfs.zip",
                mime="application/zip",
                use_container_width=True,
                key=f"{key_prefix}_masked",
            )
            st.caption("Price-redacted copies of all uploaded PDFs")

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
    """CPRS API requirements document (POST /export/requirements-doc,
    CPRS ≥1.6.14) — generated on demand so the user picks the variant first.

    The app sends the stored order context + PO register and saves the
    returned HTML verbatim; the variant is the only policy and it is the
    API's, not ours: 工厂 factory strips pricing/fob/amount, internal keeps
    everything. One file per order context; several become a zip.
    """
    reqs = outputs.get("requirements_api_reqs") or []
    if not reqs:
        return
    with st.expander("🧭 " + t("API requirements document (HTML)"),
                     expanded=False):
        for w in outputs.get("requirements_api_warns", []):
            st.warning(w)
        st.caption(t("Generated by CPRS itself — a self-contained bilingual "
                     "HTML pack, one per order context. The factory variant "
                     "strips prices; internal keeps everything."))
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

        docs_key = f"{key_prefix}_api_docs"
        if st.button("🧭 " + t("Generate via CPRS API")
                     + f" ({len(reqs)} {t('document(s)')})",
                     key=f"{key_prefix}_api_go", type="primary"):
            from ui.stores import get_cprs_client
            cprs = get_cprs_client()
            if cprs is None or not hasattr(cprs, "export_requirements_doc"):
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
                    # The export endpoint takes the /evaluate context — let
                    # CPRS decode the raw PO itself (cached since upload) and
                    # pass its decoded context through verbatim.
                    ev = cprs.evaluate_po(dict(rq["raw"])) or {}
                    body = export_body_from_decoded(ev.get("decoded") or {})
                    if not body.get("clientId"):
                        failed.append(rq["label"])
                        continue
                    body["pos"] = rq["pos"]
                    body["variant"] = variant
                    body["includeImages"] = bool(include_images)
                    if notes:
                        body["notes"] = notes
                    res = cprs.export_requirements_doc(body)
                    if res and res.get("html"):
                        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_"
                                       for ch in rq["label"])[:60] or "doc"
                        files.append((f"Requirements_{safe}_{variant}.html",
                                      res["html"], res))
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
            counts = " · ".join(
                f"{f[0]} — {f[2].get('card_count') or '?'} {t('card(s)')}, "
                f"{f[2].get('image_count') or '0'} {t('image(s)')}"
                for f in files)
            st.caption(counts)
            if len(files) == 1:
                fname, data, _meta = files[0]
                st.download_button(
                    "⬇️ " + fname, data=data, file_name=fname,
                    mime="text/html", use_container_width=True,
                    key=f"{key_prefix}_api_dl",
                )
            else:
                import io as _io
                import zipfile as _zipfile
                buf = _io.BytesIO()
                with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
                    for fname, data, _meta in files:
                        zf.writestr(fname, data)
                st.download_button(
                    "⬇️ " + t("Requirements pack (.zip)")
                    + f" — {len(files)} {t('file(s)')}",
                    data=buf.getvalue(),
                    file_name=f"Requirements_API_{variant}.zip",
                    mime="application/zip", use_container_width=True,
                    key=f"{key_prefix}_api_dl",
                )


def _show_excel_downloads(outputs: dict):
    st.divider()
    st.subheader("📥 Downloads")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            label="📊 Zalando Buy Plan (.xlsx)",
            data=outputs["buyplan_bytes"],
            file_name=outputs["buyplan_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            type="primary",
            key="excel_dl_buyplan",
        )
        st.caption("One sheet per style — fabric, photos, PO rows, size grid")

    with col2:
        st.download_button(
            label=f"🎨 Template_P — {outputs['template_p_count']} workbook(s) (.zip)",
            data=outputs["template_p_zip"],
            file_name="Zalando_面料_by_Fabric.zip",
            mime="application/zip",
            use_container_width=True,
            key="excel_dl_templatep",
        )
        st.caption("Color × Size pivot grouped by Fabric1_Code")

    if "repeat_csv" in outputs:
        with col3:
            st.download_button(
                label=f"↩ Repeat Orders Report ({outputs['repeat_count']} group(s))",
                data=outputs["repeat_csv"],
                file_name="repeat_orders.csv",
                mime="text/csv",
                use_container_width=True,
                key="excel_dl_repeats",
            )
            st.caption("Styles with same color appearing in multiple POs")

    if "masked_zip" in outputs:
        st.download_button(
            label="🔒 Download Masked Files (.zip)",
            data=outputs["masked_zip"],
            file_name="zalando_masked.zip",
            mime="application/zip",
            use_container_width=True,
            key="excel_dl_masked",
        )

    if outputs.get("conflict_count", 0):
        st.warning(
            f"{outputs['conflict_count']} quantity conflict(s) found across files — "
            "see processing log for details."
        )


def _show_smart_downloads(outputs: dict):
    st.divider()
    st.subheader("📥 Downloads")
    groups: dict = outputs.get("groups", {})

    if not groups:
        st.warning("No output was generated.")
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
                    "✅ Cross Check (.xlsx)", grp["cross_check_bytes"],
                    file_name=grp["cross_check_name"], mime=_XLSX_MIME,
                    use_container_width=True, key=f"dl_{company}_cc",
                )
            with cols2[1]:
                st.download_button(
                    "📁 Extracted Data (.zip)", grp["csvs_zip"],
                    file_name=f"{company}_data.zip", mime="application/zip",
                    use_container_width=True, key=f"dl_{company}_csv",
                )
            if "masked_zip" in grp:
                with cols2[2]:
                    st.download_button(
                        "🔒 Masked PDFs (.zip)", grp["masked_zip"],
                        file_name=f"{company}_masked.zip", mime="application/zip",
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
                    "📊 Buy Plan (.xlsx)", grp["buyplan_bytes"],
                    file_name=grp["buyplan_name"], mime=_XLSX_MIME,
                    use_container_width=True, type="primary",
                    key=f"dl_{company}_bp",
                )
                st.caption("Fabric, photos, PO rows, size grid per style")
            with cols[1]:
                st.download_button(
                    f"🎨 Template_P — {grp['template_p_count']} workbook(s) (.zip)",
                    grp["template_p_zip"],
                    file_name=f"{company}_面料_workbooks.zip", mime="application/zip",
                    use_container_width=True,
                    key=f"dl_{company}_tp",
                )
                st.caption("Color × Size pivot grouped by Fabric code")
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
                        f"↩ Repeat Orders ({len(repeats)} group(s))",
                        rbuf.getvalue().encode(),
                        file_name=f"{company}_repeat_orders.csv",
                        mime="text/csv", use_container_width=True,
                        key=f"dl_{company}_rep",
                    )
                    st.caption("Styles appearing in multiple POs")
            if "masked_zip" in grp:
                st.download_button(
                    "🔒 Masked Files (.zip)", grp["masked_zip"],
                    file_name=f"{company}_masked.zip", mime="application/zip",
                    use_container_width=True,
                    key=f"dl_{company}_mask",
                )
            if grp.get("conflicts"):
                st.warning(f"{len(grp['conflicts'])} quantity conflict(s) — see log.")
