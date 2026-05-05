"""Persistent SQLite store for PO history with conflict detection.

Implementation is split across private sibling modules:
  _po_store_schema.py     — SQL DDL and migration column list
  _po_store_write.py      — SaveStatus type + write-side mixin (_WritesMixin)
  _po_store_read.py       — read-side mixin (_ReadsMixin)
  _po_store_exceptions.py — exception-queue mixin (_ExceptionsMixin)
  _po_store_fabric.py     — fabric-parts and HHN-cache mixin (_FabricMixin)
"""
from __future__ import annotations

from pathlib import Path

from .base_store import BaseSQLiteStore
from ._po_store_schema import _SCHEMA, _NEW_METADATA_COLS
from ._po_store_write import SaveStatus, _WritesMixin  # noqa: F401 (SaveStatus re-exported)
from ._po_store_read import _ReadsMixin
from ._po_store_exceptions import _ExceptionsMixin
from ._po_store_fabric import _FabricMixin


class POStore(_WritesMixin, _ReadsMixin, _ExceptionsMixin, _FabricMixin, BaseSQLiteStore):
    """Persistent SQLite store for PO history with conflict detection."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            # Migrate: add company column to existing databases
            cols = {r[1] for r in conn.execute("PRAGMA table_info(po_metadata)")}
            if "company" not in cols:
                conn.execute("ALTER TABLE po_metadata ADD COLUMN company TEXT")
            # Migrate: add traceability + placeholder columns to existing databases
            for col_name, col_type in _NEW_METADATA_COLS:
                if col_name not in cols:
                    conn.execute(
                        f"ALTER TABLE po_metadata ADD COLUMN {col_name} {col_type}"
                    )
            # Migrate: add combo_idx column to style_fabric_parts (fabric combination
            # grouping).  SQLite cannot alter a UNIQUE constraint in-place, so we
            # recreate the table with the updated schema when the column is absent.
            _sfp_cols = {r[1] for r in conn.execute("PRAGMA table_info(style_fabric_parts)")}
            if "combo_idx" not in _sfp_cols:
                conn.executescript("""
                    CREATE TABLE style_fabric_parts_new (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        source      TEXT    NOT NULL,
                        style       TEXT    NOT NULL,
                        combo_idx   INTEGER NOT NULL DEFAULT 0,
                        seq         INTEGER NOT NULL,
                        body_part   TEXT    DEFAULT '',
                        hhn_no      TEXT    DEFAULT '',
                        composition TEXT    DEFAULT '',
                        weight_gsm  INTEGER DEFAULT 0,
                        width_cm    INTEGER DEFAULT 0,
                        updated_at  TEXT,
                        UNIQUE(source, style, combo_idx, seq)
                    );
                    INSERT INTO style_fabric_parts_new
                           (id, source, style, combo_idx, seq, body_part, hhn_no,
                            composition, weight_gsm, width_cm, updated_at)
                    SELECT  id, source, style, 0,         seq, body_part, hhn_no,
                            composition, weight_gsm, width_cm, updated_at
                    FROM style_fabric_parts;
                    DROP TABLE style_fabric_parts;
                    ALTER TABLE style_fabric_parts_new RENAME TO style_fabric_parts;
                    CREATE INDEX IF NOT EXISTS idx_sfp_style
                        ON style_fabric_parts(style);
                """)
            # Migrate: fabric mapping uploaded under 'zalando' (before Sky East was a
            # registered company) should live under 'sky_east'.
            # INSERT OR IGNORE preserves any existing sky_east record for the same
            # (style, combo_idx, seq); DELETE removes the now-redundant zalando rows.
            _has_zalando = conn.execute(
                "SELECT 1 FROM style_fabric_parts WHERE source='zalando' LIMIT 1"
            ).fetchone()
            if _has_zalando:
                conn.execute(
                    """INSERT OR IGNORE INTO style_fabric_parts
                       (source, style, combo_idx, seq, body_part, hhn_no, composition,
                        weight_gsm, width_cm, updated_at)
                       SELECT 'sky_east', style, combo_idx, seq, body_part, hhn_no,
                              composition, weight_gsm, width_cm, updated_at
                       FROM style_fabric_parts WHERE source='zalando'"""
                )
                conn.execute(
                    "DELETE FROM style_fabric_parts WHERE source='zalando'"
                )
