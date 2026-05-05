"""Sky East tab — shared schema helpers and Excel-writer wrappers."""
from __future__ import annotations
import streamlit as st
from po_extractor.ui_helpers import (
    live_label_for,
    load_live_schema, schema_seed_rows,
    parse_fabric_mapping_rows as _parse_fabric_mapping_rows,
    write_wash_label_excel as _write_wash_label_excel_impl,
    write_dual_header_excel as _write_dual_header_excel_impl,
    get_dual_header as _get_dual_header_impl,
)
from po_extractor.ui_helpers.fabric_mapping_template import generate_fabric_mapping_template

# Sky East uses the same shared template as GIII
_generate_se_fabric_mapping_template = generate_fabric_mapping_template

# Schema cache (module-local; re-uses same TTL pattern as app.py)
from po_extractor.config import SCHEMA_PATH as _SCHEMA_PATH, CACHE_TTL_SECONDS


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def _cached_schema() -> list[dict]:
    rows = load_live_schema(_SCHEMA_PATH)
    return rows if rows else schema_seed_rows()


def live_label(db_col: str, fallback: str | None = None) -> str:
    return live_label_for(_cached_schema(), db_col, fallback)


# ---------------------------------------------------------------------------
# Local wrappers for ui_helpers Excel writers
# ---------------------------------------------------------------------------

def _get_dual_header() -> list[tuple[str, str, str]]:
    return _get_dual_header_impl(live_label)


def _write_wash_label_excel(
    df_enriched: "pd.DataFrame",
    image_cache: dict,
    fabric_parts_by_style: dict | None = None,
    styles: list[str] | None = None,
) -> bytes:
    return _write_wash_label_excel_impl(df_enriched, image_cache, fabric_parts_by_style,
                                        styles=styles)


def _write_dual_header_excel(
    df_enriched: "pd.DataFrame",
    sheet_name: str,
    writer,
    image_cache: dict | None = None,
) -> None:
    _write_dual_header_excel_impl(
        df_enriched, sheet_name, writer, image_cache, label_for=live_label
    )


# ---------------------------------------------------------------------------
# Fabric mapping file parser (local -- pure openpyxl)
# ---------------------------------------------------------------------------

def _parse_fabric_mapping_file(path: str) -> dict:
    """Parse a filled-in style-fabric mapping file; returns {style: [FabricPart]}."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()
    return _parse_fabric_mapping_rows(all_rows)


def _parse_fabric_mapping_bytes(raw_bytes: bytes) -> dict:
    """Parse a style-fabric mapping from raw bytes (e.g. UploadedFile.getvalue()).

    Accepts the same file format as ``_parse_fabric_mapping_file`` but takes
    bytes instead of a path, so no temp file is needed for Streamlit uploads.
    Returns ``{style: [FabricPart, ...]}``.
    """
    import io
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()
    return _parse_fabric_mapping_rows(all_rows)
