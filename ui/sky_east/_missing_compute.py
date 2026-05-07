"""Compute the missing-fields DataFrame for Sky East items."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.session_keys import SK
from ui.stores import get_sky_east_store


def _compute_se_missing_df() -> pd.DataFrame:
    """Build missing-fields DataFrame at view level."""
    from ui.sky_east.items_view import _enrich_items_df  # local to avoid circular

    store = get_sky_east_store()
    all_items = store.list_items()
    if all_items.empty:
        return pd.DataFrame()

    if "contract_no" not in all_items.columns:
        all_items["contract_no"] = ""

    pl = st.session_state.get(SK.SE_PROGRESS_LKUP)
    if pl is not None and "contract_no" in all_items.columns:
        def _fill_cno(row):
            cno = str(row.get("contract_no", "") or "").strip()
            if cno and cno.lower() not in ("", "none", "nan"):
                return cno
            return pl.get_contract_no(
                str(row.get("style", "")).strip(),
                str(row.get("color_name", "")).strip(),
                str(row.get("zalando_po", "")).strip(),
                pc_no=str(row.get("pc_no", "")).strip(),
            ) or cno
        all_items["contract_no"] = all_items.apply(_fill_cno, axis=1)

    enriched = _enrich_items_df(all_items)

    for col in ("composition_en", "cuttable_width_cm"):
        if col not in enriched.columns:
            enriched[col] = None

    mask = (
        enriched["fabric_item_no"].fillna("").str.strip().eq("") |
        enriched["contract_no"].fillna("").str.strip().eq("") |
        enriched["composition_en"].fillna("").str.strip().eq("") |
        enriched["cuttable_width_cm"].fillna(0).eq(0)
    )
    keep_cols = [c for c in
                 ["pc_no", "zalando_po", "style", "color_name", "brand",
                  "fabric_item_no", "contract_no", "ex_fty_date", "total_qty",
                  "composition_en", "cuttable_width_cm", "picture_id"]
                 if c in enriched.columns]
    return enriched[mask][keep_cols].copy()
