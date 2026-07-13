"""Tests for _po_store_write: batch revision, UPC hash, and save_many_checked."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from po_extractor.store.po_store import POStore
from po_extractor.models.po_data import POData, POMetadata, SizeRow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_po(po_number: str, style: str, color: str, size: str, units: int,
             upc: str = "", version: str = "") -> POData:
    meta = POMetadata(
        po_number=po_number,
        style=style,
        version=version,
    )
    row = SizeRow(
        po_number=po_number,
        style=style,
        color=color,
        size=size,
        units=units,
        upc=upc,
    )
    return POData(metadata=meta, size_rows=[row])


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "test.db"
    return POStore(str(db))


# ---------------------------------------------------------------------------
# P1-fix-1: save_many_checked no longer drops real revisions
# ---------------------------------------------------------------------------

class TestSaveManyCheckedRevisions:
    def test_two_versions_same_batch_creates_history_row(self, store):
        """v1 then v2 of the same PO in one batch → new + updated, history archived."""
        po_v1 = _make_po("PO001", "STYLE-A", "Black", "M", units=10, version="1")
        po_v2 = _make_po("PO001", "STYLE-A", "Black", "M", units=20, version="2")

        results = store.save_many_checked([po_v1, po_v2])

        statuses = [(pn, s) for pn, s, _ in results]
        assert statuses == [("PO001", "new"), ("PO001", "updated")], (
            "Second occurrence of same PO with changed content must be 'updated', not 'duplicate'"
        )

        # A history row should exist
        with store._conn() as conn:
            hist = conn.execute(
                "SELECT COUNT(*) FROM po_version_history WHERE po_number='PO001'"
            ).fetchone()[0]
        assert hist == 1, "Revision must create a history row"

    def test_truly_identical_po_twice_is_duplicate(self, store):
        """Identical PO twice in same batch → new + duplicate (no data change)."""
        po = _make_po("PO002", "STYLE-B", "Red", "S", units=5)
        results = store.save_many_checked([po, po])
        statuses = [s for _, s, _ in results]
        assert statuses == ["new", "duplicate"]

    def test_three_versions_sequential(self, store):
        """v1 → v2 → v3 all in one batch each triggers an update."""
        pos = [
            _make_po("PO003", "STYLE-C", "Blue", "L", units=i * 10, version=str(i))
            for i in range(1, 4)
        ]
        results = store.save_many_checked(pos)
        statuses = [s for _, s, _ in results]
        assert statuses == ["new", "updated", "updated"]

        with store._conn() as conn:
            hist = conn.execute(
                "SELECT COUNT(*) FROM po_version_history WHERE po_number='PO003'"
            ).fetchone()[0]
        assert hist == 2, "Two revisions should produce two history rows"


# ---------------------------------------------------------------------------
# Split-delivery: same SKU, different ex-factory date → both rows kept
# ---------------------------------------------------------------------------

class TestSplitDeliveryKeepsBothRows:
    def _po(self, rows):
        meta = POMetadata(po_number="SD1", style="ST1", company="GIII")
        return POData(metadata=meta, size_rows=rows)

    def test_same_sku_different_xfty_kept_and_summed(self, store):
        po = self._po([
            SizeRow("SD1", "ST1", "BLACK", "M", 100, "U1", xfty_date="2026-08-01"),
            SizeRow("SD1", "ST1", "BLACK", "M",  50, "U1", xfty_date="2026-09-01"),
            SizeRow("SD1", "ST1", "BLACK", "S",  30, "U2", xfty_date="2026-08-01"),
        ])
        store.save_many_checked([po])
        rows = store.load_size_rows(["SD1"])
        assert len(rows) == 3                                  # both M shipments kept
        assert int(rows[rows["Size"] == "M"]["Units"].sum()) == 150
        tot = store.list_pos()
        assert int(tot[tot["po_number"] == "SD1"]["total_units"].iloc[0]) == 180

    def test_same_sku_same_xfty_still_collapses(self, store):
        po = self._po([
            SizeRow("SD1", "ST1", "RED", "L", 10, "U", xfty_date="2026-08-01"),
            SizeRow("SD1", "ST1", "RED", "L", 99, "U", xfty_date="2026-08-01"),
        ])
        store.save_many_checked([po])
        rows = store.load_size_rows(["SD1"])
        assert len(rows) == 1 and int(rows["Units"].iloc[0]) == 99  # genuine dup, last wins

    def test_migration_from_pre_xfty_schema_preserves_rows(self, tmp_path):
        import sqlite3
        db = tmp_path / "old.db"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE po_size_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT, po_number TEXT NOT NULL,
                style TEXT, color TEXT, size TEXT, units INTEGER, upc TEXT,
                extracted_at TEXT, UNIQUE(po_number, style, color, size));
            INSERT INTO po_size_rows (po_number, style, color, size, units, upc, extracted_at)
                VALUES ('OLD', 'S', 'C', 'M', 77, 'U', '2026-01-01');
        """)
        conn.commit(); conn.close()
        store = POStore(str(db))                    # __init__ runs the migration
        cols = {r[1] for r in sqlite3.connect(str(db))
                .execute("PRAGMA table_info(po_size_rows)")}
        assert "xfty_date" in cols
        rows = store.load_size_rows(["OLD"])
        assert len(rows) == 1 and int(rows["Units"].iloc[0]) == 77


# ---------------------------------------------------------------------------
# P1-fix-2: UPC included in content hash
# ---------------------------------------------------------------------------

class TestRowHash:
    def test_upc_change_detected_as_update(self, store):
        """A PO where only the UPC changes must not be treated as a duplicate."""
        po_v1 = _make_po("PO010", "STYLE-X", "White", "XL", units=3, upc="1234567890")
        po_v2 = _make_po("PO010", "STYLE-X", "White", "XL", units=3, upc="9999999999")

        s1, _ = store.check_and_save(po_v1)
        s2, diff = store.check_and_save(po_v2)

        assert s1 == "new"
        assert s2 == "updated", (
            "UPC-only change must be detected as 'updated', not 'duplicate'"
        )

    def test_same_upc_still_duplicate(self, store):
        """Identical UPC → still duplicate when nothing else changes."""
        po = _make_po("PO011", "STYLE-Y", "Green", "S", units=7, upc="AAA111")
        store.check_and_save(po)
        s2, _ = store.check_and_save(po)
        assert s2 == "duplicate"

    def test_missing_upc_vs_populated_upc_is_update(self, store):
        """Going from no UPC to a populated UPC is a real change."""
        po_no_upc  = _make_po("PO012", "STYLE-Z", "Navy", "M", units=4, upc="")
        po_has_upc = _make_po("PO012", "STYLE-Z", "Navy", "M", units=4, upc="555000555")

        store.check_and_save(po_no_upc)
        s2, _ = store.check_and_save(po_has_upc)
        assert s2 == "updated"
