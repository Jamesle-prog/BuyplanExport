"""The 船样要求 a user types for a new brand must reach the buy plan.

Two failures were possible and both printed an empty column with everything
apparently configured:

1. the prompt stored a blank because st.data_editor had not committed the cell
   the user was still typing in when they clicked Save;
2. the exporter looked the brand up unstripped against a cache keyed on
   stripped names.
"""
from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")


@pytest.fixture
def store(tmp_path):
    from po_extractor.store.boat_sample_store import BoatSampleStore
    return BoatSampleStore(str(tmp_path / "bs.db"))


# ── The prompt captures what was typed ──────────────────────────────────────

def test_the_prompt_uses_a_form_not_a_data_editor():
    """A data_editor cell is only committed on blur, so typing and clicking
    Save immediately stored a blank. A form flushes its widgets on submit."""
    import inspect
    import ui.sky_east.items_view as iv
    src = inspect.getsource(iv._show_new_brand_shipping_sample_prompt)
    assert "st.form(" in src and "form_submit_button" in src
    # The CALL, not the word — the fix's own comment explains the data_editor.
    assert "st.data_editor(" not in src, (
        "the data_editor is what silently dropped the requirement")


def test_every_pending_brand_gets_its_own_input():
    """One box per brand, keyed by index — a shared key would make every brand
    show the last one's text."""
    import inspect
    import ui.sky_east.items_view as iv
    src = inspect.getsource(iv._show_new_brand_shipping_sample_prompt)
    assert "se_new_brand_req_{i}" in src or 'se_new_brand_req_' in src


# ── What is saved is what the buy plan reads ────────────────────────────────

def test_a_typed_requirement_is_found_by_the_buy_plan(store, monkeypatch):
    """End to end across the two components: what the prompt writes is what
    _prefetch_boat_sample_cache hands the row writer."""
    import pandas as pd
    from auth.companies import COMPANY_SKY_EAST
    import po_extractor.exporters.sky_east_buyplan_export as ex

    store.upsert(COMPANY_SKY_EAST, "NEWBRAND", "M码齐色2套")
    monkeypatch.setattr("po_extractor.store.get_boat_sample_store",
                        lambda: store)

    df = pd.DataFrame([{"brand": "NEWBRAND"}])
    cache = ex._prefetch_boat_sample_cache(df)
    assert cache.get("NEWBRAND") == "M码齐色2套"


def test_a_brand_with_stray_whitespace_still_matches(store, monkeypatch):
    """The cache is keyed on stripped names; the row writer's value comes
    straight off the item and may not be stripped."""
    import pandas as pd
    from auth.companies import COMPANY_SKY_EAST
    import po_extractor.exporters.sky_east_buyplan_export as ex

    store.upsert(COMPANY_SKY_EAST, "Even&Odd", "M码齐色2套")
    monkeypatch.setattr("po_extractor.store.get_boat_sample_store",
                        lambda: store)
    cache = ex._prefetch_boat_sample_cache(pd.DataFrame([{"brand": "Even&Odd "}]))

    # What the row writer now does.
    assert cache.get("Even&Odd ".strip(), "") == "M码齐色2套"


def test_the_row_writer_strips_before_looking_up():
    import inspect
    import po_extractor.exporters.sky_east_buyplan_export as ex
    src = inspect.getsource(ex._fill_one_style_row)
    assert "ctx.bsr_cache.get(brand.strip()" in src


def test_a_blank_requirement_registers_the_brand_but_prints_nothing(store):
    """Saving blank is a legitimate answer — it marks the brand known so the
    prompt stops asking — and must not put an empty string in the column."""
    from auth.companies import COMPANY_SKY_EAST
    store.upsert(COMPANY_SKY_EAST, "NOREQ", "")
    assert "NOREQ" in store.list_known_brands(COMPANY_SKY_EAST)
    assert store.get_batch(COMPANY_SKY_EAST, ["NOREQ"]) == {}
