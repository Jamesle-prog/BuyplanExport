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


# ── 船样要求 is compulsory ───────────────────────────────────────────────────
#
# "Compulsory" needs two answers to be possible, not one: a requirement, or an
# explicit "this brand has none". Blank alone means nobody has decided yet, and
# that now holds the buy plan instead of printing an empty column silently.

def test_blank_is_never_an_answer(store):
    """There is no "this brand has none" escape: blank always counts as
    outstanding, so the prompt keeps asking and the buy plan stays held."""
    from auth.companies import COMPANY_SKY_EAST as CO
    store.upsert(CO, "BLANK", "")
    store.upsert(CO, "SPACES", "   ")
    assert store.brands_missing_requirement(CO, ["BLANK", "SPACES"]) == [
        "BLANK", "SPACES"]


def test_a_bare_blank_is_not_an_answer(store):
    from auth.companies import COMPANY_SKY_EAST as CO
    store.upsert(CO, "UNANSWERED", "")
    assert store.brands_missing_requirement(CO, ["UNANSWERED"]) == ["UNANSWERED"]


def test_a_brand_never_seen_is_missing(store):
    from auth.companies import COMPANY_SKY_EAST as CO
    assert store.brands_missing_requirement(CO, ["NEVERSEEN"]) == ["NEVERSEEN"]


def test_text_clears_the_outstanding_state(store):
    from auth.companies import COMPANY_SKY_EAST as CO
    store.upsert(CO, "B", "")
    store.upsert(CO, "B", "3 pcs")
    assert store.brands_missing_requirement(CO, ["B"]) == []
    assert store.get_batch(CO, ["B"]) == {"B": "3 pcs"}


def test_the_existing_blank_rows_are_reported_as_missing(store):
    """The three brands saved blank before this shipped must surface, not sit
    silently — that is the whole point of making it compulsory."""
    from auth.companies import COMPANY_SKY_EAST as CO
    for b in ("Anna Field by Zalando", "Brand", "YOURTURN"):
        store.upsert(CO, b, "")
    store.upsert(CO, "Even&Odd", "M码齐色2套")
    missing = store.brands_missing_requirement(
        CO, ["Even&Odd", "Anna Field by Zalando", "Brand", "YOURTURN"])
    assert missing == ["Anna Field by Zalando", "Brand", "YOURTURN"]


def test_the_prompt_refuses_a_brand_with_no_answer():
    import inspect
    import ui.sky_east.items_view as iv
    src = inspect.getsource(iv._show_new_brand_shipping_sample_prompt)
    assert "unanswered" in src
    assert "This brand has no" not in src, "there is no blank escape any more"


def test_generation_is_held_when_a_brand_has_no_answer():
    import inspect
    import ui.sky_east.history as h
    src = inspect.getsource(h._show_se_buyplan_section) if hasattr(
        h, "_show_se_buyplan_section") else inspect.getsource(h)
    assert "_se_buyplan_boat_sample_preflight" in src
    assert "Cannot generate: these brands have no 船样要求" in src


def test_the_prompt_returns_for_a_brand_left_blank_long_ago(monkeypatch, store):
    """"Always pop up" — the ask is driven by what is still blank in the
    store, not only by what the last upload happened to introduce. Brands
    registered before the requirement became compulsory must resurface."""
    import pandas as pd
    import ui.sky_east_view as v
    from auth.companies import COMPANY_SKY_EAST as CO

    store.upsert(CO, "Even&Odd", "M码齐色2套")     # answered
    store.upsert(CO, "YOURTURN", "")               # blank from before

    monkeypatch.setattr("ui.stores.get_boat_sample_store", lambda: store)
    monkeypatch.setattr(
        "ui.stores.get_sky_east_store",
        lambda: type("S", (), {"list_items": lambda self, **k: pd.DataFrame(
            [{"brand": "Even&Odd"}, {"brand": "YOURTURN"}])})())
    monkeypatch.setattr(v.st, "session_state", {})

    assert v._brands_awaiting_requirement() == ["YOURTURN"]


def test_a_brand_from_the_current_upload_is_included_too(monkeypatch, store):
    """The store alone would miss a brand the running upload just introduced
    but has not registered yet."""
    import pandas as pd
    import ui.sky_east_view as v
    from ui.session_keys import SK

    monkeypatch.setattr("ui.stores.get_boat_sample_store", lambda: store)
    monkeypatch.setattr(
        "ui.stores.get_sky_east_store",
        lambda: type("S", (), {"list_items": lambda self, **k: pd.DataFrame()})())
    monkeypatch.setattr(v.st, "session_state", {SK.SE_NEW_BRAND_PENDING: ["FRESH"]})

    assert v._brands_awaiting_requirement() == ["FRESH"]


def test_nothing_outstanding_shows_nothing(monkeypatch):
    """The prompt is now called unconditionally, so it must stay silent when
    every brand is answered — otherwise it would announce '0 brand(s)'."""
    import ui.sky_east.items_view as iv
    calls = []
    monkeypatch.setattr(iv.st, "info", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(iv.st, "expander", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not render the panel when nothing is outstanding")))
    iv._show_new_brand_shipping_sample_prompt([])
    assert calls == []
