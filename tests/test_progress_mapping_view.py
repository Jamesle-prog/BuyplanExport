"""Tests for ui/progress_mapping_view.py's pure-logic helpers -- record
identity keying and the field-level diff shown for updating records.
Streamlit-rendering parts (file uploader, buttons) aren't unit-tested here,
consistent with the rest of this codebase's UI-layer test coverage.
"""
from __future__ import annotations

from po_extractor.lookups.progress_lookup import _norm_key, _normalise_color
from ui.progress_mapping_view import _diff_progress_record, _record_key


def _make_record(**overrides) -> dict:
    base = {
        "contract_no": "26302-ZA7148", "pc_no": "HHPPC048",
        "style": _norm_key("DR5124"), "style_display": "DR5124",
        "color": "NAVY", "color_norm": _normalise_color("NAVY"),
        "color_code": "52#", "label_color": "黑色", "cn_color": "藏青",
        "ex_fty": "2026-08-11", "qty": "300", "zalando_po": "", "brand": "Anna Field",
        "fabric": "", "test_note": "", "color_summary": "", "launch_date": "", "remarks": "",
    }
    base.update(overrides)
    return base


def test_record_key_uses_normalised_pc_no():
    rec = _make_record(pc_no="  hhppc048  ")
    assert _record_key(rec) == (_norm_key("HHPPC048"), "DR5124", "NAVY")


def test_record_key_distinguishes_by_colour():
    navy = _make_record(color="NAVY", color_norm=_normalise_color("NAVY"))
    black = _make_record(color="BLACK", color_norm=_normalise_color("BLACK"))
    assert _record_key(navy) != _record_key(black)


def test_diff_progress_record_no_changes():
    old_db_row = {
        "contract_no": "26302-ZA7148", "color_en": "NAVY", "color_cn": "藏青",
        "color_code": "52#", "label_color": "黑色", "ex_fty_date": "2026-08-11",
        "qty": "300", "zalando_po": "", "brand": "Anna Field", "fabric_detail": "",
        "test_note": "", "color_summary": "", "launch_date": "", "remarks": "",
    }
    new_record = _make_record()
    assert _diff_progress_record(old_db_row, new_record) == []


def test_diff_progress_record_detects_contract_no_change():
    old_db_row = {
        "contract_no": "OLD-CONTRACT", "color_en": "NAVY", "color_cn": "藏青",
        "color_code": "52#", "label_color": "黑色", "ex_fty_date": "2026-08-11",
        "qty": "300", "zalando_po": "", "brand": "Anna Field", "fabric_detail": "",
        "test_note": "", "color_summary": "", "launch_date": "", "remarks": "",
    }
    new_record = _make_record(contract_no="NEW-CONTRACT")
    diff = _diff_progress_record(old_db_row, new_record)
    assert len(diff) == 1
    assert diff[0]["Field"] == "Contract No."
    assert diff[0]["Stored"] == "OLD-CONTRACT"
    assert diff[0]["In File"] == "NEW-CONTRACT"


def test_diff_progress_record_detects_multiple_field_changes():
    old_db_row = {
        "contract_no": "26302-ZA7148", "color_en": "NAVY", "color_cn": "藏青",
        "color_code": "52#", "label_color": "黑色", "ex_fty_date": "2026-08-11",
        "qty": "300", "zalando_po": "", "brand": "Anna Field", "fabric_detail": "",
        "test_note": "", "color_summary": "", "launch_date": "", "remarks": "",
    }
    new_record = _make_record(color_code="53#", brand="Even&Odd")
    diff = _diff_progress_record(old_db_row, new_record)
    fields_changed = {d["Field"] for d in diff}
    assert fields_changed == {"Color Code", "Brand"}


def test_diff_progress_record_ignores_routine_churn_fields():
    """Per review policy, ex_fty / qty / test_note / color_summary /
    launch_date / remarks are NOT flagged for review (they still get
    overwritten on import) -- a record differing only in them is 'unchanged'."""
    old_db_row = {
        "contract_no": "26302-ZA7148", "color_en": "NAVY", "color_cn": "藏青",
        "color_code": "52#", "label_color": "黑色", "ex_fty_date": "2026-08-11",
        "qty": "300", "zalando_po": "", "brand": "Anna Field", "fabric_detail": "",
        "test_note": "", "color_summary": "", "launch_date": "", "remarks": "",
    }
    new_record = _make_record(ex_fty="2026-09-01", qty="500",
                              test_note="passed", remarks="rush order")
    assert _diff_progress_record(old_db_row, new_record) == []


def test_diff_progress_record_empty_old_row_treated_as_all_blank():
    """A brand-new key with no stored row (old_db_row={}) should not crash --
    every populated field in the new record shows as a diff from blank.
    """
    new_record = _make_record()
    diff = _diff_progress_record({}, new_record)
    assert any(d["Field"] == "Contract No." and d["Stored"] == "—" for d in diff)
