"""Fabric-mapping header-column detector (bilingual, slot-based)."""
from __future__ import annotations

from po_extractor.utils.normalize import normalize_header as _norm

# Pre-normalised style-column keyword set
STYLE_COL_KEYWORDS: set[str] = {
    _norm(a) for a in [
        "style no.", "style no", "style", "款式号", "款式",
        "supplier article number", "style number", "style code",
    ]
}
# Sub-strings that indicate a "body part" column (checked after slot digit found)
BODY_PART_KEYWORDS = ("body part", "body", "部位", "body_part", "bodypart")
# Sub-strings that indicate a "fabric code / HHN" column
CODE_KEYWORDS = ("code", "编号", "hhn", "fabric no", "fabric_no", "fabric code")


def detect_fabric_mapping_columns(header_row: tuple) -> dict:
    """Scan *header_row* and return a column-layout dict.

    Returns:
        {
            "style": int,                          # 0-based col index
            "parts": [                             # up to 4 fabric slots
                {"body_part": int | None, "code": int},
            ],
        }

    Falls back to the standard template layout when no headers are recognised.
    """
    style_col: int | None = None
    body_part_cols: dict[int, int] = {}
    code_cols: dict[int, int] = {}

    for ci, val in enumerate(header_row):
        norm = _norm(val)
        if not norm:
            continue

        if norm in STYLE_COL_KEYWORDS:
            style_col = ci
            continue
        if any(kw in norm for kw in ("style no", "款式号", "款式", "style code")):
            if style_col is None:
                style_col = ci
            continue

        slot: int | None = None
        for ch in norm:
            if ch.isdigit() and 1 <= int(ch) <= 4:
                slot = int(ch)
                break
        if slot is None:
            continue

        if any(kw in norm for kw in BODY_PART_KEYWORDS):
            body_part_cols.setdefault(slot, ci)
        elif any(kw in norm for kw in CODE_KEYWORDS):
            code_cols.setdefault(slot, ci)

    # Fallback: standard template layout
    if style_col is None or not code_cols:
        return {
            "style": 0,
            "parts": [
                {"body_part": (s - 1) * 2 + 1, "code": (s - 1) * 2 + 2}
                for s in range(1, 5)
            ],
        }

    all_slots = sorted(set(code_cols) | set(body_part_cols))
    parts = [
        {"body_part": body_part_cols.get(slot), "code": code_cols[slot]}
        for slot in all_slots
        if slot in code_cols
    ]
    return {"style": style_col, "parts": parts}
