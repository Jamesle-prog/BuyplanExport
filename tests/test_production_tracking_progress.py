"""Tests for the PO-progress-by-style helpers on ProductionTrackingStore:
overall_progress, current_stage, get_batch_by_po_styles.

These back the Tracking tab's Dashboard/Overview (Stage 7) and the Sky East
buy plan exporter's best-effort milestone enrichment.
"""
from __future__ import annotations

import pytest

from po_extractor.store.production_tracking_store import ProductionTrackingStore
from po_extractor.store._production_tracking_schema import STAGES


@pytest.fixture
def store(tmp_path):
    return ProductionTrackingStore(str(tmp_path / "po_history.db"))


def _upsert(store, po, style, stage_fields=None, **kw):
    return store.upsert(
        po_number=po, style=style,
        factory=kw.get("factory", ""), company=kw.get("company", "GIII"),
        updated_by="tester", overall_notes="",
        use_substitute_materials=1,
        stage_fields=stage_fields or {},
        dep_fields={}, qc_fields={},
    )


def test_overall_progress_counts_done_across_applicable_stages_only(store, tmp_path):
    _upsert(store, "PO1", "STY1", stage_fields={
        "trim_layout_status": "Done",
        "trim_purchase_status": "Done",
        # Optional sample stages default applicable=0 -- must be excluded
        # from the denominator even if a status happens to be set.
        "proto_sample_status": "Done",
        "proto_sample_applicable": 0,
    })
    record = store.get("PO1", "STY1")
    done, total = store.overall_progress(record)
    assert done == 2
    # 22 stages minus 5 optional-sample stages that default inapplicable
    assert total == len(STAGES) - 5


def test_overall_progress_includes_applicable_optional_sample(store):
    _upsert(store, "PO1", "STY1", stage_fields={
        "proto_sample_status": "Done",
        "proto_sample_applicable": 1,
    })
    record = store.get("PO1", "STY1")
    done, total = store.overall_progress(record)
    assert done == 1
    assert total == len(STAGES) - 4   # only 4 optional samples excluded now


def test_current_stage_is_first_not_done(store):
    _upsert(store, "PO1", "STY1", stage_fields={
        "trim_layout_status": "Done",
        "trim_purchase_status": "Done",
        "fabric_color_ld_status": "In Progress",
    })
    record = store.get("PO1", "STY1")
    assert store.current_stage(record) == "fabric_color_ld"


def test_current_stage_skips_inapplicable_optional_samples(store):
    # Every stage before pp_sample done/inapplicable; pp_sample not started.
    fields = {f"{s}_status": "Done" for s in [
        "trim_layout", "trim_purchase", "fabric_color_ld", "fabric_purchase",
        "base_size_pattern", "full_sized_pattern",
        "sample_trim_purchase", "sample_fabric_purchase",
    ]}
    _upsert(store, "PO1", "STY1", stage_fields=fields)
    record = store.get("PO1", "STY1")
    # All optional samples default applicable=0 -> skipped -> next is pp_sample
    assert store.current_stage(record) == "pp_sample"


def test_current_stage_none_when_all_applicable_stages_done(store):
    fields = {f"{s}_status": "Done" for s in STAGES}
    _upsert(store, "PO1", "STY1", stage_fields=fields)
    record = store.get("PO1", "STY1")
    assert store.current_stage(record) is None


def test_get_batch_by_po_styles_returns_keyed_dict(store):
    _upsert(store, "PO1", "STY1", stage_fields={"cutting_status": "Done"})
    _upsert(store, "PO1", "STY2", stage_fields={"sewing_status": "In Progress"})
    _upsert(store, "PO2", "STY1", stage_fields={})

    batch = store.get_batch_by_po_styles([
        ("PO1", "STY1"), ("PO1", "STY2"), ("PO-NOT-TRACKED", "X"),
    ])
    assert set(batch.keys()) == {("PO1", "STY1"), ("PO1", "STY2")}
    assert batch[("PO1", "STY1")]["cutting_status"] == "Done"
    assert batch[("PO1", "STY2")]["sewing_status"] == "In Progress"


def test_get_batch_by_po_styles_dedupes_and_strips(store):
    _upsert(store, "PO1", "STY1")
    batch = store.get_batch_by_po_styles([
        ("PO1", "STY1"), (" PO1 ", " STY1 "), ("PO1", "STY1"),
    ])
    assert len(batch) == 1


def test_get_batch_by_po_styles_empty_input(store):
    assert store.get_batch_by_po_styles([]) == {}
    assert store.get_batch_by_po_styles([("", "")]) == {}
