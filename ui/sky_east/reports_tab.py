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

    if df_contracts.empty:
        st.info(t("No Sky East contracts saved yet. Upload files via the New Contracts tab."))
        return

    pc_options = df_contracts["pc_no"].tolist()

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
