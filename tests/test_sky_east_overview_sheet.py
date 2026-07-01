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
