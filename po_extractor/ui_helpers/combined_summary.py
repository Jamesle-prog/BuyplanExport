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

import re as _re

import pandas as pd

from ..lookups.progress_lookup import _norm_key

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


def build_contract_maps(progress_records: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """Build contract-number lookups from stored 大货进度表 progress records
    (the record shape returned by ``POStore.load_progress_records()``).

    Returns ``(by_po, by_style)``:
      * by_po    — normalized PO# ("zalando_po" record key, which despite the
                   name is the sheet's generic buyer-PO column) -> contract_no
      * by_style — normalized style -> contract_no (fallback when the sheet's
                   PO# column is blank, as it often is)

    First non-empty contract wins per key, so re-listed colour rows of the
    same contract line don't flip-flop the mapping.
    """
    by_po: dict[str, str] = {}
    by_style: dict[str, str] = {}
    for rec in progress_records or []:
        contract = (rec.get("contract_no") or "").strip()
        if not contract:
            continue
        po_key = _norm_key(rec.get("zalando_po") or "")
        if po_key and po_key not in by_po:
            by_po[po_key] = contract
        style_key = _norm_key(rec.get("style") or "")
        if style_key and style_key not in by_style:
            by_style[style_key] = contract
    return by_po, by_style


def giii_pos_to_standard(df: pd.DataFrame,
                         contract_by_po: dict[str, str] | None = None,
                         contract_by_style: dict[str, str] | None = None) -> pd.DataFrame:
    """Map a ``PoStore.list_pos()`` DataFrame to the standard shape.

    GIII grain is one row per PO (color lives one level deeper in
    po_size_rows, so it stays blank here).  GIII's contract number comes
    from the HHN 大货进度表 progress records (see ``build_contract_maps``):
    matched by PO number first, then by style; blank when the progress
    sheet has no row for the order.
    """
    if df is None or df.empty:
        return _empty_standard()

    def col(name: str, default: str = "") -> pd.Series:
        if name in df.columns:
            return df[name].fillna(default)
        return pd.Series([default] * len(df), index=df.index)

    by_po = contract_by_po or {}
    by_style = contract_by_style or {}

    def contract_for(row_po: str, row_style: str) -> str:
        return (by_po.get(_norm_key(row_po))
                or by_style.get(_norm_key(row_style))
                or "")

    contract_no = [
        contract_for(p, s)
        for p, s in zip(col("po_number"), col("style"))
    ]

    out = pd.DataFrame({
        "company":           col("company"),
        "po_number":         col("po_number"),
        "contract_no":       pd.Series(contract_no, index=df.index),
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


# ---------------------------------------------------------------------------
# One-call loaders — consumers ask for "all orders in the standard shape"
# instead of orchestrating per-pipeline store reads themselves.
# ---------------------------------------------------------------------------

def load_standard_orders(po_store, sky_east_store,
                         companies: list[str] | None = None,
                         include_giii: bool = True,
                         include_sky_east: bool = True,
                         sky_east_company: str = "Sky East",
                         giii_df: pd.DataFrame | None = None,
                         se_items: pd.DataFrame | None = None) -> pd.DataFrame:
    """Load every pipeline's orders as ONE standard-shape DataFrame.

    ``po_store`` / ``sky_east_store`` are the canonical store objects (from
    the store factories); ``companies`` filters the GIII side like
    ``list_pos(companies=...)`` does.  GIII contract numbers are resolved
    from each company's stored 大货进度表 progress records automatically.

    ``giii_df`` / ``se_items`` are optional pre-fetched frames — the exact
    ``list_pos(companies=...)`` / ``list_items()`` results.  Pass them when
    the caller already loaded that data, so it isn't re-read from the stores
    (Streamlit re-renders every sub-tab per rerun; redundant full-table
    reads add up).
    """
    frames = []
    if include_giii:
        if giii_df is None:
            giii_df = po_store.list_pos(companies=companies)
        progress_records: list[dict] = []
        if not giii_df.empty and "company" in giii_df.columns:
            for comp in giii_df["company"].dropna().unique():
                # Same display-name → source-key rule as
                # ui.fabric_mapping_view._company_to_source (backend can't
                # import UI modules, so the regex is repeated here).
                source = _re.sub(r'[^a-z0-9]+', '_', str(comp).strip().lower()).strip('_')
                progress_records.extend(po_store.load_progress_records(source))
        by_po, by_style = build_contract_maps(progress_records)
        frames.append(giii_pos_to_standard(
            giii_df, contract_by_po=by_po, contract_by_style=by_style))
    if include_sky_east:
        if se_items is None:
            se_items = sky_east_store.list_items()
        contracts = sky_east_store.list_contracts()
        pc_dates = (dict(zip(contracts["pc_no"], contracts["pc_date"].fillna("")))
                    if not contracts.empty else {})
        frames.append(sky_east_items_to_standard(
            se_items, company=sky_east_company, pc_dates=pc_dates))
    return combine_standard(*frames)


# ---------------------------------------------------------------------------
# Size-grain adapter — sky_east_items in GIII's po_size_rows shape
# ---------------------------------------------------------------------------

# Fixed size buckets of the sky_east_items schema, in display order.
SKY_EAST_SIZE_COLS = ["xs", "s", "m", "l", "xl", "xxl"]

SIZE_ROW_KEYS = ["company", "po_number", "contract_no", "style", "color",
                 "size", "units"]


def sky_east_items_to_size_rows(df: pd.DataFrame,
                                company: str = "Sky East") -> pd.DataFrame:
    """Explode ``sky_east_items`` rows into one row per size — the same
    PO/style/color/size/units grain GIII's ``po_size_rows`` table has, so
    size-level consumers can treat both pipelines identically.

    Zero-quantity size buckets are dropped (a contract item never uses all
    six buckets; emitting empty ones would triple the row count for noise).
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=SIZE_ROW_KEYS)

    rows: list[dict] = []
    for rec in df.to_dict("records"):
        for size in SKY_EAST_SIZE_COLS:
            units = rec.get(size)
            try:
                units = int(units or 0)
            except (TypeError, ValueError):
                units = 0
            if units == 0:
                continue
            rows.append({
                "company":     company,
                "po_number":   rec.get("zalando_po") or "",
                "contract_no": rec.get("pc_no") or "",
                "style":       rec.get("style") or "",
                "color":       rec.get("color_name") or "",
                "size":        size.upper(),
                "units":       units,
            })
    return pd.DataFrame(rows, columns=SIZE_ROW_KEYS)
