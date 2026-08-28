"""The Sky East write paths must leave a trail naming the person.

``sky_east_item_history`` already keeps whole superseded rows, but it has no
column for *who* — so "who took that style off the contract?" was
unanswerable. These tests pin the hooks that answer it, and pin the volume
decision with them: an upload that only ADDS items must not write one log row
per item (a log that restates the contract is a log nobody reads), while
everything that overwrites or removes prior data gets its own row.
"""
from __future__ import annotations

import pytest


# --------------------------------------------------------------------------
# Helpers (shape borrowed from tests/test_sky_east_store.py)
# --------------------------------------------------------------------------
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


@pytest.fixture
def store(tmp_path):
    """A scratch SkyEastStore. Its audit hooks write to its own db_path, so
    nothing here can reach the live database."""
    from po_extractor.store.sky_east_store import SkyEastStore
    from po_extractor.store.audit_context import set_current_user

    set_current_user("angel")
    return SkyEastStore(str(tmp_path / "se.db"))


def _log(store):
    from po_extractor.store.change_log_store import ChangeLogStore
    return ChangeLogStore(store.db_path).list_recent(limit=200)


def _rows(store, entity=None, action=None):
    df = _log(store)
    if entity:
        df = df[df["entity"] == entity]
    if action:
        df = df[df["action"] == action]
    return df


# --------------------------------------------------------------------------
# Uploads
# --------------------------------------------------------------------------
def test_an_upload_that_only_adds_writes_one_summary_row(store):
    """Ten new items must not become ten log rows — the contract already
    says what it contains. One summary row, naming who uploaded it."""
    items = [_make_item(style=f"ST{i}", zalando_po=f"PO{i}") for i in range(10)]
    store.save_contract_checked(_make_contract(items))

    df = _log(store)
    assert len(df) == 1, f"expected 1 summary row, got:\n{df}"
    row = df.iloc[0]
    assert row["entity"] == "sky_east_contract"
    assert row["record_key"] == "PC1"
    assert row["username"] == "angel"
    assert row["field"] == "merge"
    assert "10 written" in row["detail"]


def test_an_overwritten_item_records_the_field_that_changed(store):
    """A revision that changes a quantity must record old -> new, not just
    'something changed'."""
    store.save_contract_checked(_make_contract([_make_item()]))
    store.save_contract_checked(_make_contract(
        [_make_item(sizes={"S": 7}, total_qty=7)]))

    df = _rows(store, entity="sky_east_item", action="update")
    fields = dict(zip(df["field"], zip(df["old_value"], df["new_value"])))
    assert "total_qty" in fields, f"no total_qty row in:\n{df}"
    assert fields["total_qty"] == ("1", "7")
    assert (df["record_key"] == "PC1 · ST1 · Blue · PO1").all()
    assert (df["username"] == "angel").all()


def test_re_uploading_the_same_file_records_no_item_rows(store):
    """An unchanged re-upload is noise; only the summary should appear."""
    store.save_contract_checked(_make_contract([_make_item()]))
    store.save_contract_checked(_make_contract([_make_item()]))

    assert _rows(store, entity="sky_east_item").empty
    summaries = _rows(store, entity="sky_east_contract")
    assert len(summaries) == 2
    assert "1 unchanged" in summaries.iloc[0]["detail"]


def test_a_replace_records_every_item_it_removed(store):
    """整份合同替换 is the destructive path — each dropped item is named, so a
    replace run in error can be traced to a person and reversed from the
    archive."""
    store.save_contract_checked(_make_contract([
        _make_item(style="KEEP", zalando_po="PO1"),
        _make_item(style="DROP", zalando_po="PO2"),
    ]))
    store.replace_contract(_make_contract([
        _make_item(style="KEEP", zalando_po="PO1")]))

    removed = _rows(store, entity="sky_east_item", action="delete")
    assert list(removed["record_key"]) == ["PC1 · DROP · Blue · PO2"]
    assert removed.iloc[0]["username"] == "angel"
    assert "整份合同替换" in removed.iloc[0]["detail"]

    summary = _rows(store, entity="sky_east_contract").iloc[0]
    assert summary["field"] == "replace"
    assert "1 removed" in summary["detail"]


# --------------------------------------------------------------------------
# Hand edits
# --------------------------------------------------------------------------
def test_a_hand_edit_records_only_the_fields_that_moved(store):
    """fabric_item_no is rewritten, contract_no is passed through unchanged —
    only the first belongs in the log."""
    store.save_contract_checked(_make_contract(
        [_make_item(fabric_item_no="OLD-1", contract_no="C-9")]))
    store.update_item_fields("PC1", "ST1", "Blue", "PO1", "NEW-2", "C-9")

    df = _rows(store, entity="sky_east_item")
    assert list(df["field"]) == ["fabric_item_no"]
    assert (df.iloc[0]["old_value"], df.iloc[0]["new_value"]) == ("OLD-1", "NEW-2")


def test_patching_a_contract_number_records_the_old_one(store):
    store.save_contract_checked(_make_contract(
        [_make_item(contract_no="C-OLD")]))
    store.update_contract_no("PC1", "ST1", "Blue", "PO1", "C-NEW")

    df = _rows(store, entity="sky_east_item")
    assert list(df["field"]) == ["contract_no"]
    assert (df.iloc[0]["old_value"], df.iloc[0]["new_value"]) == ("C-OLD", "C-NEW")


def test_an_edit_that_matches_no_row_records_nothing(store):
    """No row updated, nothing to say."""
    assert store.update_contract_no("NOPE", "ST1", "Blue", "PO1", "C-1") is False
    assert _log(store).empty


def test_a_confirmed_return_label_change_names_who_confirmed_it(store):
    """save_contract_checked deliberately refuses to apply a Return Label
    change on its own. Who said yes, and what it was before, is the point."""
    store.save_contract_checked(_make_contract([_make_item()]))
    pending = store.save_contract_checked(_make_contract(
        [_make_item(return_label="YES")]))["pending_return_label"]
    assert len(pending) == 1, "fixture assumption: the label change is held back"

    store.apply_pending_item(pending[0]["item"])

    df = _rows(store, entity="sky_east_item")
    assert list(df["field"]) == ["return_label"]
    row = df.iloc[0]
    assert (row["old_value"], row["new_value"]) == ("NA", "YES")
    assert row["username"] == "angel"
    assert "confirmed by user" in row["detail"]


def test_deleting_a_contract_is_recorded_per_pc_no(store):
    """The one write nothing can undo — the archive goes with it."""
    store.save_contract_checked(_make_contract([_make_item()]))
    store.save_contract_checked(_make_contract([_make_item(pc_no="PC2")],
                                               pc_no="PC2"))
    store.delete_contracts(["PC1", "PC2"])

    df = _rows(store, entity="sky_east_contract", action="delete")
    assert sorted(df["record_key"]) == ["PC1", "PC2"]
    assert (df["username"] == "angel").all()


# --------------------------------------------------------------------------
# The hooks must never break the write they describe
# --------------------------------------------------------------------------
def test_a_broken_change_log_does_not_break_an_upload(store, monkeypatch):
    """The rule the whole table is built on: auditing is never the reason a
    contract fails to save."""
    import po_extractor.store.change_log_store as cls

    def _boom(*a, **kw):
        raise RuntimeError("change log is on fire")

    monkeypatch.setattr(cls, "ChangeLogStore", _boom)
    result = store.save_contract_checked(_make_contract([_make_item()]))

    assert result["new_items"] == [("ST1", "Blue", "PO1")]
    assert store.contract_count() == 1


def test_the_audit_trail_lands_in_the_store_s_own_database(tmp_path):
    """Not the canonical one. A store told to use a scratch path must keep its
    audit there too -- the suite wrote 53 rows into the live po_history.db
    before this held."""
    import sqlite3
    from po_extractor.store.sky_east_store import SkyEastStore

    db = tmp_path / "scratch.db"
    SkyEastStore(str(db)).save_contract_checked(_make_contract([_make_item()]))

    n = sqlite3.connect(str(db)).execute(
        "SELECT COUNT(*) FROM change_log").fetchone()[0]
    assert n == 1
