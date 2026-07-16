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


def test_return_label_persists_through_insert(tmp_path):
    """The Return Label value (Yes/No/NA from the client's PO) is written on
    insert, same as the other item fields."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))

    store.save_contract_checked(_make_contract([
        _make_item(style="RL1", color_name="Blue", zalando_po="PO1",
                   return_label="Yes"),
    ]))
    items = store.list_items(["PC1"])
    row = items[items["style"] == "RL1"].iloc[0]
    assert row["return_label"] == "Yes"


def test_return_label_change_alone_is_held_back_not_silently_dropped(tmp_path):
    """A Return Label change with sizes/qty/FOB otherwise identical used to
    be treated as a plain duplicate (skipped) -- the new value was silently
    discarded. It must now be surfaced as a pending confirmation instead."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL2", color_name="Blue", zalando_po="PO1", return_label="Yes"),
    ]))

    result = store.save_contract_checked(_make_contract([
        _make_item(style="RL2", color_name="Blue", zalando_po="PO1", return_label="No"),
    ]))

    assert result["duplicate_items"] == []
    assert len(result["pending_return_label"]) == 1
    pending = result["pending_return_label"][0]
    assert pending["old_return_label"] == "Yes"
    assert pending["new_return_label"] == "No"

    # Not written yet -- DB still shows the original value.
    items = store.list_items(["PC1"])
    assert items[items["style"] == "RL2"].iloc[0]["return_label"] == "Yes"


def test_return_label_change_with_other_changes_holds_back_the_whole_record(tmp_path):
    """When Return Label AND sizes/qty both differ, the whole item is held
    back -- not just the label -- so a size change never sneaks in
    unconfirmed alongside a Return Label change the user hasn't approved."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL3", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 1}, total_qty=1, return_label="Yes"),
    ]))

    result = store.save_contract_checked(_make_contract([
        _make_item(style="RL3", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 9}, total_qty=9, return_label="No"),
    ]))

    assert result["updated_items"] == []
    assert len(result["pending_return_label"]) == 1
    pending = result["pending_return_label"][0]
    assert pending["changed"]["return_label"] == ("Yes", "No")
    assert pending["changed"]["total_qty"] == (1, 9)

    items = store.list_items(["PC1"])
    row = items[items["style"] == "RL3"].iloc[0]
    assert row["return_label"] == "Yes"
    assert int(row["total_qty"]) == 1


def test_return_label_unchanged_other_fields_still_auto_update(tmp_path):
    """Regression guard: when Return Label is unchanged, size/qty/FOB changes
    must keep auto-updating exactly as before this feature -- only a Return
    Label change itself requires confirmation."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL4", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 1}, total_qty=1, return_label="Yes"),
    ]))

    result = store.save_contract_checked(_make_contract([
        _make_item(style="RL4", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 9}, total_qty=9, return_label="Yes"),
    ]))

    assert result["pending_return_label"] == []
    assert len(result["updated_items"]) == 1

    items = store.list_items(["PC1"])
    row = items[items["style"] == "RL4"].iloc[0]
    assert int(row["total_qty"]) == 9
    assert row["return_label"] == "Yes"


def test_apply_pending_item_writes_the_confirmed_replacement(tmp_path):
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL5", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 1}, total_qty=1, return_label="Yes"),
    ]))
    result = store.save_contract_checked(_make_contract([
        _make_item(style="RL5", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 9}, total_qty=9, return_label="No"),
    ]))
    pending = result["pending_return_label"][0]

    outcome = store.apply_pending_item(pending["item"])
    assert outcome == "updated"

    items = store.list_items(["PC1"])
    row = items[items["style"] == "RL5"].iloc[0]
    assert row["return_label"] == "No"
    assert int(row["total_qty"]) == 9

    # The pre-confirmation state (qty=1, return_label=Yes) must be archived.
    history = store.list_item_history("PC1", style="RL5")
    assert history.iloc[0]["return_label"] == "Yes"
    assert int(history.iloc[0]["total_qty"]) == 1


def test_return_label_defaults_to_na_when_not_set(tmp_path):
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL2", color_name="Red", zalando_po="PO2"),
    ]))
    items = store.list_items(["PC1"])
    assert items[items["style"] == "RL2"].iloc[0]["return_label"] == "NA"
