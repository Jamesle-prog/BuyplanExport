"""Regression tests for the Sky East upload-time new-brand shipping-sample
requirement prompt.

Uploading a PO for a brand never seen before in 船样要求 (shipping sample
requirements) used to leave the requirement silently blank until someone
noticed at buy-plan generation time (BoatSampleStore.get_batch skips brands
with empty req_text, and the existing register_missing_brands()-at-
generation-time path only shows a static "go fill it in" warning). Detecting
new brands at UPLOAD time and prompting for the value there is a separate,
more proactive flow.
"""
from __future__ import annotations

from auth.companies import COMPANY_SKY_EAST


def _make_contract(items, **over):
    from po_extractor.models.sky_east_data import SkyEastContract
    base = dict(pc_no="PC1", pc_date="2026-01-01", buyer="B", seller="S",
                currency="USD", payment_terms="TT", trade_term="FOB")
    base.update(over)
    return SkyEastContract(items=items, **base)


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


def test_se_distinct_brands_dedupes_and_preserves_first_seen_order():
    from ui.sky_east.processing import _se_distinct_brands

    contracts = [
        _make_contract([
            _make_item(brand="Anna Field"),
            _make_item(brand="About You"),
            _make_item(brand="Anna Field"),
        ]),
        _make_contract([
            _make_item(brand="Even&Odd"),
        ]),
    ]
    assert _se_distinct_brands(contracts) == ["Anna Field", "About You", "Even&Odd"]


def test_se_distinct_brands_skips_blank_and_whitespace_only():
    from ui.sky_east.processing import _se_distinct_brands

    contracts = [_make_contract([
        _make_item(brand=""), _make_item(brand="   "), _make_item(brand="Real Brand"),
    ])]
    assert _se_distinct_brands(contracts) == ["Real Brand"]


def test_se_distinct_brands_empty_contracts_list():
    from ui.sky_east.processing import _se_distinct_brands
    assert _se_distinct_brands([]) == []


def test_unseen_brand_detected_against_boat_sample_store(tmp_path):
    """Exercises the exact store calls _run_sky_east_processing relies on:
    a brand never upserted is absent from list_known_brands (so it's
    "unseen"); after upsert() it's present."""
    from po_extractor.store.boat_sample_store import BoatSampleStore

    store = BoatSampleStore(str(tmp_path / "bs.db"))
    known = store.list_known_brands(COMPANY_SKY_EAST)
    assert "Anna Field" not in known

    store.upsert(COMPANY_SKY_EAST, "Anna Field", "Confirm before shipping")

    known = store.list_known_brands(COMPANY_SKY_EAST)
    assert "Anna Field" in known
    assert store.get(COMPANY_SKY_EAST, "Anna Field") == "Confirm before shipping"


def test_upsert_with_blank_text_still_registers_brand(tmp_path):
    """Saving the prompt with a blank requirement (no requirement applies)
    must still register the brand so it isn't prompted again next upload."""
    from po_extractor.store.boat_sample_store import BoatSampleStore

    store = BoatSampleStore(str(tmp_path / "bs.db"))
    store.upsert(COMPANY_SKY_EAST, "No Req Brand", "")

    assert "No Req Brand" in store.list_known_brands(COMPANY_SKY_EAST)
    assert store.get(COMPANY_SKY_EAST, "No Req Brand") == ""


# ── most_common_requirement: what the new-brand prompt pre-fills with ───────

def test_most_common_requirement_picks_the_majority_answer(tmp_path):
    from po_extractor.store.boat_sample_store import BoatSampleStore

    store = BoatSampleStore(str(tmp_path / "bs.db"))
    store.upsert(COMPANY_SKY_EAST, "A", "M码齐色2套，S码齐色1套")
    store.upsert(COMPANY_SKY_EAST, "B", "M码齐色2套，S码齐色1套")
    store.upsert(COMPANY_SKY_EAST, "C", "Something rare")

    assert store.most_common_requirement(COMPANY_SKY_EAST) == "M码齐色2套，S码齐色1套"


def test_most_common_requirement_is_empty_with_no_history(tmp_path):
    from po_extractor.store.boat_sample_store import BoatSampleStore

    store = BoatSampleStore(str(tmp_path / "bs.db"))
    assert store.most_common_requirement(COMPANY_SKY_EAST) == ""


def test_most_common_requirement_ignores_blank_answers(tmp_path):
    """A brand explicitly marked as having no requirement (blank, but
    registered) must not make '' win as the 'most common' answer."""
    from po_extractor.store.boat_sample_store import BoatSampleStore

    store = BoatSampleStore(str(tmp_path / "bs.db"))
    store.upsert(COMPANY_SKY_EAST, "No Req 1", "")
    store.upsert(COMPANY_SKY_EAST, "No Req 2", "")
    store.upsert(COMPANY_SKY_EAST, "No Req 3", "")
    store.upsert(COMPANY_SKY_EAST, "Real Answer", "Confirm before shipping")

    assert store.most_common_requirement(COMPANY_SKY_EAST) == "Confirm before shipping"


def test_most_common_requirement_breaks_ties_by_most_recent(tmp_path):
    """Two answers tied on frequency -- the one saved more recently wins."""
    from po_extractor.store.boat_sample_store import BoatSampleStore

    store = BoatSampleStore(str(tmp_path / "bs.db"))
    store.upsert(COMPANY_SKY_EAST, "Old", "Answer A")
    store.upsert(COMPANY_SKY_EAST, "New", "Answer B")
    # Backdate "Old" directly -- upsert() always stamps "now", so this is the
    # only way to give the two rows distinct, controlled timestamps.
    with store._conn() as conn:
        conn.execute(
            "UPDATE boat_sample_req SET updated_at=? WHERE brand='Old'",
            ("2020-01-01T00:00:00",),
        )

    assert store.most_common_requirement(COMPANY_SKY_EAST) == "Answer B"


def test_most_common_requirement_is_scoped_to_its_own_company(tmp_path):
    """A different company's convention must never leak in as the default."""
    from po_extractor.store.boat_sample_store import BoatSampleStore

    store = BoatSampleStore(str(tmp_path / "bs.db"))
    store.upsert(COMPANY_SKY_EAST, "Brand A", "Sky East's usual answer")
    store.upsert("Some Other Company", "Brand X", "A totally different answer")
    store.upsert("Some Other Company", "Brand Y", "A totally different answer")

    assert store.most_common_requirement(COMPANY_SKY_EAST) == "Sky East's usual answer"
    assert (store.most_common_requirement("Some Other Company")
            == "A totally different answer")
