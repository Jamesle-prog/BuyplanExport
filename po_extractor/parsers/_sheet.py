"""Worksheet scaffolding shared by the openpyxl-based sheet parsers
(settlement 结算统计表, fabric condition 面料情况): locate the heading row,
index headings, read cells by field name.
"""
from __future__ import annotations

from typing import Any, Callable

from ..utils.normalize import norm_header_key


def find_header_row(ws, is_header: Callable[[set[str]], bool], *,
                    max_rows: int, norm: Callable[[Any], str] = norm_header_key) -> int:
    """First row (1-based, within *max_rows*) whose set of normalised cell
    texts satisfies *is_header*; ``-1`` when none does."""
    for r in range(1, min(ws.max_row, max_rows) + 1):
        heads = {norm(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)}
        if is_header(heads):
            return r
    return -1


def header_index(ws, row: int, norm: Callable[[Any], str] = norm_header_key) -> dict[str, int]:
    """``{normalised heading: column}`` for *row*; blank cells skipped, the
    first column wins for a repeated heading."""
    idx: dict[str, int] = {}
    for c in range(1, ws.max_column + 1):
        head = norm(ws.cell(row, c).value)
        if head:
            idx.setdefault(head, c)
    return idx


def cell_getter(ws, cols: dict[str, int]) -> Callable[[int, str], Any]:
    """``get(row, field)`` → raw cell value via the *cols* field→column map,
    ``None`` for an unmapped field."""
    def get(r: int, field: str):
        c = cols.get(field)
        return ws.cell(r, c).value if c else None
    return get
