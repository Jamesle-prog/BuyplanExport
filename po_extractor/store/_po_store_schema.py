"""SQLite schema DDL and migration constants for POStore."""
from __future__ import annotations

_SCHEMA = """
CREATE TABLE IF NOT EXISTS po_metadata (
    po_number        TEXT PRIMARY KEY,
    company          TEXT,
    style            TEXT,
    factory          TEXT,
    country_of_origin TEXT,
    xport_date       TEXT,
    issue_date       TEXT,
    version          TEXT,
    division_code    TEXT,
    division_name    TEXT,
    source_format    TEXT,
    file_name        TEXT,
    extracted_at     TEXT,
    parser_version   TEXT,
    parse_confidence INTEGER,
    validation_status TEXT,
    revision_reason  TEXT,
    source_file_hash TEXT,
    processed_by     TEXT,
    external_quote_id TEXT,
    source_module    TEXT,
    integration_status TEXT,
    content_hash     TEXT
);

CREATE TABLE IF NOT EXISTS po_size_rows (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number    TEXT NOT NULL,
    style        TEXT,
    color        TEXT,
    size         TEXT,
    units        INTEGER,
    upc          TEXT,
    extracted_at TEXT,
    UNIQUE(po_number, style, color, size)
);

-- Full version history: every superseded version is archived here
CREATE TABLE IF NOT EXISTS po_version_history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number        TEXT NOT NULL,
    style            TEXT,
    factory          TEXT,
    country_of_origin TEXT,
    xport_date       TEXT,
    issue_date       TEXT,
    version          TEXT,
    division_code    TEXT,
    division_name    TEXT,
    source_format    TEXT,
    file_name        TEXT,
    extracted_at     TEXT,
    archived_at      TEXT,
    total_units      INTEGER
);

CREATE TABLE IF NOT EXISTS po_exceptions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number    TEXT,
    file_name    TEXT,
    company      TEXT,
    status       TEXT DEFAULT 'pending',
    reason       TEXT,
    raw_text_snippet TEXT,
    created_at   TEXT,
    updated_at   TEXT,
    processed_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_pom_company    ON po_metadata(company);
CREATE INDEX IF NOT EXISTS idx_psr_po_number  ON po_size_rows(po_number);
CREATE INDEX IF NOT EXISTS idx_pvh_po_number  ON po_version_history(po_number);
CREATE INDEX IF NOT EXISTS idx_poe_status     ON po_exceptions(status);

-- Universal multi-fabric table (all client types write here)
CREATE TABLE IF NOT EXISTS style_fabric_parts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,     -- 'sky_east' | 'giii' | 'reference'
    style       TEXT    NOT NULL,
    combo_idx   INTEGER NOT NULL DEFAULT 0,  -- 0-based index of the fabric combination
                                              -- (file row); parts in the same row share
                                              -- the same combo_idx.
    seq         INTEGER NOT NULL,     -- 1-based position within the combination
    body_part   TEXT    DEFAULT '',   -- "大身", "网布", "Main Body", "Lining", etc.
    hhn_no      TEXT    DEFAULT '',   -- "HHN-JA-01715"
    composition TEXT    DEFAULT '',   -- "92% Polyester 8% Elastane"
    weight_gsm  INTEGER DEFAULT 0,
    width_cm    INTEGER DEFAULT 0,
    updated_at  TEXT,
    UNIQUE(source, style, combo_idx, seq)
);
CREATE INDEX IF NOT EXISTS idx_sfp_style ON style_fabric_parts(style);

-- HHN fabric number → composition/weight/width cache (populated from 洗标 file)
-- Used by all pipelines to enrich fabric codes without re-uploading the composition file.
CREATE TABLE IF NOT EXISTS fabric_hhn_cache (
    hhn_no      TEXT PRIMARY KEY,
    composition TEXT DEFAULT '',
    weight_gsm  INTEGER DEFAULT 0,
    width_cm    INTEGER DEFAULT 0,
    updated_at  TEXT
);
"""

# Columns added after initial release — migrated in POStore.__init__
_NEW_METADATA_COLS: list[tuple[str, str]] = [
    ("parser_version",    "TEXT"),
    ("parse_confidence",  "INTEGER"),
    ("validation_status", "TEXT"),
    ("revision_reason",   "TEXT"),
    ("source_file_hash",  "TEXT"),
    ("processed_by",      "TEXT"),
    ("external_quote_id", "TEXT"),
    ("source_module",     "TEXT"),
    ("integration_status","TEXT"),
    ("content_hash",      "TEXT"),
]
