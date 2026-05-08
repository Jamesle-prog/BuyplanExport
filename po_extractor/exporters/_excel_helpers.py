"""Shared Excel-export utilities.

Single source of truth for small helpers that were previously duplicated
across several exporters (sheet-name cleanup, stable de-duplication, cell
value extraction).
"""
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.properties import PageSetupProperties


# ---------------------------------------------------------------------------
# Page / print settings
# ---------------------------------------------------------------------------

def apply_print_settings(wb) -> None:
    """Apply A4 landscape "fit all columns on one page" print settings to every
    sheet in *wb*.

    Settings match the Excel Page Setup screenshot:
      • 横向    — Landscape orientation
      • A4      — 21 cm × 29.7 cm
      • 将所有列调整为一页 — fitToWidth=1, fitToHeight=0 (unlimited rows)

    Call this just before ``wb.save()`` so it applies to all sheets including
    any Index sheet and per-style copies.

    Implementation note
    -------------------
    openpyxl's ``page_setup.fitToPage`` is not a real attribute and has no
    effect.  The "fit to page" scaling mode is controlled by two separate XML
    elements:
      • ``<sheetPr><pageSetUpPr fitToPage="1"/>`` — switches Excel from
        percentage scaling to fit-to-page mode (set via
        ``ws.sheet_properties.pageSetUpPr``).
      • ``<pageSetup fitToWidth="1" fitToHeight="0"/>`` — the actual page
        counts (set via ``ws.page_setup``).
    Both must be present; missing either one leaves Excel using the default
    percentage scaling and the fit-to-page settings are silently ignored.
    """
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize   = 9     # A4  (openpyxl PAPERSIZE_A4)
        ws.page_setup.fitToWidth  = 1     # all columns on one page
        ws.page_setup.fitToHeight = 0     # unlimited pages tall
        # Switch Excel to fit-to-page scaling mode (the missing piece).
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        # Margins (all values in inches):
        #   上/下 1.91 cm = 0.75 in  |  左/右 0.64 cm = 0.25 in
        #   页眉/页脚 0.76 cm = 0.30 in
        ws.page_margins = PageMargins(
            top=0.75, bottom=0.75,
            left=0.25, right=0.25,
            header=0.30, footer=0.30,
        )


# ---------------------------------------------------------------------------
# Sheet names
# ---------------------------------------------------------------------------

# Excel forbids these characters in sheet names: / \ [ ] * ? :
# Apostrophe is technically allowed but breaks formula references
# like 'sheet'!A1, so we strip it too (BUG-41 mitigation).
_ILLEGAL_SHEET_CHARS = r"/\[]*?:'"


def clean_sheet_name(name: str | None, *, fallback: str = "Sheet") -> str:
    """Return a valid Excel sheet name (≤31 chars, no illegal characters).

    Replaces every occurrence of ``/ \\ [ ] * ? :`` and apostrophe with ``_``
    and truncates to 31 characters.  Empty / None input returns *fallback*.
    """
    s = (name or "").strip()
    if not s:
        return fallback
    for ch in _ILLEGAL_SHEET_CHARS:
        s = s.replace(ch, "_")
    return s[:31] or fallback


# ---------------------------------------------------------------------------
# Sequence helpers
# ---------------------------------------------------------------------------

def stable_unique(values: Iterable[Any]) -> list:
    """Return values in first-seen order, with duplicates removed.

    Works on any iterable (lists, pandas Series, generators).  Values must
    be hashable.
    """
    seen: set = set()
    out: list = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


# ---------------------------------------------------------------------------
# Cell value extraction
# ---------------------------------------------------------------------------

_NULLISH = {"", "nan", "none", "null"}


def cell_value(row, col: str) -> str | None:
    """Return a stripped string from a pandas Series / dict-like *row*.

    Returns None when the cell is empty, missing, NaN, or string "nan".
    """
    v = row.get(col) if hasattr(row, "get") else None
    if v is None:
        try:
            v = row[col]
        except (KeyError, TypeError, IndexError):
            return None
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in _NULLISH else None
