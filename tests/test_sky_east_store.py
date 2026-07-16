"""Regression test for SkyEastStore.save_contract_checked's duplicate-key
bug within a single contract.

``existing_map`` was built ONCE before the item loop and never updated
inside it.  When a contract has two items sharing the same
(style, color_name, zalando_po) -- the table's own UNIQUE key -- both loop
iterations looked up the same stale pre-loop snapshot, so the second
iteration either silently overwrote the first iteration's real update with
no archive row, or double-archived the same original state while the
first item's update was lost.
"""
from __future__ import annotations


def _make_item(**over):
    from po_extractor.models.sky_east_data import SkyEastItem
    base = dict(
        pc_no="PC1", zalando_po="PO1", style="ST1", config_sku="SKU-1",
        article_name="A", brand="Anna Field", color_name="Blue",
        colour_code="Q11", launch_date="", fabric_item_no="HHP-JS-12345",
        fabrication="", contract_no="", sizes={"S": 1}, total_qty=1,
        fob_usd=1.0, total_cost_usd=1.0,
    )
    base.update(over)
    return SkyEastItem(**base)


def _make_contract(items, **over):
    from po_extractor.models.sky_east_data import SkyEastContract
    base = dict(pc_no="PC1", pc_date="2026-01-01", buyer="B", seller="S",
                currency="USD", payment_terms="TT", trade_term="FOB")
    base.update(over)
    return SkyEastContract(items=items, **base)


def test_duplicate_key_within_same_contract_both_updates_applied(tmp_path):
    """Two items sharing (style, color_name, zalando_po) within ONE
    save_contract_checked() call must both be reflected: the second item's
    values (the final DB state) must win, and the archive history must show
    two real transitions -- not the same pre-loop snapshot archived twice."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))

    # First save: establish a baseline row.
    store.save_contract_checked(_make_contract([
        _make_item(style="DUP", color_name="Red", zalando_po="POZ",
                   sizes={"S": 1}, total_qty=1, fob_usd=1.0),
    ]))

    # Second save: the SAME contract carries two items for the identical
    # (style, color_name, zalando_po) key with different quantities each
    # time -- simulating a source file that lists the same SKU twice with
    # a running total correction.
    result = store.save_contract_checked(_make_contract([
        _make_item(style="DUP", color_name="Red", zalando_po="POZ",
                   sizes={"S": 2}, total_qty=2, fob_usd=1.0),
        _make_item(style="DUP", color_name="Red", zalando_po="POZ",
                   sizes={"S": 3}, total_qty=3, fob_usd=1.0),
    ]))

    # Both iterations must be recognised as real updates (not a duplicate
    # comparing against the same stale snapshot twice).
    assert len(result["updated_items"]) == 2

    # The row actually stored must reflect the LAST item processed (qty=3),
    # proving the second iteration compared against the first iteration's
    # write, not the pre-loop DB state.
    items = store.list_items(["PC1"])
    row = items[(items["style"] == "DUP") & (items["zalando_po"] == "POZ")].iloc[0]
    assert int(row["total_qty"]) == 3
    assert int(row["s"]) == 3

    # Two real transitions (1->2, 2->3) means two archive rows, not zero or
    # a duplicated single snapshot.
    history = store.list_item_history("PC1", style="DUP")
    assert len(history) == 2
    archived_qtys = sorted(int(q) for q in history["total_qty"])
    assert archived_qtys == [1, 2], (
        f"expected archive of qty=1 (baseline) then qty=2 (first item's "
        f"write, overwritten by the second item) -- got {archived_qtys}"
    )
