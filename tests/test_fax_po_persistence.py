"""Fax POs are saved like any other PO, so they join the combined views.

The four fax sections of the GIII Upload tab (KL, MSG/CSKHHA, TK EU, Infor
Nexus) used to hand their parse straight to an Excel writer and store nothing.
Order Summary and PO Tracker read the database, so a fax PO could never appear
beside the main GIII flow and Sky East — the data simply was not there.

All four return the same 17-key dict, so one adapter converts them to POData
and the existing save_many_checked does the rest: duplicate detection,
revision history, conflict reporting.
"""
from __future__ import annotations

import pytest

from po_extractor.ui_helpers.fax_po_adapter import (
    fax_po_to_podata, fax_pos_to_podata,
)


def _fax_po(**over) -> dict:
    """The shape all four parsers return."""
    base = dict(
        po_number="__TESTFAX001__", style="G5DTN93C", po_date="05/13/2026",
        ship_date="08/01/2026", etd="2026-08-15", vendor="HIGH HOPE",
        factory="F1", fob_price="12.50", description="LS KNIT TOP",
        customer_name="ROSS STORES", ship_to="ROSS DC PERRIS CA",
        hanger_info="NO HANGER", pack_ratio="1-2-2-1", hts_num="6106.20",
        cpo="CP123", msrp="69.00", source_file="__TESTFAX001__.pdf",
        line_items=[{
            "ln": "001", "style": "G5DTN93C", "color": "JVS",
            "sizes": [("S", 10, "700948471565", 12.5),
                      ("M", 20, "700948471534", None)],
        }],
    )
    base.update(over)
    return base


# ── the mapping ─────────────────────────────────────────────────────────────

def test_a_fax_po_becomes_a_podata_with_its_size_rows():
    po = fax_po_to_podata(_fax_po(), company="GIII", source_format="kl")
    assert po is not None
    m = po.metadata
    assert m.po_number == "__TESTFAX001__"
    assert m.style == "G5DTN93C"
    assert m.company == "GIII" and m.source_format == "kl"
    assert m.customer == "ROSS STORES" and m.ship_to == "ROSS DC PERRIS CA"
    assert m.unit_cost == "12.50" and m.msrp == "69.00" and m.cpo == "CP123"
    assert m.ratio == "1-2-2-1" and m.hanger == "NO HANGER"

    assert [(r.size, r.units, r.upc) for r in po.size_rows] == [
        ("S", 10, "700948471565"), ("M", 20, "700948471534")]
    assert all(r.style == "G5DTN93C" and r.color == "JVS" for r in po.size_rows)


def test_the_ex_factory_date_rides_on_every_size_row():
    """The store keys size rows on (po, style, colour, size, xfty_date), so a
    re-issue with a new date becomes its own rows instead of overwriting the
    first shipment's."""
    po = fax_po_to_podata(_fax_po(etd="2026-08-15"))
    assert {r.xfty_date for r in po.size_rows} == {"2026-08-15"}
    assert po.metadata.xport_date == "2026-08-15"


@pytest.mark.parametrize("missing", ["?", "", "UNCONFIRMED", "N/A", "-"])
def test_the_parsers_missing_field_tokens_become_blank_not_text(missing):
    """A fax that could not be read for a price writes "?" or "UNCONFIRMED".
    Stored as text it would be exported and totalled as though it were a
    value."""
    po = fax_po_to_podata(_fax_po(fob_price=missing, msrp=missing, cpo=missing))
    assert po.metadata.unit_cost is None
    assert po.metadata.msrp is None
    assert po.metadata.cpo is None


def test_a_po_without_a_number_is_skipped_not_saved_under_a_blank_key():
    """The PO number is the store's identity — an empty one would collide
    with every other unidentified PO."""
    assert fax_po_to_podata(_fax_po(po_number="?")) is None
    assert fax_po_to_podata(_fax_po(po_number="")) is None
    assert fax_pos_to_podata([_fax_po(po_number="?"), _fax_po()]) != []
    assert len(fax_pos_to_podata([_fax_po(po_number="?"), _fax_po()])) == 1


def test_a_malformed_size_entry_is_dropped_not_fatal():
    """Fax text is OCR-adjacent; one bad line must not lose the whole PO."""
    po = fax_po_to_podata(_fax_po(line_items=[{
        "style": "S1", "color": "BLK",
        "sizes": [("S", "not a number", "u", None),
                  ("M", 5, "u2", None),
                  ("broken",)],
    }]))
    assert [(r.size, r.units) for r in po.size_rows] == [("M", 5)]


def test_a_line_item_without_a_style_falls_back_to_the_po_style():
    po = fax_po_to_podata(_fax_po(
        style="HEADER-STYLE",
        line_items=[{"color": "BLK", "sizes": [("S", 1, "u", None)]}]))
    assert po.size_rows[0].style == "HEADER-STYLE"


def test_no_line_items_still_yields_the_po_header():
    """A PO whose table did not parse is still worth recording — its
    metadata is real and the missing rows are visible as zero units."""
    po = fax_po_to_podata(_fax_po(line_items=[]))
    assert po is not None and po.size_rows == []


# ── end to end: saved, then visible in the combined view ────────────────────

def test_a_saved_fax_po_reaches_the_combined_order_summary(tmp_path):
    """The whole point of persisting: Order Summary / PO Tracker read the
    database, so a fax PO must show up there beside the other pipelines."""
    from po_extractor.store.po_store import POStore
    from po_extractor.ui_helpers.combined_summary import load_standard_orders

    store = POStore(str(tmp_path / "po.db"))
    store.save_many_checked(fax_pos_to_podata(
        [_fax_po()], company="GIII", source_format="kl"))

    df = load_standard_orders(store, None, include_sky_east=False)
    assert not df.empty
    row = df[df["po_number"] == "__TESTFAX001__"]
    assert len(row) == 1
    assert row.iloc[0]["style"] == "G5DTN93C"
    assert row.iloc[0]["company"] == "GIII"


def test_re_uploading_the_same_fax_is_a_duplicate_not_a_second_row(tmp_path):
    """Going through save_many_checked means fax POs inherit the duplicate
    detection every other PO already had."""
    from po_extractor.store.po_store import POStore

    store = POStore(str(tmp_path / "po.db"))
    pos = fax_pos_to_podata([_fax_po()], company="GIII", source_format="kl")
    first = store.save_many_checked(pos)
    second = store.save_many_checked(
        fax_pos_to_podata([_fax_po()], company="GIII", source_format="kl"))

    assert first[0][1] == "new"
    assert second[0][1] == "duplicate"
    assert len(store.list_pos()) == 1


def test_a_revised_fax_is_recorded_as_an_update(tmp_path):
    from po_extractor.store.po_store import POStore

    store = POStore(str(tmp_path / "po.db"))
    store.save_many_checked(fax_pos_to_podata([_fax_po()], company="GIII"))
    revised = _fax_po(line_items=[{
        "style": "G5DTN93C", "color": "JVS",
        "sizes": [("S", 99, "700948471565", 12.5)]}])
    result = store.save_many_checked(fax_pos_to_podata([revised], company="GIII"))
    assert result[0][1] == "updated"


# ── every fax section actually calls it ─────────────────────────────────────

@pytest.mark.parametrize("module,fmt", [
    ("ui.giii.kl_extraction", "kl"),
    ("ui.giii.msg_extraction", "msg"),
    ("ui.giii.tk_eu_extraction", "tk_eu"),
    ("ui.giii.infornexus_extraction", "infor_nexus"),
])
def test_each_fax_section_persists_what_it_parsed(module, fmt):
    """A section that parses but never saves is invisible to the combined
    views — the exact gap this change closes."""
    pytest.importorskip("streamlit")
    import importlib
    import inspect

    src = inspect.getsource(importlib.import_module(module))
    assert "persist_fax_pos(" in src, f"{module} does not save its POs"
    assert f'"{fmt}"' in src
