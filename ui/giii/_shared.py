"""Shared constants and helpers for the GIII tab sub-modules."""
from __future__ import annotations
import re
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
# Fax-copy (AS400 doubled-font) parser helpers
# shared by msg_extraction, kl_extraction, tk_eu_extraction
# ---------------------------------------------------------------------------

def _undouble(s: str) -> str:
    """Collapse doubled characters produced by the AS400 fax-copy font."""
    return re.sub(r'(.)\1', r'\1', s)


def files_signature(files) -> tuple:
    """Order-insensitive identity of an uploader's file set (name + size).

    Stored next to extraction results so a changed upload selection
    invalidates them — previously the table (and its download button) kept
    serving the previous batch after the files were swapped.
    """
    return tuple(sorted((f.name, getattr(f, "size", None)) for f in (files or [])))


# Canonical fax-PO size column order (msg / kl / tk_eu builders).
# infornexus_extraction keeps its own superset — its output column order is
# part of that workbook's layout and must not silently change.
FAX_SIZE_ORDER = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '1X', '2X', '3X']

# Shared workbook palette (every GIII extraction Excel builder uses these).
XL_NAVY   = 'FF1F3864'
XL_WHITE  = 'FFFFFFFF'
XL_YELLOW = 'FFFFF2CC'
XL_GREY   = 'FFD9D9D9'
XL_LTBLUE = 'FFDEEAF1'
XL_GREEN  = 'FFE2EFDA'


def iter_pdf_payloads(files):
    """Yield ``(name, pdf_bytes, email_subject)`` for each uploaded file.

    Accepts the mixed uploads the fax sections take: bare fax ``.pdf`` files
    pass straight through (subject ``''``); ``.msg`` Outlook emails are
    unpacked to their first PDF attachment, with the email subject carried
    along for PO-number fallbacks. Unreadable emails and emails without a
    PDF attachment are warned about and skipped — shared by the MSG and
    TK EU sections, which previously each had their own copy of this loop.
    """
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        for uf in files:
            if uf.name.lower().endswith('.pdf'):
                yield uf.name, bytes(uf.getbuffer()), ''
                continue

            import extract_msg
            msg_path = os.path.join(tmp, uf.name)
            with open(msg_path, 'wb') as f:
                f.write(uf.getbuffer())
            try:
                msg = extract_msg.openMsg(msg_path)
            except Exception as exc:
                st.warning(f"Could not open {uf.name}: {exc}")
                continue

            pdf_data = None
            for att in msg.attachments:
                if (att.longFilename or att.shortFilename or '').lower().endswith('.pdf'):
                    pdf_data = att.data
                    break
            if pdf_data is None:
                st.warning(f"No PDF attachment in {uf.name} — skipped.")
                continue

            yield uf.name, pdf_data, (msg.subject or '')


def drop_stale_results(results_key: str, sig_key: str, sig: tuple):
    """Return current results for *results_key*, dropping them first if the
    uploader's file set changed since extraction (signature mismatch) — a
    swapped selection must not display/download the previous batch."""
    results = st.session_state.get(results_key)
    if results and st.session_state.get(sig_key) != sig:
        st.session_state[results_key] = None
        results = None
    return results


_SIZE_CODES = r'(?:XXS|XS|XXL|XL|[123]XL|[123]X|OSFM|OSM|OSF|OS|S|M|L)'
_FIRST_RE   = re.compile(
    rf'^(\d{{3}})\s+(\S+)\s+(.+?)\s+({_SIZE_CODES})\s+(\d+)\s+(\d{{12,13}})\s+([\d.]+)'
)
_CONT_RE    = re.compile(rf'^({_SIZE_CODES})\s+(\d+)\s+(\d{{12,13}})')

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
