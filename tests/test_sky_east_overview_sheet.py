"""Tests for the Sky East Buy Plan's "Overview" sheet — a flat, item-level
cross-check table (one row per style/PO/colour) inserted right after Index,
mirroring the Contract History item-browser preview plus the Chinese colour
name and colour code alongside the English name.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest
from openpyxl import load_workbook
from PIL import Image

from po_extractor.exporters.sky_east_buyplan_export import export_sky_east_buyplan
from po_extractor.lookups.progress_lookup import PCColorMatch


def _png_bytes(size=(20, 20), color=(200, 50, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def two_style_df():
    return pd.DataFrame([
        {
            "pc_no": "HHPPC048", "style": "DR5124", "brand": "Anna Field",
            "contract_no": "26302-ZA7148", "article_name": "LACE DRESS",
            "zalando_po": "PO001", "config_sku": "C1", "color_name": "dark blue",
            "fabric_item_no": "HHN-JA-01715", "fabrication": "cotton",
            "ex_fty_date": "2026-08-11",
            "xs": 30, "s": 82, "m": 119, "l": 102, "xl": 67, "xxl": 0,
        },
        {
            "pc_no": "HHPPC048", "style": "DR4578", "brand": "Anna Field",
            "contract_no": "26302-ZA7149", "article_name": "LONG SLEEVE DRESS",
            "zalando_po": "PO001", "config_sku": "C2", "color_name": "green",
            "fabric_item_no": "HHN-JSRSR-04068", "fabrication": "poly",
            "ex_fty_date": "2026-08-11",
            "xs": 22, "s": 61, "m": 90, "l": 77, "xl": 50, "xxl": 0,
        },
    ])


@pytest.fixture
def pc_color_lookup():
    return {
        ("HHPPC048", "DR5124", "Dark Blue"): PCColorMatch("藏青", "503", ""),
        ("HHPPC048", "DR4578", "Green"):     PCColorMatch("绿色", "602", ""),
    }


def test_overview_sheet_created_right_after_index(two_style_df, pc_color_lookup, tmp_path):
    path, _totals = export_sky_east_buyplan(
        two_style_df, cn_lookup={}, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup={}, cn_by_pc_lookup=pc_color_lookup,
    )
    wb = load_workbook(path)
    assert wb.sheetnames[0] == "Index"
    assert wb.sheetnames[1] == "Overview"
    assert set(wb.sheetnames[2:]) == {"DR5124", "DR4578"}


def test_overview_rows_include_english_and_chinese_color_plus_code(
    two_style_df, pc_color_lookup, tmp_path,
):
    path, _totals = export_sky_east_buyplan(
        two_style_df, cn_lookup={}, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup={}, cn_by_pc_lookup=pc_color_lookup,
    )
    ov = load_workbook(path)["Overview"]
    headers = [c.value for c in ov[1]]
    assert "Color (EN)" in headers
    assert "Color (CN)" in headers
    assert "Color Code" in headers

    def _row_dict(ri):
        return dict(zip(headers, [ov.cell(ri, c + 1).value for c in range(len(headers))]))

    rows = [_row_dict(r) for r in (2, 3)]
    by_style = {r["Style"]: r for r in rows}

    assert by_style["DR5124"]["Color (EN)"]   == "Dark Blue"
    assert by_style["DR5124"]["Color (CN)"]   == "藏青"
    assert by_style["DR5124"]["Color Code"]   == "503"
    assert by_style["DR5124"]["Contract No."] == "26302-ZA7148"
    assert by_style["DR5124"]["Total Qty"]    == 30 + 82 + 119 + 102 + 67

    assert by_style["DR4578"]["Color (EN)"] == "Green"
    assert by_style["DR4578"]["Color (CN)"] == "绿色"
    assert by_style["DR4578"]["Color Code"] == "602"


def test_overview_style_cell_hyperlinks_to_its_own_sheet(
    two_style_df, pc_color_lookup, tmp_path,
):
    path, _totals = export_sky_east_buyplan(
        two_style_df, cn_lookup={}, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup={}, cn_by_pc_lookup=pc_color_lookup,
    )
    wb = load_workbook(path)
    ov = wb["Overview"]
    headers = [c.value for c in ov[1]]
    style_col = headers.index("Style") + 1
    for ri in (2, 3):
        cell = ov.cell(ri, style_col)
        assert cell.hyperlink is not None
        target_sheet = cell.value
        assert f"'{target_sheet}'!A1" in cell.hyperlink.target


def test_overview_includes_fabric_and_display_key_columns(
    two_style_df, pc_color_lookup, tmp_path,
):
    path, _totals = export_sky_east_buyplan(
        two_style_df, cn_lookup={}, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup={}, cn_by_pc_lookup=pc_color_lookup,
    )
    ov = load_workbook(path)["Overview"]
    headers = [c.value for c in ov[1]]
    assert "Fabric 1" in headers
    assert "综合标识 Key 1" in headers

    fab_col = headers.index("Fabric 1") + 1
    key_col = headers.index("综合标识 Key 1") + 1
    fab_values = [ov.cell(r, fab_col).value for r in (2, 3)]
    key_values = [ov.cell(r, key_col).value for r in (2, 3)]
    assert any(v and "HHN-JA-01715" in v for v in fab_values)
    assert all(v for v in key_values)   # display key always non-empty (falls back to bare HHN)


def test_overview_embeds_style_photo_when_available(two_style_df, pc_color_lookup, tmp_path):
    photo_map = {"DR5124": [_png_bytes()]}
    path, _totals = export_sky_east_buyplan(
        two_style_df, cn_lookup={}, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup={}, cn_by_pc_lookup=pc_color_lookup,
        style_image_map=photo_map,
    )
    ov = load_workbook(path)["Overview"]
    headers = [c.value for c in ov[1]]
    assert "Photo" in headers
    assert len(ov._images) == 1   # only DR5124 has a photo; DR4578 doesn't


def test_overview_omits_photo_column_when_no_images_supplied(
    two_style_df, pc_color_lookup, tmp_path,
):
    path, _totals = export_sky_east_buyplan(
        two_style_df, cn_lookup={}, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup={}, cn_by_pc_lookup=pc_color_lookup,
    )
    ov = load_workbook(path)["Overview"]
    headers = [c.value for c in ov[1]]
    assert "Photo" not in headers


def test_overview_not_created_when_no_items(tmp_path):
    empty_df = pd.DataFrame(columns=[
        "pc_no", "style", "brand", "contract_no", "article_name", "zalando_po",
        "config_sku", "color_name", "xs", "s", "m", "l", "xl", "xxl", "ex_fty_date",
    ])
    path, _totals = export_sky_east_buyplan(
        empty_df, cn_lookup={}, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup={},
    )
    wb = load_workbook(path)
    assert "Overview" not in wb.sheetnames


# ---------------------------------------------------------------------------
# Decorative colour brackets — "(dark blue)" style values from some order files
# ---------------------------------------------------------------------------

def test_strip_color_brackets_single_wrap():
    from po_extractor.exporters.sky_east_buyplan_export import _strip_color_brackets
    assert _strip_color_brackets("(dark blue)") == "dark blue"
    assert _strip_color_brackets("(black)") == "black"


def test_strip_color_brackets_concatenated_two_tone():
    from po_extractor.exporters.sky_east_buyplan_export import _strip_color_brackets
    assert _strip_color_brackets("(black)(white)") == "black / white"
    assert _strip_color_brackets("(dark blue)(white)") == "dark blue / white"


def test_strip_color_brackets_passthrough_when_no_brackets():
    from po_extractor.exporters.sky_east_buyplan_export import _strip_color_brackets
    assert _strip_color_brackets("BLACK") == "BLACK"
    assert _strip_color_brackets("BLACK WITH WHITE STRAP AT WAIST AND BOTTOM") == \
        "BLACK WITH WHITE STRAP AT WAIST AND BOTTOM"
    assert _strip_color_brackets("") == ""
    assert _strip_color_brackets(None) is None


def test_buyplan_color_en_has_no_brackets_in_display(tmp_path):
    """Regression: a style whose stored colour is "(dark blue)" must show
    as plain "Dark Blue" in the buy plan, both on its own sheet and in the
    Overview sheet -- and must be usable as a lookup key (no leftover
    parentheses breaking an exact match against 大货进度表 / colour DB data).
    """
    df = pd.DataFrame([{
        "pc_no": "HHPPC048", "style": "DR5124", "brand": "Anna Field",
        "contract_no": "26302-ZA7148", "article_name": "LACE INSERT DRESS",
        "zalando_po": "PO001", "config_sku": "C1", "color_name": "(dark blue)",
        "xs": 30, "s": 82, "m": 0, "l": 0, "xl": 0, "xxl": 0,
    }])
    path, _totals = export_sky_east_buyplan(
        df, cn_lookup={}, output_dir=str(tmp_path), label_lookup={}, cn_code_lookup={},
    )
    wb = load_workbook(path)
    ov = wb["Overview"]
    headers = [c.value for c in ov[1]]
    color_col = headers.index("Color (EN)") + 1
    assert ov.cell(2, color_col).value == "Dark Blue"

    style_ws = wb["DR5124"]
    col_g_values = [style_ws.cell(r, 7).value for r in range(5, 8)]
    assert not any(v and "(" in str(v) for v in col_g_values)


# ---------------------------------------------------------------------------
# Colour source is authoritative — no silent cross-source fallback
# ---------------------------------------------------------------------------

def test_progress_source_miss_does_not_fall_back_to_internal_db(tmp_path):
    """When 大货进度表 is the selected source (cn_by_pc_lookup provided) and a
    style/colour isn't in it, the internal DB must NOT be consulted even if
    it has a matching entry -- that would silently show data from a source
    other than the one the user picked.
    """
    from po_extractor.exporters.sky_east_buyplan_export import _COLOR_NOT_FOUND

    df = pd.DataFrame([{
        "pc_no": "HHPPC048", "style": "DR5124", "brand": "Anna Field",
        "contract_no": "26302-ZA7148", "article_name": "LACE DRESS",
        "zalando_po": "PO001", "config_sku": "C1", "color_name": "dark blue",
        "xs": 30, "s": 82, "m": 0, "l": 0, "xl": 0, "xxl": 0,
    }])
    # cn_lookup/cn_code_lookup DO have a matching entry -- but must be ignored
    # because cn_by_pc_lookup (the selected source) is provided and misses.
    poisoned_cn      = {("Sky East", "Anna Field", "Dark Blue"): "藏青"}
    poisoned_cn_code = {("Sky East", "Anna Field", "Dark Blue"): "999"}
    path, _totals = export_sky_east_buyplan(
        df, cn_lookup=poisoned_cn, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup=poisoned_cn_code,
        cn_by_pc_lookup={},   # progress source selected, but empty/no match
    )
    ov = load_workbook(path)["Overview"]
    headers = [c.value for c in ov[1]]
    row = dict(zip(headers, [ov.cell(2, c + 1).value for c in range(len(headers))]))
    assert row["Color (CN)"] == _COLOR_NOT_FOUND
    assert row["Color Code"] == _COLOR_NOT_FOUND


def test_internal_db_source_miss_shows_error_not_blank(tmp_path):
    """When the internal DB is the selected source (cn_by_pc_lookup is None)
    and neither cn_lookup nor cn_code_lookup has an entry, that must show as
    an explicit error -- not silent blank/"NA" as if nothing was even tried.
    """
    from po_extractor.exporters.sky_east_buyplan_export import _COLOR_NOT_FOUND

    df = pd.DataFrame([{
        "pc_no": "HHPPC048", "style": "DR9999", "brand": "Anna Field",
        "contract_no": "C1", "article_name": "TEST",
        "zalando_po": "PO001", "config_sku": "C1", "color_name": "chartreuse",
        "xs": 10, "s": 0, "m": 0, "l": 0, "xl": 0, "xxl": 0,
    }])
    path, _totals = export_sky_east_buyplan(
        df, cn_lookup={}, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup={},
        cn_by_pc_lookup=None,   # internal DB is the selected source
    )
    ov = load_workbook(path)["Overview"]
    headers = [c.value for c in ov[1]]
    row = dict(zip(headers, [ov.cell(2, c + 1).value for c in range(len(headers))]))
    assert row["Color (CN)"] == _COLOR_NOT_FOUND
    assert row["Color Code"] == _COLOR_NOT_FOUND


def test_partial_match_still_uses_na_placeholder_not_error(tmp_path):
    """A genuine match whose colour-code field happens to be blank in the
    source row is a different situation from a full miss -- it must keep
    showing the existing "NA" placeholder, not the new error marker.
    """
    from po_extractor.lookups.progress_lookup import PCColorMatch

    df = pd.DataFrame([{
        "pc_no": "HHPPC048", "style": "DR5124", "brand": "Anna Field",
        "contract_no": "26302-ZA7148", "article_name": "LACE DRESS",
        "zalando_po": "PO001", "config_sku": "C1", "color_name": "dark blue",
        "xs": 30, "s": 82, "m": 0, "l": 0, "xl": 0, "xxl": 0,
    }])
    # Matched in 大货进度表, but its colour-code field is blank.
    cn_by_pc = {("HHPPC048", "DR5124", "Dark Blue"): PCColorMatch("藏青", "", "")}
    path, _totals = export_sky_east_buyplan(
        df, cn_lookup={}, output_dir=str(tmp_path),
        label_lookup={}, cn_code_lookup={}, cn_by_pc_lookup=cn_by_pc,
    )
    ov = load_workbook(path)["Overview"]
    headers = [c.value for c in ov[1]]
    row = dict(zip(headers, [ov.cell(2, c + 1).value for c in range(len(headers))]))
    assert row["Color (CN)"] == "藏青"
    # Overview blanks the internal "NA" sentinel -- openpyxl round-trips an
    # empty-string cell write as None on reload, which is the correct
    # "blank cell" outcome in Excel.
    assert not row["Color Code"]
