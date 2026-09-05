"""The live column-label schema, cached once for the whole app.

``cached_schema()`` is the single ``st.cache_data`` entry for the schema
file: the GIII tab, the Sky East tab and the Admin schema editor's
``on_schema_change`` all share it, so clearing it after an edit refreshes
every tab's labels at once (three separate caches used to wait out their own
60 s TTL).  Heavy imports stay inside the function so the login page never
pays for them.
"""
from __future__ import annotations

import streamlit as st

from po_extractor.config import SCHEMA_PATH, CACHE_TTL_SECONDS


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cached_schema() -> list[dict]:
    """Live schema rows, or the built-in seed rows when the file is empty /
    missing."""
    from po_extractor.ui_helpers import load_live_schema, schema_seed_rows
    rows = load_live_schema(SCHEMA_PATH)
    return rows if rows else schema_seed_rows()


def live_label(db_col: str, fallback: str | None = None) -> str:
    """Display label for *db_col* from the live schema (``fallback`` when the
    column is not in the schema)."""
    from po_extractor.ui_helpers import live_label_for
    return live_label_for(cached_schema(), db_col, fallback)
