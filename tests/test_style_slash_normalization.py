"""A style's "/" matches "_" everywhere — but is never rewritten.

Client files carry the same style both ways — ``TP3267-3/4SLV`` (a 3/4
sleeve) in the contract, ``TP3267-3_4SLV`` wherever a filename was involved,
because Windows filenames cannot hold "/". Compared raw, the two spellings
are different strings: fabric-mapping joins missed, search found one and not
the other.

Rule since 2026-09-01 (superseding the 2026-08-31 store-as-underscore
attempt, reverted the next day at the user's direction): **what the file
says is what is stored and shown** — displays and exports keep the slash.
Only comparisons use ``style_key`` ("/"·"\\" → "_"), the same raw-value /
matching-key split as ``sky_east_store.colour_key``.
"""
from __future__ import annotations

import pytest

from po_extractor.utils.style_norm import style_key


# ── the matching key itself ─────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("TP3267-3/4SLV", "TP3267-3_4SLV"),
    ("ZLD060/S24DTR003", "ZLD060_S24DTR003"),
    ("A/B/C", "A_B_C"),
    ("A\\B", "A_B"),                       # backslash too — same filename rule
    ("  PLAIN123  ", "PLAIN123"),
    ("ALREADY_OK", "ALREADY_OK"),
])
def test_style_key_treats_slash_as_underscore(raw, expected):
    assert style_key(raw) == expected


def test_non_strings_key_as_nothing():
    assert style_key(None) == ""
    assert style_key(123) == ""


# ── storage and display keep the file's spelling ────────────────────────────

def test_models_keep_the_style_verbatim():
    """The 2026-08-31 version rewrote "/" to "_" at model construction; that
    put the wrong spelling on buy plans and 核料 docs. Styles now pass
    through untouched."""
    from po_extractor.models.po_data import POMetadata, SizeRow
    from po_extractor.models.sky_east_data import SkyEastItem

    assert SizeRow("PO1", "TP3267-3/4SLV", "BLK", "M", 10, "1").style \
        == "TP3267-3/4SLV"
    assert POMetadata(po_number="P1", style="A/B").style == "A/B"
    assert POMetadata(po_number="P1").style is None
    item = SkyEastItem(
        pc_no="PC1", zalando_po="PO1", style="TP3267-3/4SLV",
        config_sku="AN6/21C", article_name="A", brand="B",
        color_name="BLK/WHT", colour_code="Q11", launch_date="",
        fabric_item_no="HHP-JS/1", fabrication="", contract_no="",
        sizes={"S": 1}, total_qty=1, fob_usd=1.0, total_cost_usd=1.0)
    assert item.style == "TP3267-3/4SLV"


def test_fabric_mapping_stores_the_spelling_it_was_given(tmp_path):
    from po_extractor.store.po_store import POStore
    from po_extractor.models.fabric_part import FabricPart

    s = POStore(str(tmp_path / "t.db"))
    s.save_fabric_parts(
        "sky_east", "ZLD060/S24DTR003",
        [FabricPart(seq=1, body_part="主面料", hhn_no="HHP-JS-1",
                    composition="100% PL", weight_gsm=180, width_cm=150)])
    assert s.list_mapped_styles("sky_east") == {"ZLD060/S24DTR003"}


# ── matching crosses the spellings, both directions ─────────────────────────

def test_mapping_saved_one_way_is_found_the_other_way(tmp_path):
    """The whole point: the mapping file said "_", the PO says "/" — the
    join lands, keyed under the CALLER's spelling so its lookups hit."""
    from po_extractor.store.po_store import POStore
    from po_extractor.models.fabric_part import FabricPart

    s = POStore(str(tmp_path / "t.db"))
    s.save_fabric_parts(
        "sky_east", "TP3267-3_4SLV",
        [FabricPart(seq=1, body_part="主面料", hhn_no="HHP-1",
                    composition="", weight_gsm=0, width_cm=0)])

    got = s.load_fabric_parts_for_styles(["TP3267-3/4SLV"], source="sky_east")
    assert "TP3267-3/4SLV" in got and got["TP3267-3/4SLV"]

    # and the reverse direction: stored "/", asked with "_"
    s2 = POStore(str(tmp_path / "t2.db"))
    s2.save_fabric_parts(
        "sky_east", "TP3267-3/4SLV",
        [FabricPart(seq=1, body_part="主面料", hhn_no="HHP-1",
                    composition="", weight_gsm=0, width_cm=0)])
    got2 = s2.load_fabric_parts_for_styles(["TP3267-3_4SLV"], source="sky_east")
    assert "TP3267-3_4SLV" in got2 and got2["TP3267-3_4SLV"]


def test_consumption_matches_across_spellings(tmp_path):
    from po_extractor.store.po_store import POStore
    s = POStore(str(tmp_path / "t.db"))
    s.save_fabric_consumption([{"style": "A_B", "cons_kg": 1.5}])
    got = s.load_fabric_consumption(["A/B"])
    assert "A/B" in got and got["A/B"]["cons_kg"] == 1.5


def test_tracking_never_forks_a_twin_across_spellings(tmp_path):
    """A "/" retype must land on the existing row — and the spelling first
    typed is the one that stays on screen."""
    from po_extractor.store.production_tracking_store import ProductionTrackingStore

    s = ProductionTrackingStore(str(tmp_path / "t.db"))
    s.upsert(po_number="PO1", style="ZLD060/S24DTR003", factory="F1",
             company="GIII", overall_notes="", use_substitute_materials=0,
             stage_fields={}, dep_fields={}, qc_fields={}, updated_by="t")
    s.upsert(po_number="PO1", style="ZLD060_S24DTR003", factory="F2",
             company="GIII", overall_notes="", use_substitute_materials=0,
             stage_fields={}, dep_fields={}, qc_fields={}, updated_by="t")

    recs = s.list_all(allow_all=True)
    assert len(recs) == 1
    assert recs[0]["style"] == "ZLD060/S24DTR003"      # first spelling kept
    assert recs[0]["factory"] == "F2"                  # second save applied


def test_cutting_plan_style_filter_matches_across_spellings(tmp_path):
    from po_extractor.store.cutting_plan_store import CuttingPlanStore

    s = CuttingPlanStore(str(tmp_path / "t.db"))
    plan_id = s.save_plan({"plan_name": "P"}, source_file="x.pdf",
                          uploaded_by="t")
    s.set_links(plan_id, [{"pc_no": "PC1", "po_no": "PO1",
                           "style": "TP3267-3/4SLV"}])

    hits = s.plans_for_pos(styles=["TP3267-3_4SLV"])
    assert not hits.empty and int(hits.iloc[0]["plan_id"]) == plan_id
    # stored spelling untouched
    assert hits.iloc[0]["style"] == "TP3267-3/4SLV"
