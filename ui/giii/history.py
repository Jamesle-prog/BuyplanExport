"""GIII PO History tab — re-export and delete sections."""
from __future__ import annotations

import streamlit as st

from auth.users import get_user_companies, is_admin
from ui.session_keys import SK
from ui.stores import get_store
from ui.giii._shared import _XLSX_MIME, live_label
from ui.giii.extraction import _run_from_history, _create_buyplan_bytes
from ui.giii.results import (
    _show_downloads,
    _generate_color_plan_excel,
    _generate_po_summary_excel,
    _show_master_po_table,
)


def _show_history(exc_df=None):
    store = get_store()
    user_cos = get_user_companies(st.session_state.username)
    df = store.list_pos(companies=user_cos if user_cos else None)

    # ── Summary metrics ───────────────────────────────────────────────────────
    total_pos    = len(df)
    total_units  = int(df["total_units"].sum()) if not df.empty and "total_units" in df.columns else 0
    companies    = df["company"].nunique() if not df.empty and "company" in df.columns else 0
    pending_exc  = (len(exc_df[exc_df["status"] == "pending"])
                    if exc_df is not None and not exc_df.empty and "status" in exc_df.columns else 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total POs",    f"{total_pos:,}")
    m2.metric("Total Units",  f"{total_units:,}")
    m3.metric("Companies",    companies)
    m4.metric("Pending Exceptions", pending_exc, delta=None,
              delta_color="inverse" if pending_exc else "off")

    if df.empty:
        st.info("No POs stored yet. Extract some PDFs and they will appear here automatically.")
        return

    st.divider()

    # ── PO table — essential cols by default, expandable ─────────────────────
    essential_cols = ["company", "po_number", "style", "factory",
                      "country_of_origin", "xport_date", "total_units"]
    all_cols = ["company", "po_number", "style", "factory", "country_of_origin",
                "xport_date", "issue_date", "version", "division_code", "division_name",
                "total_units", "extracted_at", "file_name"]
    rename_map = {
        "company":           live_label("company",           "Company"),
        "po_number":         live_label("po_number",         "PO No."),
        "style":             live_label("style",             "Style No."),
        "factory":           live_label("factory",           "Factory"),
        "country_of_origin": live_label("country_of_origin","COO"),
        "xport_date":        live_label("ex_fty_date",       "Ex-Fty"),
        "issue_date":        "Issue Date",
        "version":           "Version",
        "division_code":     "Div Code",
        "division_name":     live_label("division", "Division"),
        "total_units":       live_label("total_qty", "Total Qty"),
        "extracted_at":      live_label("extracted_at", "Extracted At"),
        "file_name":         live_label("source_file", "Source File"),
    }
    show_all = st.toggle("Show all columns", value=False, key="hist_show_all")
    active_cols = all_cols if show_all else essential_cols
    show_df = df[[c for c in active_cols if c in df.columns]].rename(columns=rename_map)
    st.dataframe(show_df, width="stretch", hide_index=True)

    # ── Version history ───────────────────────────────────────────────────────
    with st.expander("📜 View version history for a PO"):
        inspect_po = st.selectbox("Select PO:", [""] + df["po_number"].tolist(),
                                  key="inspect_po")
        if inspect_po:
            hist = store.list_history(inspect_po)
            if hist.empty:
                st.info("No previous versions — this PO has never been updated.")
            else:
                st.caption(f"{len(hist)} archived version(s) for {inspect_po}")
                st.dataframe(hist, width="stretch", hide_index=True)

    st.divider()

    # ── Re-export ─────────────────────────────────────────────────────────────
    st.markdown("**Re-export selected POs**")
    st.caption("Select PO numbers to regenerate all Excel outputs from stored data.")
    po_options = df["po_number"].tolist()
    selected = st.multiselect(
        "Choose POs to include:", po_options,
        placeholder="Select one or more PO numbers…",
    )
    col_a, col_b, _col_pad = st.columns([1, 1, 2])
    with col_a:
        if st.button("▶  Generate from History", type="primary",
                     disabled=not selected, use_container_width=True):
            st.session_state.pop("history_bp_bytes", None)
            _run_from_history(selected)
    with col_b:
        if st.button("📋  Buy Plan Only", disabled=not selected,
                     use_container_width=True, key="giii_bp_only_btn"):
            st.session_state.pop("history_results", None)
            with st.spinner("Generating buy plan…"):
                bp_bytes = _create_buyplan_bytes(selected)
            if bp_bytes:
                st.session_state[SK.HISTORY_BP_BYTES] = bp_bytes
            else:
                st.warning("No size data found for selected POs.")

    if st.session_state.get(SK.HISTORY_RESULTS):
        _show_downloads(st.session_state.history_results, key_prefix="history")
    elif st.session_state.get(SK.HISTORY_BP_BYTES):
        st.divider()
        st.download_button(
            "⬇️ Download Buy Plan (.xlsx)",
            data=st.session_state[SK.HISTORY_BP_BYTES],
            file_name="buy_plan.xlsx",
            mime=_XLSX_MIME,
            key="history_bp_dl",
        )

    st.divider()

    # ── Reports ───────────────────────────────────────────────────────────────
    st.markdown("**📊 Reports**")
    st.caption("Generate standard output reports from all saved POs.")
    rpt_c1, rpt_c2 = st.columns(2)

    with rpt_c1:
        st.markdown("**Color Plan**")
        st.caption("Style × Color × Size breakdown — one row per color.")
        if st.button("Generate Color Plan Excel", key="rpt_color_plan"):
            all_pos = df["po_number"].tolist()
            with st.spinner("Building color plan…"):
                xlsx_bytes = _generate_color_plan_excel(all_pos, store)
            if xlsx_bytes:
                st.download_button(
                    "⬇ Download Color Plan",
                    data=xlsx_bytes,
                    file_name="Color_Plan.xlsx",
                    mime=_XLSX_MIME,
                    key="rpt_color_plan_dl",
                )
            else:
                st.warning("No size data found.")

    with rpt_c2:
        st.markdown("**PO Summary**")
        st.caption("One row per PO with factory, COO, X-factory date and quantity.")
        if st.button("Generate PO Summary Excel", key="rpt_po_summary"):
            with st.spinner("Building summary…"):
                xlsx_bytes = _generate_po_summary_excel(df)
            st.download_button(
                "⬇ Download PO Summary",
                data=xlsx_bytes,
                file_name="PO_Summary.xlsx",
                mime=_XLSX_MIME,
                key="rpt_po_summary_dl",
            )

    # ── Master table (admin only) ─────────────────────────────────────────────
    if is_admin(st.session_state.get(SK.USERNAME, "")):
        st.divider()
        _show_master_po_table()

    st.divider()

    # ── Delete ────────────────────────────────────────────────────────────────
    st.markdown("**Delete POs from history**")
    to_delete = st.multiselect("Select POs to delete:", po_options,
                               placeholder="Select POs to remove…",
                               key="del_pos")
    if st.button("🗑 Delete selected", disabled=not to_delete):
        n = store.delete_pos(to_delete)
        st.success(f"Deleted {n} PO(s).")
        st.rerun()

    st.divider()

    # ── Exception queue ───────────────────────────────────────────────────────
    if exc_df is None:
        exc_df = store.list_exceptions(companies=user_cos if user_cos else None)
    exc_label = f"⚠️ Exception Queue ({pending_exc} pending)" if pending_exc else "⚠️ Exception Queue"
    with st.expander(exc_label, expanded=pending_exc > 0):
        if exc_df.empty:
            st.info("No exceptions.")
        else:
            st.dataframe(exc_df, width="stretch", hide_index=True)
            exc_id = st.number_input("Exception ID to update:", min_value=1, step=1, key="exc_id")
            new_status = st.selectbox("New status:", ["pending", "triaged", "corrected", "closed"],
                                      key="exc_status")
            if st.button("Update exception status", key="update_exc"):
                store.update_exception_status(int(exc_id), new_status)
                st.success("Updated.")
                st.rerun()
