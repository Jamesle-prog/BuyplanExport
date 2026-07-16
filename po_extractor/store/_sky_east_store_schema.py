"""Schema DDL and row-helper functions for SkyEastStore."""
from __future__ import annotations

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sky_east_contracts (
    pc_no           TEXT PRIMARY KEY,
    pc_date         TEXT,
    buyer           TEXT,
    seller          TEXT,
    currency        TEXT,
    payment_terms   TEXT,
    trade_term      TEXT,
    source_file     TEXT,
    extracted_at    TEXT,
    processed_by    TEXT,
    source_file_hash TEXT
);

CREATE TABLE IF NOT EXISTS sky_east_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pc_no           TEXT NOT NULL,
    zalando_po      TEXT,
    style           TEXT,
    config_sku      TEXT,
    article_name    TEXT,
    brand           TEXT,
    color_name      TEXT,
    colour_code     TEXT,
    launch_date     TEXT,
    fabric_item_no  TEXT,
    fabrication     TEXT,
    contract_no     TEXT,
    xs              INTEGER DEFAULT 0,
    s               INTEGER DEFAULT 0,
    m               INTEGER DEFAULT 0,
    l               INTEGER DEFAULT 0,
    xl              INTEGER DEFAULT 0,
    xxl             INTEGER DEFAULT 0,
    total_qty       INTEGER DEFAULT 0,
    fob_usd         REAL DEFAULT 0,
    total_cost_usd  REAL DEFAULT 0,
    ex_fty_date     TEXT,
    picture_id      TEXT,
    revision_reason TEXT,
    return_label    TEXT DEFAULT 'NA',
    UNIQUE(pc_no, style, color_name, zalando_po)
);

CREATE TABLE IF NOT EXISTS sky_east_item_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pc_no           TEXT NOT NULL,
    zalando_po      TEXT,
    style           TEXT,
    config_sku      TEXT,
    article_name    TEXT,
    brand           TEXT,
    color_name      TEXT,
    colour_code     TEXT,
    launch_date     TEXT,
    fabric_item_no  TEXT,
    fabrication     TEXT,
    contract_no     TEXT,
    xs              INTEGER DEFAULT 0,
    s               INTEGER DEFAULT 0,
    m               INTEGER DEFAULT 0,
    l               INTEGER DEFAULT 0,
    xl              INTEGER DEFAULT 0,
    xxl             INTEGER DEFAULT 0,
    total_qty       INTEGER DEFAULT 0,
    fob_usd         REAL DEFAULT 0,
    total_cost_usd  REAL DEFAULT 0,
    ex_fty_date     TEXT,
    picture_id      TEXT,
    revision_reason TEXT,
    return_label    TEXT DEFAULT 'NA',
    archived_at     TEXT
);

CREATE TABLE IF NOT EXISTS sky_east_color_misses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pc_no           TEXT,
    contract_no     TEXT,
    style           TEXT,
    po_no           TEXT,
    client_po_color TEXT,   -- raw client colour text, before bracket-strip/split
    attempted_color TEXT,   -- the specific component the lookup was tried with
    progress_colors TEXT,   -- 大货进度表's own colour(s) on file for this PC/style, comma-joined
    source          TEXT,   -- "progress" | "db" — which source was selected
    logged_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_sei_pc_no  ON sky_east_items(pc_no);
CREATE INDEX IF NOT EXISTS idx_seih_pc_no ON sky_east_item_history(pc_no);
CREATE INDEX IF NOT EXISTS idx_secm_pc_no ON sky_east_color_misses(pc_no);
"""


def _item_sizes_dict(row: dict) -> dict:
    """Extract size quantities from a DB row dict (canonical 6-key format)."""
    return {
        "XS":  row.get("xs",  0) or 0,
        "S":   row.get("s",   0) or 0,
        "M":   row.get("m",   0) or 0,
        "L":   row.get("l",   0) or 0,
        "XL":  row.get("xl",  0) or 0,
        "2XL": row.get("xxl", 0) or 0,
    }


# Maps DB bucket name (lowercase) → canonical display key used by _item_sizes_dict
_DB_TO_CANONICAL: dict[str, str] = {
    "xs": "XS", "s": "S", "m": "M", "l": "L", "xl": "XL", "xxl": "2XL",
}


def _normalize_sizes(sizes: dict) -> dict:
    """Collapse a raw sizes dict (any keys) into the 6 canonical keys.

    Uses SIZE_TO_DB from the parser so dynamic sizes like "1X", "2X", "XXXL"
    are bucketed correctly before any comparison or storage.

    Returns e.g. {"XS": 0, "S": 10, "M": 20, "L": 0, "XL": 5, "2XL": 3}
    """
    from ..parsers.sky_east_order import SIZE_TO_DB  # lazy — no circular import
    result: dict[str, int] = {"XS": 0, "S": 0, "M": 0, "L": 0, "XL": 0, "2XL": 0}
    for raw_key, qty in sizes.items():
        if not qty:
            continue
        bucket = SIZE_TO_DB.get(str(raw_key).strip().upper())
        if bucket:
            canonical = _DB_TO_CANONICAL[bucket]
            result[canonical] = result.get(canonical, 0) + int(qty)
    return result


def _sizes_equal(sizes_a: dict, sizes_b: dict) -> bool:
    """Compare two size dicts, treating missing keys as 0.

    Both dicts are first normalised to the 6 canonical DB keys so that raw
    parser keys (e.g. "1X", "XXXL") and canonical keys ("XL", "2XL") compare
    as equal when they map to the same DB bucket.
    """
    # Normalise only when needed: if both already look canonical, skip the
    # extra import.  A dict is "canonical" if all its keys are in the 6-key set.
    _CANONICAL = frozenset({"XS", "S", "M", "L", "XL", "2XL"})
    a_is_canonical = set(sizes_a.keys()).issubset(_CANONICAL)
    b_is_canonical = set(sizes_b.keys()).issubset(_CANONICAL)

    na = sizes_a if a_is_canonical else _normalize_sizes(sizes_a)
    nb = sizes_b if b_is_canonical else _normalize_sizes(sizes_b)

    all_keys = set(na) | set(nb)
    return all((na.get(k, 0) or 0) == (nb.get(k, 0) or 0) for k in all_keys)
