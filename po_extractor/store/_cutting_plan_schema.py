"""Schema for uploaded cutting plans and their PO links.

Three tables:
  - ``cutting_plans``         — one row per uploaded plan file (summary columns
    for the list view, the full parse as JSON, and the original bytes so the
    file the factory sent can always be handed back unchanged)
  - ``cutting_plan_links``    — many-to-many, down to the style: a plan
    covers one or more POs and specific styles inside them, and a PO can be
    re-cut under a later plan
  - ``cutting_plan_materials`` — one row per fabric in the plan, so shell and
    lining consumption stay separate (they are different fabrics at different
    widths; a combined metre count means nothing)
  - ``cutting_plan_demands``  — the plan's colour/size matrix, flattened, so a
    plan can be compared against PO quantities in SQL instead of by unpacking
    JSON

``parsed_json`` is the source of truth for re-emitting a plan in the standard
layout; the summary columns exist only so the list view and PO-coverage checks
don't have to parse every plan's JSON.
"""
from __future__ import annotations

# Which PO module a link's keys belong to.  Sky East is the only source today;
# the column exists so GIII POs can be linked later without a migration.
SOURCE_SKY_EAST = "sky_east"

_CUTTING_PLAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS cutting_plans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_name       TEXT NOT NULL,              -- 'Order name' from the file
    client          TEXT DEFAULT '',
    operator        TEXT DEFAULT '',            -- 'Cut plan operator'
    plan_date       TEXT DEFAULT '',
    plan_time       TEXT DEFAULT '',
    source_file     TEXT DEFAULT '',            -- original upload filename
    source_hash     TEXT DEFAULT '',            -- sha256 of the bytes (re-upload guard)
    plan_format     TEXT DEFAULT 'optitex',
    styles          TEXT DEFAULT '',            -- comma-joined style names
    colors          TEXT DEFAULT '',            -- comma-joined colour names
    materials       TEXT DEFAULT '',            -- comma-joined material names
    order_qty       INTEGER DEFAULT 0,          -- demand total, per style
    cut_qty         INTEGER DEFAULT 0,          -- achieved total, per style
    total_tables    INTEGER DEFAULT 0,
    total_markers   INTEGER DEFAULT 0,
    fabric_length_m REAL    DEFAULT 0,          -- summed across materials
    efficiency_pct  REAL    DEFAULT 0,          -- fabric-length-weighted mean
    notes           TEXT DEFAULT '',
    parsed_json     TEXT DEFAULT '',            -- full parse (drives the export)
    file_blob       BLOB,                       -- original file, for re-download
    uploaded_at     TEXT,
    uploaded_by     TEXT
);

-- ``style`` is the style as the PO names it, not as the plan names it: the
-- plan carries CAD style names (S24DTR003) while the PO carries the client's
-- style codes (TP5016), and nothing in either file connects the two. The link
-- is where that mapping is recorded. '' means the whole PO.
CREATE TABLE IF NOT EXISTS cutting_plan_links (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id   INTEGER NOT NULL,
    source    TEXT NOT NULL DEFAULT 'sky_east',
    pc_no     TEXT DEFAULT '',
    po_no     TEXT DEFAULT '',
    style     TEXT DEFAULT '',
    linked_at TEXT,
    linked_by TEXT,
    UNIQUE(plan_id, source, pc_no, po_no, style)
);
CREATE INDEX IF NOT EXISTS idx_cpl_plan  ON cutting_plan_links(plan_id);
CREATE INDEX IF NOT EXISTS idx_cpl_pc    ON cutting_plan_links(pc_no);
CREATE INDEX IF NOT EXISTS idx_cpl_po    ON cutting_plan_links(po_no);
CREATE INDEX IF NOT EXISTS idx_cpl_style ON cutting_plan_links(style);

-- One row per fabric. Kept out of the plan row on purpose: a plan's shell and
-- lining are different fabrics at different cuttable widths, so a single
-- summed metre count or averaged efficiency across them is not a number
-- anyone can act on.
CREATE TABLE IF NOT EXISTS cutting_plan_materials (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id         INTEGER NOT NULL,
    seq             INTEGER NOT NULL DEFAULT 0,   -- order within the plan
    material        TEXT DEFAULT '',
    width_cm        REAL,
    length_cm       REAL,
    spreading       TEXT DEFAULT '',
    n_markers       INTEGER DEFAULT 0,
    total_tables    INTEGER DEFAULT 0,
    min_plies       INTEGER,
    max_plies       INTEGER,
    total_plies     INTEGER DEFAULT 0,            -- summed over the spreads
    cut_qty         INTEGER DEFAULT 0,
    fabric_length_m REAL,
    efficiency_pct  REAL,
    cut_length_m    REAL,
    cost            REAL
);
CREATE INDEX IF NOT EXISTS idx_cpm_plan     ON cutting_plan_materials(plan_id);
CREATE INDEX IF NOT EXISTS idx_cpm_material ON cutting_plan_materials(material);

CREATE TABLE IF NOT EXISTS cutting_plan_demands (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    style   TEXT DEFAULT '',
    color   TEXT DEFAULT '',
    size    TEXT DEFAULT '',
    qty     INTEGER DEFAULT 0,      -- ordered (Order demands block)
    cut_qty INTEGER DEFAULT 0       -- achieved (Solution block, 'Real' row)
);
CREATE INDEX IF NOT EXISTS idx_cpd_plan ON cutting_plan_demands(plan_id);
"""
