"""Pure-logic fabric-mapping row parser.

Reads pre-loaded rows (from an xlsx workbook) into {style: [FabricPart, ...]}.
File-IO is left to the caller so this stays unit-testable.
"""
from __future__ import annotations

from typing import Iterable

from po_extractor.models.fabric_part import FabricPart
from po_extractor.ui_helpers.fabric_mapping_detect import (
    detect_fabric_mapping_columns,
)


def parse_fabric_mapping_rows(rows: Iterable[tuple]) -> dict[str, list[FabricPart]]:
    """Parse fabric-mapping rows (header + data) into {style: [FabricPart]}.

    First row is the header — passed to detect_fabric_mapping_columns().
    Subsequent rows are data; rows starting with '↑' (instruction marker) or
    blank style cells are skipped.
    """
    all_rows = list(rows)
    if not all_rows:
        return {}

    header_row = all_rows[0]
    layout = detect_fabric_mapping_columns(header_row)
    style_col = layout["style"]
    parts_layout = layout["parts"]

    result: dict[str, list[FabricPart]] = {}
    # Track how many file rows have been seen for each style so we can assign
    # a unique combo_idx to each row.  Styles appearing on N rows produce N
    # combinations (combo_idx 0 … N-1).  All parts from the same file row
    # share the same combo_idx; seq restarts at 1 within each row.
    combo_counter: dict[str, int] = {}
    # When the style column uses merged cells (common in Excel), openpyxl
    # returns None for all merged cells except the top-left one.  We carry
    # forward the last seen non-empty style so every data row is processed.
    last_style: str = ""

    for row in all_rows[1:]:
        if not row:
            continue
        style_val = row[style_col] if style_col < len(row) else None
        if not style_val:
            # Merged cell — inherit from previous row
            style_val = last_style if last_style else None
        if not style_val:
            continue
        style = str(style_val).strip()
        if not style or style.startswith("↑"):
            continue
        last_style = style

        parts: list[FabricPart] = []
        for seq, slot in enumerate(parts_layout, start=1):
            bp_ci = slot.get("body_part")
            code_ci = slot.get("code")
            bp = (str(row[bp_ci] or "").strip()
                  if (bp_ci is not None and bp_ci < len(row)) else "")
            hhn = (str(row[code_ci] or "").strip()
                   if (code_ci is not None and code_ci < len(row)) else "")
            if hhn:
                parts.append(FabricPart(seq=seq, body_part=bp, hhn_no=hhn))

        if not parts:
            continue

        # Assign the next available combo_idx for this style
        cidx = combo_counter.get(style, 0)
        combo_counter[style] = cidx + 1
        for p in parts:
            p.combo_idx = cidx

        result.setdefault(style, []).extend(parts)

    return result
