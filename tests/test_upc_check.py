"""UPC check store methods — lookup by UPC + stocktake (盘点)."""
from __future__ import annotations

import pytest

from po_extractor.store.po_store import POStore
from po_extractor.models.po_data import POData, POMetadata, SizeRow


@pytest.fixture()
def store(tmp_path):
    s = POStore(str(tmp_path / "t.db"))
    po = POData(metadata=POMetadata(
        po_number="PO1", style="ST1", company="GIII",
        destination_code="UC", ship_to="ROSS DC PERRIS CA", buyer="ROSS"),
        size_rows=[
            SizeRow("PO1", "ST1", "BLACK", "M", 100, "700948471565"),
            SizeRow("PO1", "ST1", "BLACK", "L", 50, "700948471534"),
        ])
    po2 = POData(metadata=POMetadata(po_number="PO2", style="ST2", company="GIII"),
                 size_rows=[SizeRow("PO2", "ST2", "RED", "S", 7, "700948471565")])
    s.save_many_checked([po, po2])
    return s


# ── lookup ────────────────────────────────────────────────────────────────────

def test_find_by_upc_returns_context(store):
    rows = store.find_by_upc("700948471534")
    assert len(rows) == 1
    r = rows[0]
    assert r["po_number"] == "PO1" and r["style"] == "ST1"
    assert r["color"] == "BLACK" and r["size"] == "L" and r["units"] == 50
    assert r["company"] == "GIII" and r["destination_code"] == "UC"


def test_find_by_upc_multiple_pos(store):
    # same UPC on PO1 (M) and PO2 (S)
    rows = store.find_by_upc("700948471565")
    assert {r["po_number"] for r in rows} == {"PO1", "PO2"}


def test_find_by_upc_unknown_and_blank(store):
    assert store.find_by_upc("000000000000") == []
    assert store.find_by_upc("") == []


def test_find_by_upc_company_scope(store):
    assert store.find_by_upc("700948471534", companies=["Sky East"]) == []
    assert len(store.find_by_upc("700948471534", companies=["GIII"])) == 1


# ── stocktake ─────────────────────────────────────────────────────────────────

def test_stocktake_increment_decrement(store):
    assert store.adjust_stocktake("700948471565", 1) == 1
    assert store.adjust_stocktake("700948471565", 1) == 2
    assert store.adjust_stocktake("700948471565", -1) == 1
    # can go negative (over-scan on the remove pass is a real signal)
    store.adjust_stocktake("XYZ", -1)
    assert store.adjust_stocktake("XYZ", -1) == -2


def test_stocktake_load_joins_context_and_hides_zero(store):
    store.adjust_stocktake("700948471565", 3)
    store.adjust_stocktake("700948471534", 1)
    store.adjust_stocktake("700948471534", -1)   # back to 0 → hidden
    data = store.load_stocktake()
    upcs = {d["upc"]: d for d in data}
    assert "700948471534" not in upcs             # zero hidden
    assert upcs["700948471565"]["qty"] == 3
    assert upcs["700948471565"]["style"] == "ST1"  # joined context


def test_stocktake_clear(store):
    store.adjust_stocktake("700948471565", 5)
    assert store.load_stocktake()
    store.clear_stocktake()
    assert store.load_stocktake() == []
