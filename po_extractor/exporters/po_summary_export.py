"""PO Summary export — delegates to the rich two-sheet format in excel_reports.

The rich format produces:
  Sheet 1 "PO Summary"   — header block (Vendor, Factory, COO, Incoterm, ETD,
                            Season, Fabric, Pack, Discount, HTS, FOB) +
                            detail table (PO Number | Style | Color Code | Color Name |
                            FOB | Cost P/U | <sizes> | Total Units | Extended Cost)
  Sheet 2 "Size Breakdown" — Style | Color Code | Color Name | <sizes> | Total
"""
from __future__ import annotations

import pandas as pd

from ..utils.file_utils import versioned_path
from ..ui_helpers.excel_reports import generate_po_summary_excel


def export_po_summary(df_size: pd.DataFrame, df_meta: pd.DataFrame, output_dir: str) -> str:
    """Write the rich PO Summary workbook to *output_dir* and return the path.

    Parameters
    ----------
    df_size : DataFrame
        Size rows — columns: PO Number, Style, Color, Size, Units [, UPC].
    df_meta : DataFrame
        Metadata rows — one row per PO, snake_case field names matching
        POMetadata (po_number, seller, factory, country_of_origin, incoterm,
        po_date / issue_date, xport_date, season, style_description,
        packaging, discount, style_group, unit_cost, line_extended_cost, …).
    output_dir : str
        Directory where the Excel file is written.
    """
    path = versioned_path(output_dir, "po_summary", ".xlsx")

    # Normalise df_meta so generate_po_summary_excel can find all fields.
    # The key difference: export_csvs uses POMetadata field names (po_date),
    # while list_pos() uses the DB column name (issue_date). We accept both.
    df_pos = df_meta.copy()
    if "po_date" in df_pos.columns and "issue_date" not in df_pos.columns:
        df_pos = df_pos.rename(columns={"po_date": "issue_date"})
    if "po_number" not in df_pos.columns and "PO Number" in df_pos.columns:
        df_pos = df_pos.rename(columns={"PO Number": "po_number"})

    # Normalise df_size for generate_po_summary_excel (expects PO Number, Color, Size, Units)
    df_sz = df_size.copy()

    xlsx_bytes = generate_po_summary_excel(df_pos, df_sizes=df_sz)

    with open(path, "wb") as fh:
        fh.write(xlsx_bytes)

    return path
