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
)
from ui.shared import build_image_cache_for_ids as _build_image_cache_for_ids
from auth.companies import COMPANY_SKY_EAST
from ui.stores import get_store, get_sky_east_store
from ui.giii._shared import _XLSX_MIME, live_label


def _excel_header_row(ws, cols, fill_hex="4472C4"):
    _write_excel_header_row(ws, cols, fill_hex)


def _generate_color_plan_excel(po_numbers: list, store) -> bytes:
    """Pivot size rows into a color plan: one row per (PO, Style, Color), sizes as columns."""
    df = store.load_size_rows(po_numbers)
    return _generate_color_plan_excel_impl(df)


def _generate_po_summary_excel(df_pos: "pd.DataFrame") -> bytes:
    """One-row-per-PO summary with key header fields."""
    return _generate_po_summary_excel_impl(df_pos, label_for=live_label)


def _show_master_po_table():
    """Admin-only interactive table: all POs across all clients, with style photos."""
    st.subheader("🗂 Master PO View — All Clients")

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
        st.info("No POs saved yet.")
        return

    df = pd.DataFrame(rows)
    st.caption(f"{len(df):,} row(s) across all clients")

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

    col_cfg = {"Photo": st.column_config.ImageColumn("Photo", width="small")}

    # Optional company filter
    companies = sorted(df["Company"].dropna().unique().tolist())
    sel_cos = st.multiselect("Filter by Company:", companies, key="master_co_filter")
    if sel_cos:
        mask = display_df["Company"].isin(sel_cos)
        display_df = display_df[mask].reset_index(drop=True)

    st.dataframe(display_df, width="stretch", hide_index=True, column_config=col_cfg)

    # Download master table as Excel
    if st.button("⬇ Download Master Table", key="master_dl_btn"):
        from openpyxl import Workbook
        dl_df = display_df.drop(columns=["Photo"])
        wb = Workbook(); ws = wb.active; ws.title = "Master PO"
        _excel_header_row(ws, list(dl_df.columns))
        for ri, row in enumerate(dl_df.itertuples(index=False), start=2):
            for ci, val in enumerate(row, start=1):
                ws.cell(row=ri, column=ci, value=val)
        buf = io.BytesIO(); wb.save(buf)
        st.download_button(
            "⬇ Save Excel", data=buf.getvalue(),
            file_name="Master_PO_All_Clients.xlsx",
            mime=_XLSX_MIME,
            key="master_dl_save",
        )


def _show_downloads(outputs: dict, key_prefix: str = "dl"):
    st.divider()
    st.subheader("📥 Downloads")


    row1 = st.columns(3)
    with row1[0]:
        st.download_button(
            label="📊 Buy Plan (.xlsx)",
            data=outputs["buyplan_bytes"],
            file_name=outputs["buyplan_name"],
            mime=_XLSX_MIME,
            use_container_width=True,
            type="primary",
            key=f"{key_prefix}_buyplan",
        )
        st.caption("PO × Color × Size pivot per style, with 出厂日期")

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
                ("📊 Buy Plan",    "buyplan",     "Style × PO × Color, size grid"),
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
