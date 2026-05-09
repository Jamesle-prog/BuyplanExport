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
import json as _json
_ROOT = _Path(__file__).parent.parent   # project root

DATA_DIR    = str(_ROOT / "data")
SCHEMA_PATH = str(_ROOT / "data" / "output_schema.json")
DB_PATH     = str(_ROOT / "data" / "po_history.db")

# ── Centralised Fabric Master DB ──────────────────────────────────────────────
# Resolution order (first non-empty wins):
#   1. FABRIC_DB_PATH environment variable
#   2. fabric_db_path key in data/fabric_config.json
#   3. Default: data/fabric_master.db (sibling to po_history.db)
#
# Other applications that want to read the same fabric master just need to
# point their FabricMasterStore (or FabricMasterClient) at this path.
_FABRIC_CONFIG_FILE = str(_ROOT / "data" / "fabric_config.json")


def get_fabric_db_path() -> str:
    """Return the fabric master DB path, re-reading fabric_config.json each call.

    Calling this function (rather than reading the module-level constant)
    means the admin can change the path via the Settings UI and the new path
    takes effect on the next ``get_fabric_master_store()`` call without an
    app restart.
    """
    import os as _os
    env = _os.environ.get("FABRIC_DB_PATH", "").strip()
    if env:
        return env
    try:
        with open(_FABRIC_CONFIG_FILE, encoding="utf-8") as _fh:
            _cfg = _json.load(_fh)
        path = (_cfg.get("fabric_db_path") or "").strip()
        if path:
            return path
    except FileNotFoundError:
        pass  # No config yet — first run.
    except (OSError, _json.JSONDecodeError) as _exc:
        # Corrupt config or permissions issue — surface it so the user can fix.
        import warnings as _w
        _w.warn(f"[fabric_config] could not read {_FABRIC_CONFIG_FILE}: {_exc!r}")
    return str(_ROOT / "data" / "fabric_master.db")


def save_fabric_db_path(path: str) -> None:
    """Persist *path* to fabric_config.json so it survives restarts."""
    import os as _os
    _os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(_FABRIC_CONFIG_FILE, encoding="utf-8") as _fh:
            cfg = _json.load(_fh)
    except FileNotFoundError:
        cfg = {}
    except (OSError, _json.JSONDecodeError):
        cfg = {}
    cfg["fabric_db_path"] = path.strip()
    with open(_FABRIC_CONFIG_FILE, "w", encoding="utf-8") as _fh:
        _json.dump(cfg, _fh, indent=2, ensure_ascii=False)


# Module-level constant for code that needs a fixed import-time path.
# Most internal code should call get_fabric_db_path() instead.
FABRIC_DB_PATH: str = get_fabric_db_path()

# ── Cache TTL ─────────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = 60   # @st.cache_data TTL used by schema loaders

# SMTP settings live in auth.smtp_settings (admin-editable from the UI,
# persisted to auth/smtp_settings.json, with PO_SMTP_* env-var fallback).

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
