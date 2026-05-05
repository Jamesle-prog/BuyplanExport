"""Shared constants and regex patterns."""

SIZE_ORDER = [
    'PXS', 'PS', 'PM', 'PL', 'PXL', 'P1X', 'P2X', 'P3X', 'P2XL', 'P3XL',
    'XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL',
    '0X', '1X', '2X', '3X', '4X',
]
SIZE_INFO = '|'.join(SIZE_ORDER)
SIZE_PATTERN = rf'({SIZE_INFO})'

# Legacy G-III patterns
PO_NUMBER_PATTERN = r'PO NUMBER\s+(\w+)'
STYLE_PATTERN = r'STYLE#\s+(.+)'
COLOR_PATTERN = r'(\w+(?:/\w+)+|\w+/\w+(?:\s\w+)?)'
UNITS_PATTERN = r'(\d+)\s+(\d{12})'
FULL_PATTERN = rf'{COLOR_PATTERN}\s+{SIZE_PATTERN}\s+{UNITS_PATTERN}'
LN_START = "LN#"
VENDOR_PATTERN = r'VENDOR\s+(\w+)'
ISSUED_BY_PATTERN = r'ISSUED BY\s+([a-zA-Z0-9.]+)'
PO_DATE_PATTERN = r'PO DATE\s+(\d{1,2}/\d{1,2}/\d{2,4})'
VEND_CNTRY_PATTERN = r'VEND CNTRY\s+(\w+(?:\s*-\s*\w+)?)'
FACTORY_PATTERN = r'FACTORY\s+(\d+)\s*-\s*([A-Z]+(?:\s[A-Z]+)*)(?=\s{2,}|$)'
HANGER_PATTERN = r'HANGER'
CNTRY_OF_ORIGIN_PATTERN = r'CNTRY OF ORIGIN\s+(\w+)'

FORMAT_INFOR_NEXUS = "infor_nexus"
FORMAT_LEGACY = "legacy_giii"
FORMAT_EXCEL_ZALANDO = "excel_zalando"
FORMAT_UNKNOWN = "unknown"

# ── Paths (resolved relative to this file: po_extractor/ → project root) ─────
from pathlib import Path as _Path
_ROOT = _Path(__file__).parent.parent   # project root

DATA_DIR    = str(_ROOT / "data")
SCHEMA_PATH = str(_ROOT / "data" / "output_schema.json")
DB_PATH     = str(_ROOT / "data" / "po_history.db")

# ── Cache TTL ─────────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = 60   # @st.cache_data TTL used by schema loaders

# ── Excel colour palette (6-char RGB; openpyxl prepends FF alpha) ─────────────
EXCEL_PALETTE: dict[str, str] = {
    "black":       "000000",
    "white":       "FFFFFF",
    "yellow":      "FFFF00",
    "light_grey":  "F2F2F2",
    "border_grey": "AAAAAA",
    "hdr_blue":    "4472C4",   # hhp / giii buy-plan header
    "alt_blue":    "D9E1F2",   # hhp / giii alt row
    "wash_hdr":    "1F4E79",   # wash-label header
    "wash_alt":    "EBF3FB",   # wash-label alt row
}

# ── Format-detection keywords ─────────────────────────────────────────────────
# Used by po_extractor/detectors/format_detector.py
FORMAT_DETECTION_KEYWORDS: dict[str, list] = {
    # Any one of these strings triggers FORMAT_INFOR_NEXUS (primary)
    "infor_nexus_primary":  ["Infor Nexus", "Powered by Infor Nexus"],
    # ALL three must be present to trigger FORMAT_LEGACY
    "legacy_giii_required": ["PO NUMBER", "STYLE#", "LN#"],
    # Any one of these triggers FORMAT_INFOR_NEXUS (fallback)
    "infor_nexus_fallback": ["Order Number", "BUYER"],
}
