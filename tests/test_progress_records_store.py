"""Tests for the persistent progress-records (大货进度表) store.

Covers po_extractor/store/_po_store_progress.py -- save/load/list/diff/delete
-- and the round trip through progress_lookup.parse_progress_rows() /
ProgressLookup.from_records(), which is what lets a buy plan run use the
saved data instead of requiring the file to be re-uploaded every time.
"""
from __future__ import annotations

import pytest

from po_extractor.lookups.progress_lookup import ProgressLookup, parse_progress_rows
from po_extractor.store.po_store import POStore


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "test.db"
    return POStore(str(db))


def _make_record(
    style="DR5124", style_display=None, pc_no="HHPPC048", color="NAVY",
    contract_no="26302-ZA7148", color_code="52#", cn_color="藏青",
    label_color="黑色", ex_fty="2026-08-11", qty="300", zalando_po="",
    brand="Anna Field", fabric="", test_note="", color_summary="",
    launch_date="", remarks="",
) -> dict:
    """Build a record dict in the exact shape parse_progress_rows() produces."""
    from po_extractor.lookups.progress_lookup import _norm_key, _normalise_color
    return {
        "contract_no": contract_no, "pc_no": pc_no,
        "style": _norm_key(style), "style_display": style_display or style,
        "color": color, "color_norm": _normalise_color(color),
        "color_code": color_code, "label_color": label_color,
        "cn_color": cn_color, "ex_fty": ex_fty, "qty": qty,
        "zalando_po": zalando_po, "brand": brand, "fabric": fabric,
        "image_id": "", "test_note": test_note, "color_summary": color_summary,
        "launch_date": launch_date, "remarks": remarks,
    }


def test_save_and_load_round_trip(store):
    rec = _make_record()
    n = store.save_progress_records_batch("sky_east", [rec])
    assert n == 1
    assert store.count_progress_records("sky_east") == 1

    loaded = store.load_progress_records("sky_east")
    assert len(loaded) == 1
    assert loaded[0]["contract_no"] == "26302-ZA7148"
    assert loaded[0]["style"] == "DR5124"
    assert loaded[0]["style_display"] == "DR5124"
    assert loaded[0]["cn_color"] == "藏青"


def test_upsert_overwrites_same_identity(store):
    rec = _make_record(contract_no="OLD-CONTRACT")
    store.save_progress_records_batch("sky_east", [rec])

    updated = _make_record(contract_no="NEW-CONTRACT")
    store.save_progress_records_batch("sky_east", [updated])

    assert store.count_progress_records("sky_east") == 1
    loaded = store.load_progress_records("sky_east")
    assert loaded[0]["contract_no"] == "NEW-CONTRACT"


def test_pc_no_normalisation_prevents_duplicate_rows(store):
    """Re-uploading with a differently-cased/whitespace PC No. must still
    match the same stored row -- not create a duplicate.
    """
    rec1 = _make_record(pc_no="HHPPC048")
    store.save_progress_records_batch("sky_east", [rec1])

    rec2 = _make_record(pc_no="  hhppc048  ", contract_no="UPDATED")
    store.save_progress_records_batch("sky_east", [rec2])

    assert store.count_progress_records("sky_east") == 1
    loaded = store.load_progress_records("sky_east")
    assert loaded[0]["contract_no"] == "UPDATED"


def test_different_colours_same_style_are_separate_rows(store):
    recs = [
        _make_record(color="NAVY",  contract_no="C1"),
        _make_record(color="BLACK", contract_no="C2"),
    ]
    store.save_progress_records_batch("sky_east", recs)
    assert store.count_progress_records("sky_east") == 2


def test_scoped_by_source(store):
    store.save_progress_records_batch("sky_east", [_make_record(contract_no="SE1")])
    store.save_progress_records_batch("giii",     [_make_record(contract_no="G1")])
    assert store.count_progress_records("sky_east") == 1
    assert store.count_progress_records("giii") == 1
    se_records = store.load_progress_records("sky_east")
    assert se_records[0]["contract_no"] == "SE1"


def test_list_progress_keys_and_get_by_keys(store):
    rec = _make_record()
    store.save_progress_records_batch("sky_east", [rec])

    from po_extractor.lookups.progress_lookup import _norm_key
    keys = store.list_progress_keys("sky_east")
    expected_key = (_norm_key("HHPPC048"), "DR5124", "NAVY")
    assert expected_key in keys

    by_key = store.get_progress_records_by_keys("sky_east", [expected_key])
    assert expected_key in by_key
    assert by_key[expected_key]["contract_no"] == "26302-ZA7148"


def test_delete_progress_records_scoped_to_source(store):
    store.save_progress_records_batch("sky_east", [_make_record()])
    store.save_progress_records_batch("giii", [_make_record()])

    deleted = store.delete_progress_records("sky_east")
    assert deleted == 1
    assert store.count_progress_records("sky_east") == 0
    assert store.count_progress_records("giii") == 1


def test_row_without_style_is_skipped(store):
    rec = _make_record()
    rec["style"] = ""   # no usable identity
    n = store.save_progress_records_batch("sky_east", [rec])
    assert n == 0
    assert store.count_progress_records("sky_east") == 0


def test_extra_descriptive_columns_persisted(store):
    rec = _make_record(
        test_note="OK", color_summary="NAVY 藏青52#",
        launch_date="2026-01-01", remarks="urgent",
    )
    store.save_progress_records_batch("sky_east", [rec])
    loaded = store.load_progress_records("sky_east")[0]
    assert loaded["test_note"] == "OK"
    assert loaded["color_summary"] == "NAVY 藏青52#"
    assert loaded["launch_date"] == "2026-01-01"
    assert loaded["remarks"] == "urgent"


def test_from_db_records_feeds_progresslookup_correctly(store):
    """The real point of this store: a buy plan run should be able to build
    a working ProgressLookup purely from saved DB records, with no file.
    """
    rec = _make_record()
    store.save_progress_records_batch("sky_east", [rec])

    loaded = store.load_progress_records("sky_east")
    pl = ProgressLookup.from_records(loaded)

    assert pl.get_contract_no("DR5124", "NAVY", pc_no="HHPPC048") == "26302-ZA7148"
    assert pl.get_cn_color("DR5124", "NAVY", pc_no="HHPPC048") == "藏青"
    assert pl.get_color_code("DR5124", "NAVY", pc_no="HHPPC048") == "52#"


def test_parse_and_persist_full_pipeline(store, tmp_path):
    """parse_progress_rows() -> save -> load -> ProgressLookup.from_records()
    end to end, using a hand-built workbook (avoids depending on any
    external file being present on disk).
    """
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    headers = ["序号", "合同号", "客人PC NO", "IMAGE", "款式", "BRAND",
              "英文颜色", "中文颜色", "中文颜色代码", "主标颜色", "PO离厂日期"]
    ws.append(headers)
    ws.append([1, "26302-ZA7148", "HHPPC048", "", "DR5124", "Anna Field",
              "NAVY", "藏青", "52#", "黑色", "2026-08-11"])
    path = tmp_path / "progress.xlsx"
    wb.save(str(path))

    records = parse_progress_rows(str(path))
    assert len(records) == 1

    store.save_progress_records_batch("sky_east", records)
    loaded = store.load_progress_records("sky_east")
    pl = ProgressLookup.from_records(loaded)
    assert pl.get_contract_no("DR5124", "NAVY", pc_no="HHPPC048") == "26302-ZA7148"
