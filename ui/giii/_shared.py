"""Shared constants and helpers for the GIII tab sub-modules."""
from __future__ import annotations
import streamlit as st
from po_extractor.ui_helpers import (
    live_label_for,
    load_live_schema, schema_seed_rows,
    enrich_cn_color as _enrich_cn_color_impl,
)
from po_extractor.utils.normalize import normalize_header as _normalize_header
from ui.shared import XLSX_MIME, CSV_MIME, ZIP_MIME, ProgressTracker
from ui.stores import get_color_translation_store

# ---------------------------------------------------------------------------
# MIME aliases
# ---------------------------------------------------------------------------
_XLSX_MIME = XLSX_MIME
_CSV_MIME  = CSV_MIME
_ZIP_MIME  = ZIP_MIME

# ---------------------------------------------------------------------------
# ProgressTracker alias
# ---------------------------------------------------------------------------
_ProgressTracker = ProgressTracker

# ---------------------------------------------------------------------------
# Live schema / label helpers
# ---------------------------------------------------------------------------
from po_extractor.config import SCHEMA_PATH as _SCHEMA_PATH, CACHE_TTL_SECONDS


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def _cached_schema() -> list[dict]:
    rows = load_live_schema(_SCHEMA_PATH)
    return rows if rows else schema_seed_rows()


def live_label(db_col: str, fallback: str | None = None) -> str:
    return live_label_for(_cached_schema(), db_col, fallback)


# ---------------------------------------------------------------------------
# Color enrichment wrapper
# ---------------------------------------------------------------------------

def _enrich_cn_color(df_size, df_meta):
    lookup = get_color_translation_store().build_lookup_dict()
    return _enrich_cn_color_impl(df_size, df_meta, lookup)


# ---------------------------------------------------------------------------
# Module-level aliases
# ---------------------------------------------------------------------------

_norm_mapping_header = _normalize_header

# ---------------------------------------------------------------------------
# Smart upload confidence badges
# ---------------------------------------------------------------------------
_CONF_BADGE = {"high": "🟢", "medium": "🟡", "low": "🔴"}

# ---------------------------------------------------------------------------
# Body part list (used for fabric mapping template)
# ---------------------------------------------------------------------------
_BODY_PART_LIST = [
    "Main Body / 大身",
    "Upper Body / 上身",
    "Lower Body / 下身",
    "Lining / 里布",
    "Sleeve / 袖子",
    "Collar / 领子",
    "Cuff / 袖口",
    "Hood / 帽子",
    "Pocket / 口袋布",
    "Pocket Lining / 口袋里布",
    "Pocket Mesh / 网眼布",
    "Waistband / 腰头",
    "Front Panel / 前片",
    "Back Panel / 后片",
    "Facing / 贴边",
    "Interlining / 衬布",
    "Piping / 嵌条",
    "Trim / 辅料",
]
