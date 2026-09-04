"""Schema for fabric presentation sheets (面料推荐单 / HHN Presentation).

Three tables:

  - ``fabric_presentations``      — one row per sheet built for a customer:
    who it is for, when, which quoting parameters were used, and the QR
    token that identifies it
  - ``fabric_presentation_lines`` — the fabrics chosen for that sheet, with
    their prices **snapshotted** at build time
  - ``fabric_presentation_scans`` — one row per QR scan, so it is always
    answerable when a sheet went out and who looked at it

Why prices are snapshotted rather than read live from ``fabric_master``:
a quote that was sent to a customer in May must not silently change when
somebody edits a cost in June.  The sheet is a record of what was quoted,
so the numbers it was built from are stored with it.

The quoting parameters (markup, FX rate, rounding step) are stored per
sheet for the same reason — ``1.1 / 6.7 / 0.05`` are today's values, and
an FX rate in particular will drift.  Storing them makes any past quote
reproducible.
"""
from __future__ import annotations

_FABRIC_PRESENTATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS fabric_presentations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    token         TEXT NOT NULL UNIQUE,     -- QR payload, URL-safe
    title         TEXT DEFAULT '',          -- sheet name, e.g. 'GIII-SWIMMING'
    customer      TEXT DEFAULT '',          -- 'GIII'
    season        TEXT DEFAULT '',
    submission_date TEXT DEFAULT '',        -- as printed on the sheet
    fabric_type   TEXT DEFAULT '',          -- HHN-Initiated / Client-Initiated

    -- Quoting parameters actually used, so the sheet is reproducible.
    markup        REAL DEFAULT 1.1,         -- ×1.1 = +10%
    fx_rate       REAL DEFAULT 6.7,         -- RMB per USD
    round_step    REAL DEFAULT 0.05,        -- CEILING step, in USD

    created_at    TEXT,
    created_by    TEXT DEFAULT '',
    notes         TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_fpres_token    ON fabric_presentations(token);
CREATE INDEX IF NOT EXISTS idx_fpres_customer ON fabric_presentations(customer);

CREATE TABLE IF NOT EXISTS fabric_presentation_lines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    presentation_id INTEGER NOT NULL,
    line_no         INTEGER DEFAULT 0,      -- the printed NO. column

    quality_no      TEXT DEFAULT '',        -- HHN_Fabric# → fabric_master key
    style           TEXT DEFAULT '',        -- per-sheet, not a fabric property
    season          TEXT DEFAULT '',

    -- Snapshot of the fabric's properties as printed.
    content         TEXT DEFAULT '',        -- composition_en
    description     TEXT DEFAULT '',        -- structure_en
    weight_gsm      REAL,
    width_in        TEXT DEFAULT '',        -- '63/61' (full/cuttable)
    moq_y           REAL,
    mcq_y           REAL,

    -- Snapshot of price at build time, both forms.
    price_rmb_m     REAL,                   -- internal cost, RMB per metre
    price_usd_y     REAL,                   -- quoted price, USD per yard

    FOREIGN KEY (presentation_id) REFERENCES fabric_presentations(id)
);

CREATE INDEX IF NOT EXISTS idx_fpline_pres    ON fabric_presentation_lines(presentation_id);
CREATE INDEX IF NOT EXISTS idx_fpline_quality ON fabric_presentation_lines(quality_no);

CREATE TABLE IF NOT EXISTS fabric_presentation_scans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    presentation_id INTEGER NOT NULL,
    scanned_at      TEXT NOT NULL,
    client_ip       TEXT DEFAULT '',
    user_agent      TEXT DEFAULT '',

    FOREIGN KEY (presentation_id) REFERENCES fabric_presentations(id)
);

CREATE INDEX IF NOT EXISTS idx_fpscan_pres ON fabric_presentation_scans(presentation_id);
CREATE INDEX IF NOT EXISTS idx_fpscan_at   ON fabric_presentation_scans(scanned_at);
"""
