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
    archived_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_sei_pc_no  ON sky_east_items(pc_no);
CREATE INDEX IF NOT EXISTS idx_seih_pc_no ON sky_east_item_history(pc_no);
"""


def _item_sizes_dict(row: dict) -> dict:
    """Extract size quantities from a DB row dict."""
    return {
        "XS":  row.get("xs",  0) or 0,
        "S":   row.get("s",   0) or 0,
        "M":   row.get("m",   0) or 0,
        "L":   row.get("l",   0) or 0,
        "XL":  row.get("xl",  0) or 0,
        "2XL": row.get("xxl", 0) or 0,
    }


def _sizes_equal(sizes_a: dict, sizes_b: dict) -> bool:
    """Compare two size dicts, treating missing keys as 0."""
    all_keys = set(sizes_a) | set(sizes_b)
    return all((sizes_a.get(k, 0) or 0) == (sizes_b.get(k, 0) or 0) for k in all_keys)
