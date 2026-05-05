"""Cross-company Order Summary tab."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from auth.companies import COMPANY_GIII, COMPANY_SKY_EAST
from ui.shared import _th, _tr
from ui.stores import get_store, get_sky_east_store


def show_summary_tab(user_cos: list[str], admin_mode: bool) -> None:
    """Cross-company order summary, filtered by user permissions."""
    st.subheader("📊 Order Summary")
    st.caption("Aggregated view of all orders across clients, filtered to your permitted companies.")

    # Permission helpers
    # admin or empty user_cos = unrestricted
    unrestricted = admin_mode or not user_cos

    can_see_giii    = unrestricted or bool(user_cos)          # any company assigned includes GIII-type data
    can_see_zalando = unrestricted or COMPANY_SKY_EAST in [c.strip() for c in user_cos]

    # Load data
    giii_df = pd.DataFrame()
    se_df   = pd.DataFrame()

    if can_see_giii:
        giii_df = get_store().list_pos(companies=user_cos if user_cos else None)

    if can_see_zalando:
        se_items = get_sky_east_store().list_items()
        if not se_items.empty:
            se_df = se_items

    # Build unified summary rows (one row per Company)
    # Columns: Company | POs | Styles | Units | Latest Ex-Fty | Factory | COO | Source
    summary_rows = []

    if can_see_giii and not giii_df.empty:
        for company, grp in giii_df.groupby("company", dropna=False):
            summary_rows.append({
                "Company":       company or "—",
                "Source":        COMPANY_GIII,
                "POs":           grp["po_number"].nunique(),
                "Styles":        grp["style"].nunique() if "style" in grp.columns else 0,
                "Units":         int(grp["total_units"].sum()) if "total_units" in grp.columns else 0,
                "Factory":       grp["factory"].mode()[0] if "factory" in grp.columns and not grp["factory"].dropna().empty else "",
                "COO":           grp["country_of_origin"].mode()[0] if "country_of_origin" in grp.columns and not grp["country_of_origin"].dropna().empty else "",
                "Latest Ex-Fty": grp["xport_date"].max() if "xport_date" in grp.columns else "",
            })

    if can_see_zalando and not se_df.empty:
        summary_rows.append({
            "Company":       COMPANY_SKY_EAST,
            "Source":        COMPANY_SKY_EAST,
            "POs":           se_df["zalando_po"].nunique() if "zalando_po" in se_df.columns else 0,
            "Styles":        se_df["style"].nunique() if "style" in se_df.columns else 0,
            "Units":         int(se_df["total_qty"].sum()) if "total_qty" in se_df.columns else 0,
            "Factory":       "",
            "COO":           "",
            "Latest Ex-Fty": se_df["ex_fty_date"].max() if "ex_fty_date" in se_df.columns else "",
        })

    # Top metrics
    total_pos    = sum(r["POs"]    for r in summary_rows)
    total_styles = sum(r["Styles"] for r in summary_rows)
    total_units  = sum(r["Units"]  for r in summary_rows)
    total_cos    = len(summary_rows)

    mc = st.columns(4)
    mc[0].metric(_th("Companies"),    f"{total_cos:,}")
    mc[1].metric(_th("Total POs"),    f"{total_pos:,}")
    mc[2].metric(_th("Total Styles"), f"{total_styles:,}")
    mc[3].metric(_th("Total Units"),  f"{total_units:,}")

    st.divider()

    # Unified summary table
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows,
                                  columns=["Company", "Source", "POs", "Styles", "Units",
                                           "Factory", "COO", "Latest Ex-Fty"])
        _sum_rename = {c: _th(c) for c in summary_df.columns}
        st.dataframe(summary_df.rename(columns=_sum_rename),
                     use_container_width=True, hide_index=True)
    else:
        st.info("No order data available for your permitted companies.")

    st.divider()

    # ── Detail expanders with user-configurable column selection ─────────────
    show_cols: list[str] = []
    labels: dict = {}
    se_show: list[str] = []
    se_labels: dict = {}

    if can_see_giii and not giii_df.empty:
        with st.expander("🔍 GIII — full PO list"):
            # Virtual "pc_no" column — mirrors po_number for users whose
            # external workflow refers to it as "PC No." (Purchase Contract No.).
            if "po_number" in giii_df.columns and "pc_no" not in giii_df.columns:
                giii_df["pc_no"] = giii_df["po_number"]

            # All selectable columns (key → human label)
            giii_field_labels: dict = {
                "po_number":         "PO No.",
                "pc_no":             "PC No.",
                "company":           "Company",
                "style":              "Style",
                "factory":           "Factory",
                "country_of_origin": "COO",
                "xport_date":        "Ex-Fty",
                "issue_date":        "Issue Date",
                "version":           "Version",
                "division_code":     "Division Code",
                "division_name":     "Division Name",
                "total_units":       "Units",
            }
            giii_avail = [k for k in giii_field_labels if k in giii_df.columns]
            giii_default = [k for k in
                            ["po_number", "pc_no", "company", "style", "factory",
                             "country_of_origin", "xport_date", "total_units"]
                            if k in giii_avail]

            picked = st.multiselect(
                "Columns to display",
                options=giii_avail,
                default=giii_default,
                format_func=lambda k: giii_field_labels.get(k, k),
                key="sum_giii_cols",
            )
            show_cols = picked or giii_default
            labels = _tr({k: giii_field_labels[k] for k in show_cols})
            st.dataframe(giii_df[show_cols].rename(columns=labels),
                         use_container_width=True, hide_index=True)

    if can_see_zalando and not se_df.empty:
        with st.expander("🔍 Sky East — full item list"):
            # Virtual "company" column — Sky East is the source by definition.
            if "company" not in se_df.columns:
                se_df["company"] = COMPANY_SKY_EAST

            se_field_labels: dict = {
                "pc_no":       "PC No.",
                "zalando_po":  "PO No.",
                "company":     "Company",
                "style":       "Style",
                "brand":       "Brand",
                "color_name":  "Color",
                "config_sku":  "Config SKU",
                "fabric_item_no": "Fabric Code",
                "total_qty":   "Units",
                "ex_fty_date": "Ex-Fty",
            }
            se_avail = [k for k in se_field_labels if k in se_df.columns]
            se_default = [k for k in
                          ["pc_no", "zalando_po", "company", "style", "brand",
                           "color_name", "total_qty", "ex_fty_date"]
                          if k in se_avail]

            se_picked = st.multiselect(
                "Columns to display",
                options=se_avail,
                default=se_default,
                format_func=lambda k: se_field_labels.get(k, k),
                key="sum_se_cols",
            )
            se_show = se_picked or se_default
            se_labels = _tr({k: se_field_labels[k] for k in se_show})
            st.dataframe(se_df[se_show].rename(columns=se_labels),
                         use_container_width=True, hide_index=True)

    # Download
    if summary_rows:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as wr:
            summary_df.to_excel(wr, sheet_name="Summary", index=False)
            if can_see_giii and not giii_df.empty and show_cols:
                giii_df[show_cols].rename(columns=labels).to_excel(
                    wr, sheet_name="GIII POs", index=False)
            if can_see_zalando and not se_df.empty and se_show:
                se_df[se_show].rename(columns=se_labels).to_excel(
                    wr, sheet_name="Sky East Items", index=False)
        st.download_button("⬇️ Download Full Summary", buf.getvalue(),
                           "order_summary.xlsx", key="sum_dl_all")

    if not can_see_giii and not can_see_zalando:
        st.warning("You don't have permission to view any company's orders. Contact an admin.")
