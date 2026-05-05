"""Regression tests for Sky East items → buyplan DataFrame transformation."""
import pandas as pd

from po_extractor.ui_helpers.sky_east_buyplan import (
    SE_SIZE_COLS, se_items_to_buyplan_dfs,
)


def test_empty_input_returns_empty_dfs():
    df_size, df_meta = se_items_to_buyplan_dfs(pd.DataFrame())
    assert df_size.empty
    assert df_meta.empty


def test_basic_size_explosion():
    df_items = pd.DataFrame([
        {"zalando_po": "PO1", "style": "STY1", "color_name": "Red",
         "brand": "Z", "ex_fty_date": "2026-01-01",
         "xs": 1, "s": 2, "m": 3, "l": 0, "xl": 0, "xxl": 0},
    ])
    df_size, df_meta = se_items_to_buyplan_dfs(df_items)
    # Only sizes with qty > 0 are emitted
    assert len(df_size) == 3
    assert list(df_size.columns) == ["PO Number", "Style", "Color", "Size", "Units"]
    assert set(df_size["Size"]) == {"XS", "S", "M"}
    assert df_size[df_size["Size"] == "M"]["Units"].iloc[0] == 3


def test_meta_df_has_sky_east_company():
    df_items = pd.DataFrame([
        {"zalando_po": "PO1", "style": "S1", "color_name": "Red",
         "brand": "ZBrand", "ex_fty_date": "2026-01-01",
         "xs": 1, "s": 0, "m": 0, "l": 0, "xl": 0, "xxl": 0},
    ])
    _, df_meta = se_items_to_buyplan_dfs(df_items)
    assert df_meta["company"].iloc[0] == "Sky East"
    assert df_meta["division_name"].iloc[0] == "ZBrand"
    assert df_meta["po_number"].iloc[0] == "PO1"
    assert df_meta["xport_date"].iloc[0] == "2026-01-01"


def test_meta_dedupes_by_zalando_po():
    df_items = pd.DataFrame([
        {"zalando_po": "PO1", "style": "S1", "color_name": "Red",
         "brand": "Z", "ex_fty_date": "2026-01-01",
         "xs": 1, "s": 0, "m": 0, "l": 0, "xl": 0, "xxl": 0},
        {"zalando_po": "PO1", "style": "S1", "color_name": "Blue",
         "brand": "Z", "ex_fty_date": "2026-01-01",
         "xs": 0, "s": 1, "m": 0, "l": 0, "xl": 0, "xxl": 0},
    ])
    df_size, df_meta = se_items_to_buyplan_dfs(df_items)
    assert len(df_meta) == 1, "meta should dedupe by zalando_po"
    assert len(df_size) == 2  # one row per (item × size>0)


def test_zero_qty_sizes_skipped():
    df_items = pd.DataFrame([
        {"zalando_po": "PO1", "style": "S1", "color_name": "Red",
         "brand": "Z", "ex_fty_date": "",
         "xs": 0, "s": 0, "m": 0, "l": 0, "xl": 0, "xxl": 0},
    ])
    df_size, _ = se_items_to_buyplan_dfs(df_items)
    assert df_size.empty


def test_missing_size_columns_handled_gracefully():
    df_items = pd.DataFrame([
        {"zalando_po": "PO1", "style": "S1", "color_name": "Red",
         "brand": "Z", "ex_fty_date": "",
         "m": 5},  # only "m" present
    ])
    df_size, _ = se_items_to_buyplan_dfs(df_items)
    assert len(df_size) == 1
    assert df_size["Size"].iloc[0] == "M"
    assert df_size["Units"].iloc[0] == 5


def test_se_size_cols_constant_unchanged():
    """Lock the size column ordering — downstream exporters depend on it."""
    assert SE_SIZE_COLS == [
        ("xs", "XS"), ("s", "S"), ("m", "M"),
        ("l", "L"), ("xl", "XL"), ("xxl", "XXL"),
    ]
