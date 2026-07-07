"""Tests for the standardized cross-client PO summary adapters."""
from __future__ import annotations

import pandas as pd

from po_extractor.ui_helpers.combined_summary import (
    STANDARD_KEYS,
    STANDARD_LABELS,
    build_contract_maps,
    combine_standard,
    giii_pos_to_standard,
    sky_east_items_to_standard,
)


def _giii_df() -> pd.DataFrame:
    return pd.DataFrame([{
        "po_number": "PO123", "company": "GIII", "style": "ST1",
        "customer": "Macy's", "factory": "F1", "country_of_origin": "CN",
        "issue_date": "2026-01-02", "xport_date": "2026-03-04",
        "total_units": 100, "unit_cost": "$5.00",
        "line_extended_cost": "$500.00", "season": "S26",
        "source_format": "infor_nexus",
    }])


def _se_df() -> pd.DataFrame:
    return pd.DataFrame([{
        "pc_no": "PC001", "zalando_po": "PO2276067C", "style": "S25DDR2036",
        "color_name": "Blue", "brand": "Anna Field",
        "ex_fty_date": "2026-05-01", "total_qty": 700,
        "fob_usd": 6.5, "total_cost_usd": 4550.0,
    }])


def test_every_standard_key_has_a_label():
    for k in STANDARD_KEYS:
        assert k in STANDARD_LABELS


def test_giii_maps_to_standard_shape():
    out = giii_pos_to_standard(_giii_df())
    assert list(out.columns) == STANDARD_KEYS
    row = out.iloc[0]
    assert row["po_number"] == "PO123"
    assert row["contract_no"] == ""             # no progress data → blank, not PO
    assert row["color"] == ""                   # not at PO grain
    assert row["brand_customer"] == "Macy's"
    assert row["order_date"] == "2026-01-02"
    assert row["ex_fty_date"] == "2026-03-04"
    assert row["units"] == 100
    assert row["source"] == "infor_nexus"


def test_giii_contract_no_resolved_from_progress_by_po():
    """GIII contract numbers come from the HHN 大货进度表 progress records,
    matched on the sheet's PO# column (stored under the 'zalando_po' key)."""
    by_po, by_style = build_contract_maps([
        {"contract_no": "HHN-2026-001", "zalando_po": "po 123", "style": "OTHER"},
    ])
    out = giii_pos_to_standard(_giii_df(), contract_by_po=by_po, contract_by_style=by_style)
    # "po 123" normalizes to PO123 — matches despite casing/whitespace
    assert out.iloc[0]["contract_no"] == "HHN-2026-001"


def test_giii_contract_no_falls_back_to_style_match():
    by_po, by_style = build_contract_maps([
        {"contract_no": "HHN-2026-002", "zalando_po": "", "style": "st1"},
    ])
    out = giii_pos_to_standard(_giii_df(), contract_by_po=by_po, contract_by_style=by_style)
    assert out.iloc[0]["contract_no"] == "HHN-2026-002"


def test_build_contract_maps_first_contract_wins_and_blanks_skipped():
    by_po, by_style = build_contract_maps([
        {"contract_no": "",     "zalando_po": "PO9", "style": "S9"},   # blank contract skipped
        {"contract_no": "C-1",  "zalando_po": "PO9", "style": "S9"},
        {"contract_no": "C-2",  "zalando_po": "PO9", "style": "S9"},  # later duplicate ignored
    ])
    assert by_po == {"PO9": "C-1"}
    assert by_style == {"S9": "C-1"}


def test_sky_east_maps_to_standard_shape():
    out = sky_east_items_to_standard(_se_df(), pc_dates={"PC001": "2026-02-10"})
    assert list(out.columns) == STANDARD_KEYS
    row = out.iloc[0]
    assert row["po_number"] == "PO2276067C"
    assert row["contract_no"] == "PC001"
    assert row["color"] == "Blue"
    assert row["brand_customer"] == "Anna Field"
    assert row["order_date"] == "2026-02-10"    # from contract pc_date
    assert row["factory"] == ""                 # SE has no factory field
    assert row["units"] == 700
    assert row["unit_price"] == 6.5
    assert row["source"] == "sky_east"


def test_sky_east_without_pc_dates_leaves_order_date_blank():
    out = sky_east_items_to_standard(_se_df())
    assert out.iloc[0]["order_date"] == ""


def test_combine_keeps_header_identical_and_stacks_rows():
    combined = combine_standard(
        giii_pos_to_standard(_giii_df()),
        sky_east_items_to_standard(_se_df()),
    )
    assert list(combined.columns) == STANDARD_KEYS
    assert len(combined) == 2
    assert set(combined["source"]) == {"infor_nexus", "sky_east"}


def test_combine_of_nothing_returns_empty_with_standard_header():
    combined = combine_standard(pd.DataFrame(), None)
    assert list(combined.columns) == STANDARD_KEYS
    assert combined.empty


def test_empty_inputs_produce_standard_header():
    assert list(giii_pos_to_standard(pd.DataFrame()).columns) == STANDARD_KEYS
    assert list(sky_east_items_to_standard(None).columns) == STANDARD_KEYS


def test_missing_columns_dont_crash():
    # A store variant missing optional columns still maps cleanly.
    out = giii_pos_to_standard(pd.DataFrame([{"po_number": "X", "total_units": 5}]))
    assert out.iloc[0]["season"] == ""
    assert out.iloc[0]["units"] == 5
