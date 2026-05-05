"""Shared string normalization utilities used across parsers, stores and exporters."""
from __future__ import annotations

import re


def normalize_header(s: str | None) -> str:
    """Normalize a header / column label for alias matching.

    * Strips surrounding whitespace
    * Maps full-width brackets, colons, spaces and yen signs to ASCII equivalents
    * Converts ``\\n`` to a regular space
    * Collapses any run of whitespace to a single space
    * Lowercases the result

    This is the single canonical implementation used by
    ``fabric_master_store``, ``buyplan_export`` and the Sky East mapping
    parser in ``app.py``.  Any previously local ``_norm_header`` /
    ``_norm_col`` / ``_norm_mapping_header`` functions delegate here.
    """
    if s is None:
        return ""
    s = str(s).strip()
    s = (
        s.replace('\uff08', '(')   # （
         .replace('\uff09', ')')   # ）
         .replace('\uff1a', ':')   # ：
         .replace('\u3000', ' ')   # ideographic space
         .replace('\uffe5', '\xa5')  # ￥ → ¥
         .replace('\n', ' ')
    )
    return re.sub(r'\s+', ' ', s.lower())
