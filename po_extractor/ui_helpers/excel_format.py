"""Pure-logic Excel header-row writer (openpyxl)."""
from __future__ import annotations

from typing import Iterable


def write_excel_header_row(ws, cols: Iterable, fill_hex: str = "4472C4") -> None:
    """Write *cols* as a styled header row in row 1 of openpyxl worksheet *ws*.

    Side effects on ws:
      - Cells (1, 1..N) get values, bold white font, solid fill, centered alignment.
      - Column widths are set to max(10, len(label) + 2).
      - Row 1 height is set to 28.
    """
    from openpyxl.styles import Alignment, Font, PatternFill

    fill = PatternFill("solid", start_color=fill_hex, end_color=fill_hex)
    for ci, col in enumerate(cols, start=1):
        c = ws.cell(row=1, column=ci, value=col)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = max(10, len(str(col)) + 2)
    ws.row_dimensions[1].height = 28
