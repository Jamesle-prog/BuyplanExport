"""Schema DDL, header aliases, column map, and helper functions for FabricMasterStore."""
from __future__ import annotations

from ..utils.normalize import normalize_header

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fabric_master (
    quality_no        TEXT PRIMARY KEY,
    erp_code          TEXT,
    supplier_no       TEXT,
    supplier          TEXT,
    composition_en    TEXT,
    composition_cn    TEXT,
    yarn_count        TEXT,
    structure_en      TEXT,
    structure_cn      TEXT,
    weight_gsm        REAL,
    full_width_cm     REAL,
    cuttable_width_cm REAL,
    full_width_in     REAL,
    cuttable_width_in REAL,
    dyeing_process    TEXT,
    moq_y             REAL,
    moq_setup_fee     REAL,
    mcq_y             REAL,
    mcq_small_fee     REAL,
    is_in_stock       TEXT,
    spot_price_kg     REAL,
    spot_price_m      REAL,
    cost_per_kg       REAL,
    cost_per_m        REAL,
    quote_date        TEXT,
    shrinkage_rate    REAL,
    short_rate        REAL,
    notes_cn          TEXT,
    notes_en          TEXT,
    quote_history     TEXT,
    display_key       TEXT,
    imported_at       TEXT,
    source_file       TEXT
);

CREATE INDEX IF NOT EXISTS idx_fm_erp_code ON fabric_master(erp_code);
"""

# ---------------------------------------------------------------------------
# Dynamic header detection for the 'all' sheet
# ---------------------------------------------------------------------------
# Each entry: (field_name, [alias_strings])
# Aliases are matched case-insensitively after stripping whitespace and
# normalising full-width parentheses.

_HEADER_ALIASES: list[tuple[str, list[str]]] = [
    ("quality_no",        ["公司面料编号", "面料编号", "quality no", "quality_no"]),
    ("erp_code",          ["erp编码", "erp code", "erp_code", "erp"]),
    ("supplier_no",       ["供应商面料编号", "supplier no", "supplier_no", "supplierno"]),
    ("supplier",          ["供应商", "supplier"]),
    ("composition_en",    ["面料成分(英文)", "成分英文", "composition(en)", "composition en",
                           "composition_en"]),
    ("composition_cn",    ["面料成分(中文)", "成分中文", "composition(cn)", "composition cn",
                           "composition_cn"]),
    ("yarn_count",        ["纱支", "yarn count", "yarn_count"]),
    ("structure_en",      ["面料结构(英文)", "结构英文", "structure(en)", "structure en",
                           "structure_en"]),
    ("structure_cn",      ["面料结构(中文)", "结构中文", "structure(cn)", "structure cn",
                           "structure_cn"]),
    ("weight_gsm",        ["克重(gsm)", "gsm", "克重", "weight(gsm)", "weight gsm",
                           "weight_gsm"]),
    ("cuttable_width_cm", ["有效门幅(cm)", "有效门幅", "cuttable width(cm)",
                           "cuttable width cm", "cuttable_width_cm"]),
    ("full_width_cm",     ["全门幅(cm)", "全门幅", "full width(cm)", "full width cm",
                           "full_width_cm"]),
    ("full_width_in",     ["全门幅(inch)", "全门幅(in)", "full width(in)", "full width in",
                           "full_width_in"]),
    ("cuttable_width_in", ["有效门幅(inch)", "有效门幅(in)", "cuttable width(in)",
                           "cuttable width in", "cuttable_width_in"]),
    ("dyeing_process",    ["印染工艺", "dyeing", "dyeing process", "dyeing_process"]),
    ("moq_y",             ["moq(y)", "moq", "moq_y"]),
    ("moq_setup_fee",     ["上机费", "少于moq付上机费", "setup fee", "moq_setup_fee"]),
    ("mcq_y",             ["mcq(y)", "mcq", "mcq_y"]),
    ("mcq_small_fee",     ["小缸费", "少于mcq付小缸费", "small fee", "mcq_small_fee"]),
    ("is_in_stock",       ["是否有现货", "in stock", "is_in_stock"]),
    ("spot_price_kg",     ["现货价格(¥/kg)", "现货价格(/kg)", "spot price/kg",
                           "spot_price_kg"]),
    ("spot_price_m",      ["现货价格(¥/m)", "现货价格(/m)", "spot price/m",
                           "spot_price_m"]),
    ("cost_per_kg",       ["定金/成本价(¥/kg)", "定金价(¥/kg)", "cost/kg",
                           "cost_per_kg"]),
    ("cost_per_m",        ["定金/成本价(¥/m)", "定金价(¥/m)", "cost/m",
                           "cost_per_m"]),
    ("quote_date",        ["报价时间", "quote date", "quote_date"]),
    ("shrinkage_rate",    ["烫缩率", "shrinkage rate", "shrinkage", "shrinkage_rate"]),
    ("short_rate",        ["短码率", "short rate", "short_rate"]),
    ("notes_cn",          ["备注说明", "备注", "notes(cn)", "notes cn", "notes_cn"]),
    ("notes_en",          ["note", "notes(en)", "notes en", "notes_en"]),
    ("quote_history",     ["报价记录", "quote history", "quote_history"]),
]

# Fallback column positions (1-based) used when a header cannot be matched.
_COL_MAP_FALLBACK: dict[int, str] = {
    1:  "quality_no",
    2:  "erp_code",
    3:  "supplier_no",
    4:  "supplier",
    5:  "composition_en",
    6:  "composition_cn",
    7:  "yarn_count",
    8:  "structure_en",
    9:  "structure_cn",
    10: "weight_gsm",
    11: "cuttable_width_cm",
    12: "full_width_cm",
    13: "full_width_in",
    14: "cuttable_width_in",
    15: "dyeing_process",
    16: "moq_y",
    17: "moq_setup_fee",
    18: "mcq_y",
    19: "mcq_small_fee",
    20: "is_in_stock",
    21: "spot_price_kg",
    22: "spot_price_m",
    23: "cost_per_kg",
    24: "cost_per_m",
    25: "quote_date",
    26: "shrinkage_rate",
    27: "short_rate",
    28: "notes_cn",
    29: "notes_en",
    30: "quote_history",
}

_NUMERIC_FIELDS = {
    "weight_gsm", "full_width_cm", "cuttable_width_cm",
    "full_width_in", "cuttable_width_in",
    "moq_y", "moq_setup_fee", "mcq_y", "mcq_small_fee",
    "spot_price_kg", "spot_price_m",
    "cost_per_kg", "cost_per_m", "shrinkage_rate", "short_rate",
}

# Alias for the shared normalization utility (kept for backward compatibility).
_norm_header = normalize_header

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _build_col_map(ws) -> tuple[dict[str, int], list[tuple[int, str]]]:
    """Read the header row (row 1) and return ({field: col_index}, unmatched_list)."""
    alias_lookup: dict[str, str] = {}
    for field, aliases in _HEADER_ALIASES:
        for alias in aliases:
            key = _norm_header(alias)
            alias_lookup.setdefault(key, field)

    field_to_col: dict[str, int] = {}
    unmatched_headers: list[tuple[int, str]] = []

    for cell in ws[1]:
        if cell.value is None:
            continue
        raw  = str(cell.value)
        norm = _norm_header(raw)
        if norm in alias_lookup:
            field = alias_lookup[norm]
            if field not in field_to_col:
                field_to_col[field] = cell.column
        else:
            unmatched_headers.append((cell.column, raw.strip()))

    for col_idx, field in _COL_MAP_FALLBACK.items():
        field_to_col.setdefault(field, col_idx)

    return field_to_col, unmatched_headers


def _v(val) -> str:
    return "" if val is None else str(val).strip()


def _num(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _make_display_key(quality_no: str, composition_en: str,
                      weight_gsm, cuttable_width_cm) -> str:
    gsm   = str(int(weight_gsm))       if weight_gsm       else ""
    width = str(int(cuttable_width_cm)) if cuttable_width_cm else ""
    return f"{quality_no}|{composition_en}|{gsm}|{width}"
