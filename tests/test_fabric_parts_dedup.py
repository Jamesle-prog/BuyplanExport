"""Tests for find_duplicate_fabric_combos() / delete_fabric_combo() in
po_extractor/store/_po_store_fabric.py — the duplicate-combo health check
used by the Fabric Mapping tab.

Regression coverage for a real production issue: BL3069 and
ZLD060/S24DTR003 were each stored twice under different combo_idx values
with byte-for-byte identical fabric parts, which would have produced an
extra, identical sheet per style in the Sky East Buy Plan export.
"""
from __future__ import annotations

import pytest

from po_extractor.models.fabric_part import FabricPart
from po_extractor.store.po_store import POStore


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "test.db"
    return POStore(str(db))


def test_no_duplicates_on_clean_data(store):
    store.save_fabric_parts_batch("sky_east", {
        "DR5124": [FabricPart(combo_idx=0, seq=1, body_part="Main Body", hhn_no="HHN-JA-01715")],
    })
    assert store.find_duplicate_fabric_combos() == []


def test_detects_identical_combo_stored_twice(store):
    # Same style, same content, saved under combo_idx 0 and 1 — the exact
    # shape of the BL3069 / ZLD060 production bug.
    store.save_fabric_parts_batch("sky_east", {
        "BL3069": [
            FabricPart(combo_idx=0, seq=1, body_part="Main Body", hhn_no="HHN-JA-01715"),
            FabricPart(combo_idx=1, seq=1, body_part="Main Body", hhn_no="HHN-JA-01715"),
        ],
    })
    dups = store.find_duplicate_fabric_combos()
    assert len(dups) == 1
    d = dups[0]
    assert d["source"] == "sky_east"
    assert d["style"] == "BL3069"
    assert d["keep_combo_idx"] == 0
    assert d["remove_combo_idx"] == [1]


def test_multi_seq_combo_duplicate(store):
    # Two-fabric combo (Main Body + Pocket) duplicated — the ZLD060 shape.
    store.save_fabric_parts_batch("sky_east", {
        "ZLD060": [
            FabricPart(combo_idx=0, seq=1, body_part="Main Body", hhn_no="HHN-DB-YS240782"),
            FabricPart(combo_idx=0, seq=2, body_part="Pocket",    hhn_no="HHN-CJS-00074"),
            FabricPart(combo_idx=1, seq=1, body_part="Main Body", hhn_no="HHN-DB-YS240782"),
            FabricPart(combo_idx=1, seq=2, body_part="Pocket",    hhn_no="HHN-CJS-00074"),
        ],
    })
    dups = store.find_duplicate_fabric_combos()
    assert len(dups) == 1
    assert dups[0]["remove_combo_idx"] == [1]


def test_different_combos_are_not_flagged(store):
    # Two genuinely different fabric combinations for the same style — not a
    # duplicate, must not be flagged.
    store.save_fabric_parts_batch("sky_east", {
        "DR5396": [
            FabricPart(combo_idx=0, seq=1, body_part="Main Body", hhn_no="HHN-JA-01715"),
            FabricPart(combo_idx=1, seq=1, body_part="Main Body", hhn_no="HHN-JA-01715"),
            FabricPart(combo_idx=1, seq=2, body_part="Stripe",    hhn_no="HHN-JA-01715"),
        ],
    })
    assert store.find_duplicate_fabric_combos() == []


def test_scoped_by_source(store):
    # Same style name under two different sources, each with its own
    # duplicate — find_duplicate_fabric_combos(source=...) must only report
    # the requested source, and not cross-contaminate between companies.
    store.save_fabric_parts_batch("sky_east", {
        "SHARED": [
            FabricPart(combo_idx=0, seq=1, body_part="Main Body", hhn_no="HHN-AAA"),
            FabricPart(combo_idx=1, seq=1, body_part="Main Body", hhn_no="HHN-AAA"),
        ],
    })
    store.save_fabric_parts_batch("giii", {
        "SHARED": [
            FabricPart(combo_idx=0, seq=1, body_part="Main Body", hhn_no="HHN-BBB"),
        ],
    })
    sky_dups = store.find_duplicate_fabric_combos(source="sky_east")
    giii_dups = store.find_duplicate_fabric_combos(source="giii")
    assert len(sky_dups) == 1 and sky_dups[0]["source"] == "sky_east"
    assert giii_dups == []


def test_delete_fabric_combo_removes_only_target_combo(store):
    store.save_fabric_parts_batch("sky_east", {
        "BL3069": [
            FabricPart(combo_idx=0, seq=1, body_part="Main Body", hhn_no="HHN-JA-01715"),
            FabricPart(combo_idx=1, seq=1, body_part="Main Body", hhn_no="HHN-JA-01715"),
        ],
    })
    deleted = store.delete_fabric_combo("sky_east", "BL3069", 1)
    assert deleted == 1

    remaining = store.load_fabric_parts_for_styles(["BL3069"], source="sky_east")
    assert len(remaining["BL3069"]) == 1
    assert remaining["BL3069"][0].combo_idx == 0
    assert store.find_duplicate_fabric_combos() == []


def test_cleanup_workflow_matches_scan_then_delete(store):
    """End-to-end: scan finds it, delete_fabric_combo() removes it, re-scan is clean."""
    store.save_fabric_parts_batch("sky_east", {
        "BL3069": [
            FabricPart(combo_idx=0, seq=1, body_part="Main Body", hhn_no="HHN-JA-01715"),
            FabricPart(combo_idx=1, seq=1, body_part="Main Body", hhn_no="HHN-JA-01715"),
        ],
        "ZLD060": [
            FabricPart(combo_idx=0, seq=1, body_part="Main Body", hhn_no="HHN-DB-YS240782"),
            FabricPart(combo_idx=0, seq=2, body_part="Pocket",    hhn_no="HHN-CJS-00074"),
            FabricPart(combo_idx=1, seq=1, body_part="Main Body", hhn_no="HHN-DB-YS240782"),
            FabricPart(combo_idx=1, seq=2, body_part="Pocket",    hhn_no="HHN-CJS-00074"),
        ],
    })
    dups = store.find_duplicate_fabric_combos()
    assert len(dups) == 2

    total_deleted = 0
    for d in dups:
        for cidx in d["remove_combo_idx"]:
            total_deleted += store.delete_fabric_combo(d["source"], d["style"], cidx)
    assert total_deleted == 3  # 1 row for BL3069 + 2 rows for ZLD060

    assert store.find_duplicate_fabric_combos() == []
