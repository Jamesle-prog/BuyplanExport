"""Pure-logic Excel report builders (color plan + PO summary).

These take a pandas DataFrame and return bytes — no Streamlit, no DB.
The Streamlit-side caller in app.py loads the DataFrame, then delegates here.
"""
from __future__ import annotations

import io
from typing import Callable

import pandas as pd

from po_extractor.ui_helpers.excel_format import write_excel_header_row

# Standard size ordering for color-plan pivots.
SIZE_ORDER: list[str] = [
    "XS", "S", "M", "L", "XL", "XXL", "2XL", "ONE SIZE", "OS",
]


def generate_color_plan_excel(df_size_rows: pd.DataFrame) -> bytes:
    """Pivot size rows into a color plan: one row per (PO, Style, Color), sizes as columns.

    Input columns required: PO Number, Style, Color, Size, Units.
    Returns b'' for empty input.
    """
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill

    if df_size_rows is None or df_size_rows.empty:
        return b""

    pivot = df_size_rows.pivot_table(
        index=["PO Number", "Style", "Color"],
        columns="Size",
        values="Units",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    pivot.columns.name = None

    size_cols = [s for s in SIZE_ORDER if s in pivot.columns]
    extra = [c for c in pivot.columns
             if c not in ["PO Number", "Style", "Color"] + size_cols]
    ordered = ["PO Number", "Style", "Color"] + size_cols + extra
    pivot = pivot[[c for c in ordered if c in pivot.columns]]
    pivot["Total"] = pivot[size_cols + extra].sum(axis=1)

    wb = Workbook()
    ws = wb.active
    ws.title = "Color Plan"
    write_excel_header_row(ws, list(pivot.columns))

    alt_fill = PatternFill("solid", start_color="EEF2FF", end_color="EEF2FF")
    for ri, row in enumerate(pivot.itertuples(index=False), start=2):
        for ci, val in enumerate(row, start=1):
            cell = ws.cell(row=ri, column=ci, value=val)
            if ri % 2 == 0:
                cell.fill = alt_fill

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_po_summary_excel(
    df_pos: pd.DataFrame,
    label_for: Callable[[str, str], str] | None = None,
) -> bytes:
    """One-row-per-PO summary with key header fields.

    *label_for(db_col, fallback)* resolves human-readable column labels.
    When None, uses the static fallback strings only — handy for tests.
    """
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill

    if label_for is None:
        def label_for(db_col, fallback):  # noqa: E306
            return fallback

    summary_map = [
        ("company",           label_for("company",           "Company")),
        ("po_number",         label_for("po_number",         "PO No.")),
        ("style",             label_for("style",             "Style No.")),
        ("factory",           label_for("factory",           "Factory")),
        ("country_of_origin", label_for("country_of_origin", "COO")),
        ("xport_date",        label_for("ex_fty_date",       "Ex-Factory Date")),
        ("issue_date",        "Issue Date"),
        ("version",           "Version"),
        ("division_name",     "Division"),
        ("total_units",       label_for("total_qty",         "Total Qty")),
        ("source_format",     "Source"),
        ("extracted_at",      label_for("extracted_at",      "Extracted At")),
    ]
    cols = [(db, lbl) for db, lbl in summary_map if db in df_pos.columns]
    out_df = df_pos[[c[0] for c in cols]].copy()
    out_df.columns = [c[1] for c in cols]

    wb = Workbook()
    ws = wb.active
    ws.title = "PO Summary"
    write_excel_header_row(ws, list(out_df.columns))

    alt_fill = PatternFill("solid", start_color="F2F7FF", end_color="F2F7FF")
    for ri, row in enumerate(out_df.itertuples(index=False), start=2):
        for ci, val in enumerate(row, start=1):
            cell = ws.cell(row=ri, column=ci, value=val)
            if ri % 2 == 0:
                cell.fill = alt_fill

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
