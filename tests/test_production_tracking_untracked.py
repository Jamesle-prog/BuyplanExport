"""Regression: list_untracked_pos() must offer Sky East orders too.

Locks the v2.26.6 fix — the Add New picker in the 🏭 Tracking tab only ever
queried po_size_rows / po_metadata (the GIII pipeline's tables), so a Sky
East order could never appear there no matter which company the user had
access to. list_untracked_pos() now UNIONs in sky_east_items, gated by the
same allow_all / companies access-control contract as the GIII branch.

Run with: ``pytest tests/test_production_tracking_untracked.py -v``
"""
from __future__ import annotations

import sqlite3

import pytest

from auth.companies import COMPANY_SKY_EAST
from po_extractor.store.po_store import POStore
from po_extractor.store.sky_east_store import SkyEastStore
from po_extractor.store.production_tracking_store import ProductionTrackingStore


@pytest.fixture
def stores(tmp_path):
    """Single shared DB file — the canonical single-DB deployment mode."""
    db_path = str(tmp_path / "po_history.db")
    po_store = POStore(db_path)
    SkyEastStore(db_path)  # creates the sky_east_* tables in the same file
    pt_store = ProductionTrackingStore(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO po_metadata (po_number, company, style, factory) "
            "VALUES ('PO-GIII-1', 'GIII', 'STY-G1', 'Factory G')"
        )
        conn.execute(
            "INSERT INTO po_size_rows (po_number, style, color, size, units) "
            "VALUES ('PO-GIII-1', 'STY-G1', 'Black', 'M', 100)"
        )
        conn.execute(
            "INSERT INTO sky_east_items (pc_no, zalando_po, style, brand) "
            "VALUES ('PC1', 'PO-SE-1', 'STY-S1', 'Anna Field')"
        )
    return po_store, pt_store, db_path


def _po_numbers(rows: list[dict]) -> set[str]:
    return {r["po_number"] for r in rows}


def test_admin_sees_both_giii_and_sky_east(stores):
    po_store, pt_store, _ = stores
    rows = pt_store.list_untracked_pos(po_store, companies=None, allow_all=True)
    assert _po_numbers(rows) == {"PO-GIII-1", "PO-SE-1"}
    se_row = next(r for r in rows if r["po_number"] == "PO-SE-1")
    assert se_row["style"] == "STY-S1"
    assert se_row["company"] == COMPANY_SKY_EAST


def test_user_with_only_giii_company_does_not_see_sky_east(stores):
    po_store, pt_store, _ = stores
    rows = pt_store.list_untracked_pos(po_store, companies=["GIII"], allow_all=False)
    assert _po_numbers(rows) == {"PO-GIII-1"}


def test_user_with_only_sky_east_sees_only_sky_east(stores):
    po_store, pt_store, _ = stores
    rows = pt_store.list_untracked_pos(
        po_store, companies=[COMPANY_SKY_EAST], allow_all=False
    )
    assert _po_numbers(rows) == {"PO-SE-1"}


def test_user_with_both_companies_sees_both(stores):
    po_store, pt_store, _ = stores
    rows = pt_store.list_untracked_pos(
        po_store, companies=["GIII", COMPANY_SKY_EAST], allow_all=False
    )
    assert _po_numbers(rows) == {"PO-GIII-1", "PO-SE-1"}


def test_user_with_no_companies_sees_nothing(stores):
    po_store, pt_store, _ = stores
    rows = pt_store.list_untracked_pos(po_store, companies=[], allow_all=False)
    assert rows == []


def test_tracked_sky_east_po_drops_out_of_untracked(stores):
    po_store, pt_store, db_path = stores
    pt_store.upsert(
        po_number="PO-SE-1", style="STY-S1", factory="", company=COMPANY_SKY_EAST,
        updated_by="tester", overall_notes="", use_substitute_materials=1,
        stage_fields={}, dep_fields={}, qc_fields={},
    )
    rows = pt_store.list_untracked_pos(po_store, companies=None, allow_all=True)
    assert _po_numbers(rows) == {"PO-GIII-1"}
