"""GIII 'Missing Fields' tab — editable grid for POs missing factory / export date."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.stores import get_store


def _show_giii_missing_fields_section(missing_df: pd.DataFrame) -> None:
    """Show GIII POs that are missing factory or export date."""
    st.subheader("✏️ POs with Missing Fields")

    if missing_df.empty:
        st.success("✅ All stored POs are complete — no missing fields.")
        return

    st.caption(
        f"**{len(missing_df)}** PO(s) are missing factory name or export date. "
        "These fields are extracted from the source PDF. "
        "If they remain blank after re-processing, the source file may not contain them."
    )

    disp_cols = [c for c in
                 ["po_number", "company", "style", "factory",
                  "xport_date", "issue_date", "total_units", "file_name"]
                 if c in missing_df.columns]

    col_rename = {
        "po_number": "PO Number", "company": "Company", "style": "Style",
        "factory": "Factory", "xport_date": "Export Date",
        "issue_date": "Issue Date", "total_units": "Total Units",
        "file_name": "Source File",
    }
    edit_df = missing_df[disp_cols].copy().rename(columns=col_rename)

    # editable columns: Factory + Export Date; rest read-only
    editable = ["Factory", "Export Date"]
    disabled = [c for c in edit_df.columns if c not in editable]

    edited = st.data_editor(
        edit_df,
        width="stretch",
        hide_index=True,
        disabled=disabled,
        column_config={
            "Factory":     st.column_config.TextColumn("Factory"),
            "Export Date": st.column_config.TextColumn("Export Date", help="YYYY-MM-DD"),
        },
        key="giii_missing_editor",
    )

    if st.button("💾 Save Changes", key="giii_missing_save", type="primary"):
        store = get_store()
        rev   = {v: k for k, v in col_rename.items()}
        saved_df = edited.rename(columns=rev)
        updated  = 0
        with store._conn() as conn:
            for _, row in saved_df.iterrows():
                po = str(row.get("po_number", "") or "").strip()
                if not po:
                    continue
                factory    = str(row.get("factory", "")    or "").strip()
                xport_date = str(row.get("xport_date", "") or "").strip()
                conn.execute(
                    "UPDATE po_metadata SET factory=?, xport_date=? WHERE po_number=?",
                    (factory or None, xport_date or None, po),
                )
                updated += 1
        if updated:
            st.success(f"✅ Updated {updated} PO(s).")
            st.rerun()
        else:
            st.warning("No rows updated.")
