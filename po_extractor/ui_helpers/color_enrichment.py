"""Pure-logic enrichment of size rows with Chinese color names.

The Streamlit-side caller fetches `lookup` from the color-translation store and
passes it in; this module knows nothing about Streamlit or DB connections.
"""
from __future__ import annotations

import pandas as pd


def enrich_cn_color(
    df_size: pd.DataFrame,
    df_meta: pd.DataFrame,
    lookup: dict[tuple[str, str, str], str],
) -> pd.DataFrame:
    """Add 'Color (CN)' column to *df_size* using a (client, brand, en_color) lookup.

    Joins df_meta on po_number to determine each row's (client, brand), then:
      1. tries (client, brand, color),
      2. falls back to (client, '', color) if no brand-specific match.

    If *lookup* is empty, every row gets ''.

    Returns a copy; the input is not mutated.
    """
    df_size = df_size.copy()
    if not lookup:
        df_size["Color (CN)"] = ""
        return df_size

    meta_map: dict[str, tuple[str, str]] = {}
    if not df_meta.empty and "po_number" in df_meta.columns:
        for _, row in df_meta.iterrows():
            pn = str(row["po_number"])
            client = str(row.get("company", "") or "").strip()
            brand = str(row.get("division_name", "") or "").strip()
            meta_map[pn] = (client, brand)

    def _get_cn(row) -> str:
        pn = str(row.get("PO Number", ""))
        color = str(row.get("Color", "")).strip()
        client, brand = meta_map.get(pn, ("", ""))
        cn = lookup.get((client, brand, color), "")
        if not cn and brand:
            cn = lookup.get((client, "", color), "")
        return cn

    df_size["Color (CN)"] = df_size.apply(_get_cn, axis=1)
    return df_size
