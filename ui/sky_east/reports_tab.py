"""Sky East Reports tab — generate Buy Plan, 核料, Item Downloads, Wash Labels."""
from __future__ import annotations

import streamlit as st

from ui.i18n import t
from ui.stores import get_sky_east_store
from ui.sky_east.history import (
    _se_hist_buyplan_section,
    _se_hist_multi_pc_download,
    _se_hist_wash_label_download,
)


def _show_se_reports_tab() -> None:
    """Reports tab: generate outputs from stored Sky East contracts."""
    store        = get_sky_east_store()
    df_contracts = store.list_contracts()

    # Drop blank / null pc_nos — same guard as in _show_se_history_section
    df_contracts = df_contracts[df_contracts["pc_no"].fillna("").str.strip() != ""].copy()

    if df_contracts.empty:
        st.info(t("No Sky East contracts saved yet. Upload files via the New Contracts tab."))
        return

    pc_options = [pc for pc in df_contracts["pc_no"].tolist() if pc and str(pc).strip()]

    # Guard stale session-state values — identical fix to _se_hist_item_browser.
    # After a contract is deleted (History tab) the key may still hold pc_nos
    # that are no longer in pc_options, which causes StreamlitAPIException when
    # the multiselect renders and breaks the entire Buy Plan / Download / Wash
    # Label sections (making the file uploaders appear unresponsive).
    # NOTE: se_wl_styles holds *style names*, not PC Nos — it must NOT be
    # filtered against _pc_set or every valid style gets wiped after a delete.
    _pc_set = set(pc_options)
    for _sk in ("se_bp_sel", "se_dl_pcs", "se_wl_pcs"):
        _cur = st.session_state.get(_sk, [])
        if isinstance(_cur, list) and any(v not in _pc_set for v in _cur):
            st.session_state[_sk] = [v for v in _cur if v in _pc_set]

    sub_bp, sub_dl, sub_wl = st.tabs([
        "📊 Buy Plan + 核料",
        "📥 Download Items",
        "🏷 Wash Labels",
    ])

    with sub_bp:
        _se_hist_buyplan_section(store, pc_options, df_contracts)

    with sub_dl:
        _se_hist_multi_pc_download(store, pc_options)

    with sub_wl:
        _se_hist_wash_label_download(store, pc_options)
