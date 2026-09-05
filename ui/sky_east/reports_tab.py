"""Sky East Generate / Export tab — one screen for Buy Plan + 核料, Item Data,
and Wash Labels.

Flattened from three sub-tabs (v2.22.0): a horizontal output-type radio swaps
the options panel below, and ONE shared PC-No. selector serves every mode —
switching output type no longer loses the selection.  ``st.radio`` (not
``st.tabs``) so all three panels never stream/render at once and the mode is
session-state addressable — same rationale as Production Tracking's sub-nav.
"""
from __future__ import annotations

import streamlit as st

from ui.i18n import t
from ui.shared import multiselect_with_select_all
from ui.stores import get_sky_east_store
from ui.sky_east.history import (
    _se_hist_buyplan_section,
    _se_hist_multi_pc_download,
    _se_hist_wash_label_download,
)

_MODE_BP = "📊 Buy Plan + 核料"
_MODE_DL = "📥 Item Data"
_MODE_WL = "🏷 Wash Labels"
_GEN_MODES = [_MODE_BP, _MODE_DL, _MODE_WL]

# Public alias for callers (e.g. a restricted user role) that need to pin the
# output type instead of showing the full radio.
PIN_BUYPLAN = "buyplan"


def _show_se_reports_tab(pin_mode: str | None = None) -> None:
    """Generate/Export: pick an output type; PC selection is shared across all.

    ``pin_mode=PIN_BUYPLAN`` skips the output-type radio entirely and always
    renders the Buy Plan + 核料 section — used by the Sky East "Buy Plan only"
    restricted role so Item Data / Wash Labels stay hidden.
    """
    store        = get_sky_east_store()
    df_contracts = store.list_contracts()

    # Drop blank / null pc_nos — same guard as in _show_se_history_section
    df_contracts = df_contracts[df_contracts["pc_no"].fillna("").str.strip() != ""].copy()

    if df_contracts.empty:
        st.info(t("No Sky East contracts saved yet. Upload files via the New Contracts tab."))
        return

    pc_options = [pc for pc in df_contracts["pc_no"].tolist() if pc and str(pc).strip()]
    _pc_set = set(pc_options)

    # One-time migration: carry over a selection made under the old per-section
    # keys so users mid-task don't lose it after the flatten.
    if "se_gen_pcs" not in st.session_state:
        for _legacy in ("se_bp_sel", "se_dl_pcs", "se_wl_pcs"):
            _old = st.session_state.get(_legacy)
            if isinstance(_old, list) and _old:
                st.session_state["se_gen_pcs"] = [v for v in _old if v in _pc_set]
                break
    # (se_wl_styles holds style names, not PC Nos — it must NOT be pruned
    # against pc_options; the picker below guards se_gen_pcs itself.)

    # ── Output type ───────────────────────────────────────────────────────────
    if pin_mode == PIN_BUYPLAN:
        mode = _MODE_BP
    else:
        mode = st.radio(
            t("What do you want to generate?"),
            _GEN_MODES,
            horizontal=True,
            key="se_gen_mode",
        )

    # ── Shared PC selection (persists across output types) ───────────────────
    sel_pcs = multiselect_with_select_all(
        t("PC No.(s) to include:"), pc_options, "se_gen_pcs",
        placeholder="Select one or more PC Nos...")

    st.divider()

    if mode == _MODE_BP:
        _se_hist_buyplan_section(store, pc_options, df_contracts, sel_pcs=sel_pcs)
    elif mode == _MODE_DL:
        _se_hist_multi_pc_download(store, pc_options, sel_pcs=sel_pcs)
    else:
        _se_hist_wash_label_download(store, pc_options, sel_pcs=sel_pcs)
