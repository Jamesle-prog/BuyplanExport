"""Pure-logic enrichment of size rows with Chinese color names and codes.

The Streamlit-side caller fetches lookups from the color-translation store and
passes them in; this module knows nothing about Streamlit or DB connections.
"""
from __future__ import annotations

import pandas as pd

from po_extractor.store.color_translation_store import _normalize_color_name


def enrich_cn_color(
    df_size: pd.DataFrame,
    df_meta: pd.DataFrame,
    lookup: dict[tuple[str, str, str], str],
    cn_code_lookup: dict[tuple[str, str, str], str] | None = None,
) -> pd.DataFrame:
    """Add 'Color (CN)' (and optionally '中文颜色代码') to *df_size*.

    Uses a (client, brand, en_color) lookup keyed on normalised title-case
    English colour names.  Joins df_meta on po_number to determine each
    row's (client, brand), then:
      1. tries (client, brand, color),
      2. falls back to (client, '', color) if no brand-specific match.

    If *lookup* is empty, every row gets ''.
    If *cn_code_lookup* is provided the same two-step fallback populates
    the '中文颜色代码' column.

    Returns a copy; the input is not mutated.
    """
    df_size = df_size.copy()
    if not lookup:
        df_size["Color (CN)"] = ""
        if cn_code_lookup is not None:
            df_size["中文颜色代码"] = ""
        return df_size

    meta_map: dict[str, tuple[str, str]] = {}
    if not df_meta.empty and "po_number" in df_meta.columns:
        for _, row in df_meta.iterrows():
            pn = str(row["po_number"])
            client = str(row.get("company", "") or "").strip()
            brand = str(row.get("division_name", "") or "").strip()
            meta_map[pn] = (client, brand)

    def _resolve(row, lkp: dict) -> str:
        pn = str(row.get("PO Number", ""))
        color = _normalize_color_name(str(row.get("Color", "")))
        client, brand = meta_map.get(pn, ("", ""))
        val = lkp.get((client, brand, color), "")
        if not val and brand:
            val = lkp.get((client, "", color), "")
        return val

    df_size["Color (CN)"] = df_size.apply(lambda r: _resolve(r, lookup), axis=1)
    if cn_code_lookup is not None:
        df_size["中文颜色代码"] = df_size.apply(lambda r: _resolve(r, cn_code_lookup), axis=1)
    return df_size


def enrich_hhp_colors(
    df: pd.DataFrame,
    company: str,
    label_lookup: dict[tuple[str, str, str], str],
    cn_code_lookup: dict[tuple[str, str, str], str],
) -> pd.DataFrame:
    """Add '主标颜色' and '中文颜色代码' columns to an HHP/Zalando DataFrame.

    Resolves via (company, brand, en_color) with a brand-agnostic fallback.
    EN colour from 'Main Supplier Color Description'; brand from 'Brand'.

    Returns a copy; the input is not mutated.
    """
    df = df.copy()
    en_col = "Main Supplier Color Description"
    brand_col = "Brand"

    def _resolve(row, lkp: dict) -> str:
        en = _normalize_color_name(str(row.get(en_col, "") or ""))
        brand = str(row.get(brand_col, "") or "").strip()
        val = lkp.get((company, brand, en), "")
        if not val and brand:
            val = lkp.get((company, "", en), "")
        return val

    df["主标颜色"] = df.apply(lambda r: _resolve(r, label_lookup), axis=1)
    df["中文颜色代码"] = df.apply(lambda r: _resolve(r, cn_code_lookup), axis=1)
    return df
