"""Tests for SkyEastStore's colour-resolution-miss diagnostic log.

Scoped to Sky East specifically (not the GIII po_exceptions Exception
Queue, which is a different pipeline / different kind of failure) so a
reviewer can see, for every colour that failed to resolve during buy plan
generation, exactly what the client's PO said.
"""
from __future__ import annotations

import pytest

from po_extractor.store.sky_east_store import SkyEastStore


@pytest.fixture
def store(tmp_path):
    return SkyEastStore(str(tmp_path / "test.db"))


def test_log_color_miss_then_list(store):
    store.log_color_miss(
        pc_no="HHPPC048", contract_no="26302-ZA7158", style="BL4257",
        po_no="PO2338263C", client_po_color="Dark Brown",
        attempted_color="Dark Brown", source="progress",
    )
    df = store.list_color_misses()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["pc_no"] == "HHPPC048"
    assert row["style"] == "BL4257"
    assert row["client_po_color"] == "Dark Brown"
    assert row["source"] == "progress"
    assert row["logged_at"]


def test_list_color_misses_newest_first(store):
    store.log_color_miss(
        pc_no="P1", contract_no="C1", style="S1", po_no="PO1",
        client_po_color="Old Miss", attempted_color="Old Miss", source="db",
    )
    store.log_color_miss(
        pc_no="P2", contract_no="C2", style="S2", po_no="PO2",
        client_po_color="New Miss", attempted_color="New Miss", source="db",
    )
    df = store.list_color_misses()
    assert list(df["client_po_color"]) == ["New Miss", "Old Miss"]


def test_log_color_miss_is_append_only_no_dedup(store):
    """Re-running a generation over the same bad data logs another entry —
    deliberately not deduped, so the count reflects each run's failures.
    """
    for _ in range(3):
        store.log_color_miss(
            pc_no="P1", contract_no="C1", style="S1", po_no="PO1",
            client_po_color="Repeat Miss", attempted_color="Repeat Miss",
            source="db",
        )
    assert len(store.list_color_misses()) == 3


def test_clear_color_misses(store):
    store.log_color_miss(
        pc_no="P1", contract_no="C1", style="S1", po_no="PO1",
        client_po_color="X", attempted_color="X", source="db",
    )
    removed = store.clear_color_misses()
    assert removed == 1
    assert store.list_color_misses().empty


def test_list_color_misses_empty_by_default(store):
    assert store.list_color_misses().empty


def test_log_color_miss_stores_progress_colors(store):
    """progress_colors mirrors the same comparison shown in the Excel cell
    comment -- 大货进度表's own colour(s) on file for that PC No./style.
    """
    store.log_color_miss(
        pc_no="HHPPC048", contract_no="26302-ZA7148", style="DR5124",
        po_no="PO2333438C", client_po_color="Dark Blue",
        attempted_color="Dark Blue", source="progress",
        progress_colors=["Navy"],
    )
    row = store.list_color_misses().iloc[0]
    assert row["progress_colors"] == "Navy"


def test_log_color_miss_joins_multiple_progress_colors(store):
    store.log_color_miss(
        pc_no="P1", contract_no="C1", style="S1", po_no="PO1",
        client_po_color="X", attempted_color="X", source="progress",
        progress_colors=["Navy", "Black"],
    )
    row = store.list_color_misses().iloc[0]
    assert row["progress_colors"] == "Navy, Black"


def test_log_color_miss_progress_colors_blank_when_none(store):
    """None (internal-DB source, or nothing on file) stores as an empty
    string, not a literal "None" -- keeps the column clean for display.
    """
    store.log_color_miss(
        pc_no="P1", contract_no="C1", style="S1", po_no="PO1",
        client_po_color="X", attempted_color="X", source="db",
    )
    row = store.list_color_misses().iloc[0]
    assert row["progress_colors"] == ""


def test_log_color_miss_progress_colors_blank_for_empty_list(store):
    store.log_color_miss(
        pc_no="P1", contract_no="C1", style="S1", po_no="PO1",
        client_po_color="X", attempted_color="X", source="progress",
        progress_colors=[],
    )
    row = store.list_color_misses().iloc[0]
    assert row["progress_colors"] == ""


def test_existing_db_migrates_progress_colors_column(tmp_path):
    """A DB created before progress_colors existed must gain the column via
    ALTER TABLE on the next open, not crash or silently drop the row.
    """
    import sqlite3
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE sky_east_color_misses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pc_no TEXT, contract_no TEXT, style TEXT, po_no TEXT,
            client_po_color TEXT, attempted_color TEXT, source TEXT, logged_at TEXT
        );
    """)
    conn.execute(
        "INSERT INTO sky_east_color_misses "
        "(pc_no, contract_no, style, po_no, client_po_color, attempted_color, source, logged_at) "
        "VALUES ('P1','C1','S1','PO1','Old Colour','Old Colour','db','2026-01-01 00:00:00')"
    )
    conn.commit()
    conn.close()

    store = SkyEastStore(db_path)
    df = store.list_color_misses()
    assert len(df) == 1
    assert df.iloc[0]["client_po_color"] == "Old Colour"
    assert df.iloc[0]["progress_colors"] is None or df.iloc[0]["progress_colors"] == ""

    # New rows after migration must also work normally.
    store.log_color_miss(
        pc_no="P2", contract_no="C2", style="S2", po_no="PO2",
        client_po_color="New Colour", attempted_color="New Colour",
        source="progress", progress_colors=["Navy"],
    )
    df2 = store.list_color_misses()
    assert len(df2) == 2
    assert df2.iloc[0]["progress_colors"] == "Navy"   # newest first
