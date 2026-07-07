"""Standardized cross-client PO summary — one row shape for all pipelines.

Each client pipeline stores orders in its own schema (GIII: po_metadata /
po_size_rows; Sky East: sky_east_contracts / sky_east_items), so any view
that wants "all results together" previously had to hand-write per-client
column handling.  This module defines ONE standard column set and adapters
that map each pipeline's native list DataFrame into it, so combined views
and exports only ever deal with the standard shape.

The standard columns deliberately stay at the union of what both clients
can meaningfully fill — a field one client can't provide is left blank
rather than dropped, so the header row is identical no matter which
clients contribute rows.
"""
from __future__ import annotations

import pandas as pd

# Ordered standard column set: (key, English header label).
# Keys are snake_case for DataFrame use; labels are what views/exports show.
STANDARD_COLUMNS: list[tuple[str, str]] = [
    ("company",           "Company"),
    ("po_number",         "PO Number"),
    ("contract_no",       "Contract No."),
    ("style",             "Style"),
    ("color",             "Color"),
    ("brand_customer",    "Brand / Customer"),
    ("factory",           "Factory"),
    ("country_of_origin", "COO"),
    ("order_date",        "Order Date"),
    ("ex_fty_date",       "Ex-Fty Date"),
    ("units",             "Units"),
    ("unit_price",        "Unit Price"),
    ("total_cost",        "Total Cost"),
    ("season",            "Season"),
    ("source",            "Source"),
]

STANDARD_KEYS: list[str] = [k for k, _ in STANDARD_COLUMNS]
STANDARD_LABELS: dict[str, str] = dict(STANDARD_COLUMNS)


def _empty_standard() -> pd.DataFrame:
    return pd.DataFrame(columns=STANDARD_KEYS)


def giii_pos_to_standard(df: pd.DataFrame) -> pd.DataFrame:
    """Map a ``PoStore.list_pos()`` DataFrame to the standard shape.

    GIII grain is one row per PO (color lives one level deeper in
    po_size_rows, so it stays blank here).  GIII has no separate contract
    number — the PO number doubles as it, matching the existing
    "PC No. mirrors po_number" convention in the Summary view.
    """
    if df is None or df.empty:
        return _empty_standard()

    def col(name: str, default: str = "") -> pd.Series:
        if name in df.columns:
            return df[name].fillna(default)
        return pd.Series([default] * len(df), index=df.index)

    out = pd.DataFrame({
        "company":           col("company"),
        "po_number":         col("po_number"),
        "contract_no":       col("po_number"),
        "style":             col("style"),
        "color":             "",
        "brand_customer":    col("customer"),
        "factory":           col("factory"),
        "country_of_origin": col("country_of_origin"),
        "order_date":        col("issue_date"),
        "ex_fty_date":       col("xport_date"),
        "units":             pd.to_numeric(col("total_units", "0"), errors="coerce").fillna(0).astype(int),
        "unit_price":        col("unit_cost"),
        "total_cost":        col("line_extended_cost"),
        "season":            col("season"),
        "source":            col("source_format"),
    })
    return out[STANDARD_KEYS]


def sky_east_items_to_standard(df: pd.DataFrame,
                               company: str = "Sky East",
                               pc_dates: dict[str, str] | None = None) -> pd.DataFrame:
    """Map a ``SkyEastStore.list_items()`` DataFrame to the standard shape.

    Sky East grain is one row per item (style + color within a contract).
    ``pc_dates`` maps pc_no -> pc_date (from ``list_contracts()``) so the
    contract's date can serve as the Order Date; items themselves carry
    no date besides launch/ex-fty.
    """
    if df is None or df.empty:
        return _empty_standard()

    def col(name: str, default: str = "") -> pd.Series:
        if name in df.columns:
            return df[name].fillna(default)
        return pd.Series([default] * len(df), index=df.index)

    pc_no = col("pc_no")
    if pc_dates:
        order_date = pc_no.map(lambda p: pc_dates.get(p, "") or "")
    else:
        order_date = pd.Series([""] * len(df), index=df.index)

    out = pd.DataFrame({
        "company":           company,
        "po_number":         col("zalando_po"),
        "contract_no":       pc_no,
        "style":             col("style"),
        "color":             col("color_name"),
        "brand_customer":    col("brand"),
        "factory":           "",
        "country_of_origin": "",
        "order_date":        order_date,
        "ex_fty_date":       col("ex_fty_date"),
        "units":             pd.to_numeric(col("total_qty", "0"), errors="coerce").fillna(0).astype(int),
        "unit_price":        pd.to_numeric(col("fob_usd", "0"), errors="coerce").fillna(0.0),
        "total_cost":        pd.to_numeric(col("total_cost_usd", "0"), errors="coerce").fillna(0.0),
        "season":            "",
        "source":            "sky_east",
    })
    return out[STANDARD_KEYS]


def combine_standard(*frames: pd.DataFrame) -> pd.DataFrame:
    """Concatenate standard-shape frames into one, preserving column order.

    Empty/None inputs are skipped; with no usable input an empty frame with
    the full standard header is returned so callers can render it uniformly.
    """
    usable = [f for f in frames if f is not None and not f.empty]
    if not usable:
        return _empty_standard()
    out = pd.concat(usable, ignore_index=True)
    return out[STANDARD_KEYS]
