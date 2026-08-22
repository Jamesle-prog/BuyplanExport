"""GIII PO History tab — re-export and delete sections."""
from __future__ import annotations

import streamlit as st

from ui.i18n import t
from auth.users import company_scope, is_admin
from ui.session_keys import SK
from ui.shared import guard_multiselect_state, delete_button
from ui.stores import get_store
from ui.giii._shared import _XLSX_MIME, live_label
from ui.giii.results import _show_master_po_table


def _show_history(exc_df=None, pos_df=None):
    store = get_store()
    user_cos = company_scope(st.session_state[SK.USERNAME])
    # Non-admin with no assigned companies must see nothing — an empty list
    # falls through the store's falsy check to an unfiltered query.
    if not is_admin(st.session_state[SK.USERNAME]) and not user_cos:
        st.info(
            t("No companies assigned to your account. "
            "Contact an administrator to be granted access.")
        )
        return
    # *pos_df* is the company-scoped list_pos frame fetched once per rerun in
    # show_smart_upload_tab; fall back to a direct read for other callers.
    df = (pos_df if pos_df is not None
          else store.list_pos(companies=user_cos))

    # ── Summary metrics ───────────────────────────────────────────────────────
    total_pos    = len(df)
    total_units  = int(df["total_units"].sum()) if not df.empty and "total_units" in df.columns else 0
    companies    = df["company"].nunique() if not df.empty and "company" in df.columns else 0
    pending_exc  = (len(exc_df[exc_df["status"] == "pending"])
                    if exc_df is not None and not exc_df.empty and "status" in exc_df.columns else 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("Total POs"),    f"{total_pos:,}")
    m2.metric(t("Total Units"),  f"{total_units:,}")
    m3.metric(t("Companies"),    companies)
    m4.metric(t("Pending Exceptions"), pending_exc, delta=None,
              delta_color="inverse" if pending_exc else "off")

    if df.empty:
        st.info(t("No POs stored yet. Extract some PDFs and they will appear here automatically."))
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
    show_all = st.toggle(t("Show all columns"), value=False, key="hist_show_all")
    active_cols = all_cols if show_all else essential_cols
    show_df = df[[c for c in active_cols if c in df.columns]].rename(columns=rename_map)
    st.dataframe(show_df, width="stretch", hide_index=True)

    # ── Version history ───────────────────────────────────────────────────────
    with st.expander(t("📜 View version history for a PO")):
        inspect_po = st.selectbox(t("Select PO:"), [""] + df["po_number"].tolist(),
                                  key="inspect_po")
        if inspect_po:
            hist = store.list_history(inspect_po)
            if hist.empty:
                st.info(t("No previous versions — this PO has never been updated."))
            else:
                st.caption(t("{n} archived version(s) for {po}").format(n=len(hist), po=inspect_po))
                st.dataframe(hist, width="stretch", hide_index=True)

    # ── Master table (admin only) ─────────────────────────────────────────────
    if is_admin(st.session_state.get(SK.USERNAME, "")):
        st.divider()
        _show_master_po_table()

    st.divider()

    # ── Delete ────────────────────────────────────────────────────────────────
    st.markdown(t("**Delete POs from history**"))
    po_options = df["po_number"].tolist()
    # Guard: after a delete the reran multiselect would hold PO numbers no
    # longer in options — StreamlitAPIException on 1.57, silent wipe on 1.58.
    guard_multiselect_state("del_pos", po_options)
    to_delete = st.multiselect(t("Select POs to delete:"), po_options,
                               placeholder=t("Select POs to remove…"),
                               key=SK.DEL_POS)
    if delete_button(t("Delete selected"), key="giii_hist_delete", disabled=not to_delete):
        n = store.delete_pos(to_delete)
        st.session_state.pop(SK.DEL_POS, None)   # drop stale selection pre-rerun
        st.success(t("Deleted {n} PO(s).").format(n=n))
        st.rerun()

    st.divider()

    # ── Exception queue ───────────────────────────────────────────────────────
    if exc_df is None:
        exc_df = store.list_exceptions(companies=user_cos)
    exc_label = f"⚠️ Exception Queue ({pending_exc} pending)" if pending_exc else "⚠️ Exception Queue"
    with st.expander(exc_label, expanded=pending_exc > 0):
        if exc_df.empty:
            st.info(t("No exceptions."))
        else:
            st.dataframe(exc_df, width="stretch", hide_index=True)
            # Chosen from the rows this user can actually see, not typed. As a
            # free-text number this accepted any id in the table, and the store
            # updates by id without a company check — so a user scoped to one
            # client could change another client's exception status.
            _ids = [int(i) for i in exc_df["id"]]
            exc_id = st.selectbox(
                t("Exception ID to update:"), _ids, index=None,
                placeholder=t("— select an exception —"), key="exc_id")
            new_status = st.selectbox(t("New status:"), ["pending", "triaged", "corrected", "closed"],
                                      key="exc_status")
            if st.button(t("Update exception status"), key="update_exc",
                         disabled=exc_id is None):
                # Re-checked against the store at the moment of writing: the
                # list above is a render-time snapshot, and the widget key
                # outlives it.
                if int(exc_id) not in store.exception_ids(user_cos):
                    st.error(t("That exception isn't one of yours."))
                else:
                    store.update_exception_status(int(exc_id), new_status)
                    st.success(t("Updated."))
                    st.rerun()
