"""Regression tests for CN color enrichment."""
import pandas as pd

from po_extractor.ui_helpers.color_enrichment import enrich_cn_color


def _size(po, color):
    return pd.DataFrame([{"PO Number": po, "Color": color, "Size": "M", "Units": 1}])


def _meta(po, company, brand):
    return pd.DataFrame([{"po_number": po, "company": company, "division_name": brand}])


def test_empty_lookup_yields_blank_column():
    df = enrich_cn_color(_size("PO1", "Red"), _meta("PO1", "G3", "DKNY"), {})
    assert "Color (CN)" in df.columns
    assert df["Color (CN)"].iloc[0] == ""


def test_brand_specific_lookup_hits_first():
    lookup = {("G3", "DKNY", "Red"): "红色-DKNY", ("G3", "", "Red"): "红色"}
    df = enrich_cn_color(_size("PO1", "Red"), _meta("PO1", "G3", "DKNY"), lookup)
    assert df["Color (CN)"].iloc[0] == "红色-DKNY"


def test_falls_back_to_brandless_when_no_brand_match():
    lookup = {("G3", "", "Red"): "红色"}
    df = enrich_cn_color(_size("PO1", "Red"), _meta("PO1", "G3", "DKNY"), lookup)
    assert df["Color (CN)"].iloc[0] == "红色"


def test_no_match_yields_empty_string():
    lookup = {("G3", "", "Blue"): "蓝色"}
    df = enrich_cn_color(_size("PO1", "Red"), _meta("PO1", "G3", "DKNY"), lookup)
    assert df["Color (CN)"].iloc[0] == ""


def test_missing_meta_for_po_yields_empty():
    lookup = {("G3", "", "Red"): "红色"}
    # df_meta has different PO; lookup miss expected
    df = enrich_cn_color(_size("PO1", "Red"), _meta("PO_OTHER", "G3", ""), lookup)
    assert df["Color (CN)"].iloc[0] == ""


def test_input_df_is_not_mutated():
    df_in = _size("PO1", "Red")
    cols_before = list(df_in.columns)
    enrich_cn_color(df_in, _meta("PO1", "G3", ""), {("G3", "", "Red"): "红"})
    assert list(df_in.columns) == cols_before


def test_color_whitespace_stripped_from_meta():
    """Brand/client whitespace in meta should be trimmed."""
    lookup = {("G3", "DKNY", "Red"): "红"}
    meta = pd.DataFrame([{"po_number": "PO1", "company": "  G3  ",
                          "division_name": "  DKNY  "}])
    df = enrich_cn_color(_size("PO1", "Red"), meta, lookup)
    assert df["Color (CN)"].iloc[0] == "红"


def test_empty_meta_handled():
    df = enrich_cn_color(_size("PO1", "Red"), pd.DataFrame(), {("", "", "Red"): "红"})
    assert df["Color (CN)"].iloc[0] == "红"
