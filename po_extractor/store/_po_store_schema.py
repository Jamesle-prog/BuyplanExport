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
    content_hash     TEXT,
    -- Commercial fields added v1.9.0
    buyer            TEXT,
    seller           TEXT,
    ship_to          TEXT,
    destination_code TEXT,
    incoterm         TEXT,
    origin_port      TEXT,
    issued_by        TEXT,
    discount         TEXT,
    payment_terms    TEXT,
    approval_status  TEXT,
    season           TEXT,
    customer         TEXT,
    style_description TEXT,
    style_group      TEXT,
    unit_cost        TEXT,
    line_extended_cost TEXT,
    factory_ship_date TEXT,
    packaging        TEXT
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

-- Persistent copy of 大货进度表 (HHN Contract Progress) rows — uploaded once via
-- the Fabric Mapping tab's "HHN Contract Progress" section, then reused by
-- every buy-plan run without re-uploading. Row identity is (pc_no, style,
-- color) — the same key the app already uses to match a contract line, via
-- pc_no_norm/style_norm/color_norm (see progress_lookup.py's
-- _norm_key/_normalise_color) so re-uploading a file with e.g. differently
-- cased PC numbers still overwrites the same row instead of duplicating it.
-- No IMAGE column — pictures aren't persisted here (see comments below).
CREATE TABLE IF NOT EXISTS progress_records (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT    NOT NULL,     -- 'sky_east' | other companies later
    contract_no   TEXT    DEFAULT '',   -- 合同号
    pc_no         TEXT    DEFAULT '',   -- 客人PC NO / 所在PO (raw display form)
    pc_no_norm    TEXT    NOT NULL DEFAULT '',  -- normalised match key
    style         TEXT    NOT NULL,     -- 款式, display form e.g. "ZLD060/S24DTR003"
    style_norm    TEXT    NOT NULL,     -- normalised match key (ProgressLookup's internal key)
    brand         TEXT    DEFAULT '',   -- BRAND
    test_note     TEXT    DEFAULT '',   -- 测试
    color_summary TEXT    DEFAULT '',   -- 色汇总英文中文色号色卡本
    color_en      TEXT    DEFAULT '',   -- 英文颜色 (raw display form)
    color_norm    TEXT    DEFAULT '',   -- cleaned match key (progress_lookup.clean_color_for_lookup)
    color_cn      TEXT    DEFAULT '',   -- 中文颜色
    color_code    TEXT    DEFAULT '',   -- 中文颜色代码
    label_color   TEXT    DEFAULT '',   -- 主标颜色
    ex_fty_date   TEXT    DEFAULT '',   -- PO离厂日期
    launch_date   TEXT    DEFAULT '',   -- Launch date
    qty           TEXT    DEFAULT '',   -- 数量
    remarks       TEXT    DEFAULT '',   -- 备注
    zalando_po    TEXT    DEFAULT '',   -- PO#
    fabric_detail TEXT    DEFAULT '',   -- FABRICDETAIL
    updated_at    TEXT,
    UNIQUE(source, pc_no_norm, style_norm, color_norm)
);
CREATE INDEX IF NOT EXISTS idx_pr_style ON progress_records(source, style_norm);
"""

# Columns added after initial release — migrated in POStore.__init__
_NEW_METADATA_COLS: list[tuple[str, str]] = [
    ("parser_version",     "TEXT"),
    ("parse_confidence",   "INTEGER"),
    ("validation_status",  "TEXT"),
    ("revision_reason",    "TEXT"),
    ("source_file_hash",   "TEXT"),
    ("processed_by",       "TEXT"),
    ("external_quote_id",  "TEXT"),
    ("source_module",      "TEXT"),
    ("integration_status", "TEXT"),
    ("content_hash",       "TEXT"),
    # v1.9.0 commercial fields
    ("buyer",              "TEXT"),
    ("seller",             "TEXT"),
    ("ship_to",            "TEXT"),
    ("destination_code",   "TEXT"),
    ("incoterm",           "TEXT"),
    ("origin_port",        "TEXT"),
    ("issued_by",          "TEXT"),
    ("discount",           "TEXT"),
    ("payment_terms",      "TEXT"),
    ("approval_status",    "TEXT"),
    ("season",             "TEXT"),
    ("customer",           "TEXT"),
    ("style_description",  "TEXT"),
    ("style_group",        "TEXT"),
    ("unit_cost",          "TEXT"),
    ("line_extended_cost", "TEXT"),
    ("factory_ship_date",  "TEXT"),
    ("packaging",          "TEXT"),
    # v1.12.0 — KL-format fields
    ("hanger",             "TEXT"),
    ("description_code",   "TEXT"),
    # v1.13.0 — multi-brand commercial fields
    ("msrp",               "TEXT"),
    ("cpo",                "TEXT"),
    ("fabric",             "TEXT"),
]
