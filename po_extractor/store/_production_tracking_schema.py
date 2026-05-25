"""SQLite schema for the production & delivery tracking table."""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS production_tracking (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number       TEXT    NOT NULL,
    style           TEXT,
    factory         TEXT,
    ex_factory_date TEXT,
    etd             TEXT,
    eta             TEXT,
    carrier         TEXT,
    vessel          TEXT,
    bl_number       TEXT,
    status          TEXT    DEFAULT 'Confirmed',
    notes           TEXT,
    updated_at      TEXT,
    UNIQUE(po_number, style)
);
"""

STATUS_OPTIONS = [
    'Confirmed',
    'In Production',
    'Ex-Factory',
    'On Water',
    'Delivered',
    'Delayed',
]
