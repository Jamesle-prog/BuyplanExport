"""Sky East item DataFrame → buy-plan DataFrame transformation."""
from __future__ import annotations

import pandas as pd

from auth.companies import COMPANY_SKY_EAST

# Sky East size column mapping (db lowercase → display uppercase)
SE_SIZE_COLS: list[tuple[str, str]] = [
    ("xs", "XS"), ("s", "S"), ("m", "M"),
    ("l", "L"), ("xl", "XL"), ("xxl", "XXL"),
]


def se_items_to_buyplan_dfs(df_items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convert Sky East items DataFrame to (df_size, df_meta) for export_buyplan.

    df_size columns: PO Number | Style | Color | Size | Units
    df_meta columns: po_number | company | division_name | xport_date
        company = "Sky East"  → triggers Sky East template
        division_name = brand → enables Chinese color enrichment
    """
    if df_items.empty:
        return pd.DataFrame(), pd.DataFrame()

    present = [(lc, uc) for lc, uc in SE_SIZE_COLS if lc in df_items.columns]

    size_rows = []
    for _, row in df_items.iterrows():
        po = str(row.get("zalando_po", "") or "")
        style = str(row.get("style", "") or "")
        color = str(row.get("color_name", "") or "")
        for lc, uc in present:
            qty = int(row.get(lc, 0) or 0)
            if qty > 0:
                size_rows.append({
                    "PO Number": po, "Style": style,
                    "Color": color, "Size": uc, "Units": qty,
                })

    df_size = pd.DataFrame(
        size_rows,
        columns=["PO Number", "Style", "Color", "Size", "Units"],
    )

    meta_rows = []
    for _, row in df_items.drop_duplicates(subset=["zalando_po"]).iterrows():
        meta_rows.append({
            "po_number":     str(row.get("zalando_po", "") or ""),
            "company":       COMPANY_SKY_EAST,
            "division_name": str(row.get("brand", "") or ""),
            "xport_date":    str(row.get("ex_fty_date", "") or ""),
        })
    df_meta = pd.DataFrame(meta_rows)

    return df_size, df_meta
