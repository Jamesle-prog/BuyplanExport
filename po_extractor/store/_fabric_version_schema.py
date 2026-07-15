"""Schema DDL and diff-field definitions for fabric_master versioning.

Layered on top of fabric_master (see _fabric_master_schema.py): every
import_from_xlsx() call becomes a new "version" -- fabric_versions holds
per-upload metadata, fabric_master_snapshot holds full historical row data
for the current + 3 most recent prior versions (older snapshot DATA is
pruned; the metadata/diff rows below are never pruned), and
fabric_version_diff holds the field-level incremental diff between each
version and the one immediately before it.
"""
from __future__ import annotations

_VERSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS fabric_versions (
    version_id   INTEGER PRIMARY KEY,
    created_at   TEXT NOT NULL,
    uploaded_by  TEXT NOT NULL DEFAULT 'system',
    source_file  TEXT,
    row_count    INTEGER NOT NULL DEFAULT 0,
    inserted     INTEGER NOT NULL DEFAULT 0,
    updated      INTEGER NOT NULL DEFAULT 0,
    skipped      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fabric_master_snapshot (
    version_id        INTEGER NOT NULL,
    quality_no        TEXT NOT NULL,
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
    source_file       TEXT,
    PRIMARY KEY (version_id, quality_no)
);
CREATE INDEX IF NOT EXISTS idx_fms_erp ON fabric_master_snapshot(version_id, erp_code);

CREATE TABLE IF NOT EXISTS fabric_version_diff (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id  INTEGER NOT NULL,   -- the NEW version this diff produced
    quality_no  TEXT NOT NULL,
    change_type TEXT NOT NULL,      -- 'added' | 'removed' | 'changed'
    field       TEXT,               -- NULL for added/removed; column name for changed
    old_value   TEXT,
    new_value   TEXT,
    diffed_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fvd_version ON fabric_version_diff(version_id, quality_no);
"""

# fabric_master columns snapshotted verbatim -- matches fabric_master_snapshot's
# column order above (quality_no first, matching _fabric_master_schema._SCHEMA).
_ALL_FABRIC_COLUMNS = (
    "quality_no", "erp_code", "supplier_no", "supplier", "composition_en",
    "composition_cn", "yarn_count", "structure_en", "structure_cn",
    "weight_gsm", "full_width_cm", "cuttable_width_cm", "full_width_in",
    "cuttable_width_in", "dyeing_process", "moq_y", "moq_setup_fee",
    "mcq_y", "mcq_small_fee", "is_in_stock", "spot_price_kg", "spot_price_m",
    "cost_per_kg", "cost_per_m", "quote_date", "shrinkage_rate",
    "short_rate", "notes_cn", "notes_en", "quote_history", "display_key",
    "imported_at", "source_file",
)

# Fields compared when diffing one version against the previous one. Excluded:
# quality_no (identity, not a "changed field"), imported_at / source_file
# (import metadata that changes on every re-import regardless of real edits --
# would false-positive every untouched row as "changed"), and display_key
# (fully derived from composition_en/weight_gsm/cuttable_width_cm, already
# tracked -- diffing it too is pure redundant noise).
_DIFF_FIELDS = tuple(
    c for c in _ALL_FABRIC_COLUMNS
    if c not in ("quality_no", "imported_at", "source_file", "display_key")
)

# How many versions' full row-snapshot data stay queryable: the current one
# plus this many immediately-prior versions. Older snapshot DATA is pruned;
# fabric_versions / fabric_version_diff rows are kept forever regardless.
_SNAPSHOT_KEEP_VERSIONS = 4   # current + 3 previous
