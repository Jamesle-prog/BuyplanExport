"""Tests for fabric_master versioning: snapshot history, incremental diff log,
version-scoped enrichment, and pruning.

Locks the v2.75.0 feature: every ``import_from_xlsx`` call becomes a new
version (current + 3 previous snapshots stay queryable; older snapshot DATA
is pruned but ``fabric_versions``/``fabric_version_diff`` never are), and
``get_batch_enrichment`` can be pinned to a specific historical version.
"""
from __future__ import annotations

import io

import openpyxl
import pytest

from po_extractor.store.fabric_master_store import FabricMasterStore


def _make_fabric_xlsx(rows: list[dict]) -> bytes:
    """Build a minimal 面料统计表.xlsx ('all' sheet) from row dicts keyed by
    quality_no/composition_en/weight_gsm/cuttable_width_cm."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "all"
    ws.append(["公司面料编号", "面料成分(英文)", "克重(gsm)", "有效门幅(cm)"])
    for r in rows:
        ws.append([r.get("quality_no"), r.get("composition_en"),
                   r.get("weight_gsm"), r.get("cuttable_width_cm")])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _import(store, tmp_path, name: str, rows: list[dict]) -> dict:
    path = tmp_path / name
    path.write_bytes(_make_fabric_xlsx(rows))
    return store.import_from_xlsx(str(path), source_file_name=name)


@pytest.fixture
def store(tmp_path):
    return FabricMasterStore(str(tmp_path / "fabric_master.db"))


def test_first_import_creates_version_1_all_added(store, tmp_path):
    result = _import(store, tmp_path, "v1.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 200, "cuttable_width_cm": 140},
        {"quality_no": "B", "composition_en": "100%Poly", "weight_gsm": 150, "cuttable_width_cm": 150},
    ])
    assert result["version_id"] == 1
    assert result["inserted"] == 2 and result["updated"] == 0

    versions = store.list_versions()
    assert len(versions) == 1 and versions[0]["version_id"] == 1
    assert versions[0]["row_count"] == 2

    summary = store.get_diff_summary(1)
    assert summary == {"added": 2, "removed": 0, "changed": 0}
    diff = store.get_version_diff(1)
    assert {d["quality_no"] for d in diff} == {"A", "B"}
    assert all(d["change_type"] == "added" for d in diff)


def test_second_import_diffs_changed_field(store, tmp_path):
    _import(store, tmp_path, "v1.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 200, "cuttable_width_cm": 140},
    ])
    result = _import(store, tmp_path, "v2.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 220, "cuttable_width_cm": 140},
    ])
    assert result["version_id"] == 2
    summary = store.get_diff_summary(2)
    assert summary == {"added": 0, "removed": 0, "changed": 1}

    diff = store.get_version_diff(2)
    weight_diff = next(d for d in diff if d["field"] == "weight_gsm")
    assert weight_diff["quality_no"] == "A"
    assert weight_diff["old_value"] == "200.0"
    assert weight_diff["new_value"] == "220.0"
    # composition_en unchanged -- must NOT appear in the diff
    assert not any(d["field"] == "composition_en" for d in diff)


def test_removed_row_only_detected_after_delete(store, tmp_path):
    """Update/Add mode never deletes, so a row absent from a later upload but
    never explicitly deleted must NOT show as 'removed' -- it's still live."""
    _import(store, tmp_path, "v1.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 200, "cuttable_width_cm": 140},
        {"quality_no": "B", "composition_en": "100%Poly", "weight_gsm": 150, "cuttable_width_cm": 150},
    ])
    # Simulate "Update/Add": B is simply omitted from the new file, but never deleted.
    result = _import(store, tmp_path, "v2_update.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 200, "cuttable_width_cm": 140},
    ])
    assert store.get_diff_summary(result["version_id"]) == {"added": 0, "removed": 0, "changed": 0}
    assert store.count() == 2   # B is still there, untouched

    # Now simulate "Clear & Reimport": delete_all() then a fresh, smaller file.
    store.delete_all()
    result2 = _import(store, tmp_path, "v3_clear.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 200, "cuttable_width_cm": 140},
        {"quality_no": "C", "composition_en": "100%Wool", "weight_gsm": 300, "cuttable_width_cm": 145},
    ])
    summary = store.get_diff_summary(result2["version_id"])
    assert summary == {"added": 1, "removed": 1, "changed": 0}
    diff = store.get_version_diff(result2["version_id"])
    assert {d["quality_no"]: d["change_type"] for d in diff} == {"B": "removed", "C": "added"}


def test_version_numbering_increments_sequentially(store, tmp_path):
    ids = []
    for i in range(4):
        r = _import(store, tmp_path, f"v{i}.xlsx", [
            {"quality_no": f"Q{i}", "composition_en": "Cotton", "weight_gsm": 100 + i, "cuttable_width_cm": 140},
        ])
        ids.append(r["version_id"])
    assert ids == [1, 2, 3, 4]
    assert [v["version_id"] for v in store.list_versions()] == [4, 3, 2, 1]


def test_pruning_keeps_current_plus_3_previous(store, tmp_path):
    """5 uploads: only versions 2-5 keep snapshot DATA; version 1's data is
    pruned, but its metadata + diff rows must still exist (never pruned)."""
    for i in range(1, 6):
        _import(store, tmp_path, f"v{i}.xlsx", [
            {"quality_no": f"Q{i}", "composition_en": "Cotton", "weight_gsm": 100, "cuttable_width_cm": 140},
        ])

    with store._conn() as conn:
        snap_versions = {r[0] for r in conn.execute(
            "SELECT DISTINCT version_id FROM fabric_master_snapshot").fetchall()}
    assert snap_versions == {2, 3, 4, 5}, (
        f"expected only the current + 3 previous versions to retain snapshot "
        f"data, got {snap_versions}"
    )

    # Metadata and diff log survive regardless of pruning.
    assert {v["version_id"] for v in store.list_versions()} == {1, 2, 3, 4, 5}
    assert store.get_diff_summary(1) == {"added": 1, "removed": 0, "changed": 0}

    # get_batch_enrichment against a pruned version now returns nothing.
    assert store.get_batch_enrichment(["Q1"], version_id=1) == {}
    # ...but a retained version still resolves.
    assert store.get_batch_enrichment(["Q2"], version_id=2) != {}


def test_get_batch_enrichment_no_version_matches_live_table(store, tmp_path):
    """Regression guard: get_batch_enrichment(fabric_nos) with no version_id
    must behave exactly as before versioning existed -- reads live fabric_master."""
    _import(store, tmp_path, "v1.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 200, "cuttable_width_cm": 140},
    ])
    _import(store, tmp_path, "v2.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 999, "cuttable_width_cm": 140},
    ])
    live = store.get_batch_enrichment(["A"])
    assert live["A"]["weight_gsm"] == 999   # reflects the LATEST live state


def test_get_batch_enrichment_specific_version_reads_snapshot(store, tmp_path):
    _import(store, tmp_path, "v1.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 200, "cuttable_width_cm": 140},
    ])
    _import(store, tmp_path, "v2.xlsx", [
        {"quality_no": "A", "composition_en": "100%Cotton", "weight_gsm": 999, "cuttable_width_cm": 140},
    ])
    v1_data = store.get_batch_enrichment(["A"], version_id=1)
    assert v1_data["A"]["weight_gsm"] == 200   # the OLDER value, from the v1 snapshot

    v2_data = store.get_batch_enrichment(["A"], version_id=2)
    assert v2_data["A"]["weight_gsm"] == 999


def test_uploaded_by_defaults_to_system_outside_streamlit(store, tmp_path):
    result = _import(store, tmp_path, "v1.xlsx", [
        {"quality_no": "A", "composition_en": "Cotton", "weight_gsm": 100, "cuttable_width_cm": 140},
    ])
    versions = store.list_versions()
    assert versions[0]["uploaded_by"] == "system"
    assert versions[0]["version_id"] == result["version_id"]
