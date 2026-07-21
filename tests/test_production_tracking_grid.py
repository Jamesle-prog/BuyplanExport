"""Tests for the one-page Tracking Grid helpers (v2.89.0).

The grid replaced the 22-stage Dashboard/Overview/Edit surface as the daily
view: rows = tracked PO/styles, columns = the 9 MILESTONE_STAGES (the same
milestone block the Sky East buy plan's Index tab prints). ``_grid_dataframe``
and ``_grid_diff`` are pure (no Streamlit) precisely so this contract is
testable — the Index feed depends on the diff writing ``{stage}_planned``.
"""
from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.production_tracking_view as v
from po_extractor.store._factory_progress_schema import MILESTONE_STAGES


def _record(**over) -> dict:
    r = {"po_number": "PO1", "style": "STY1", "factory": "F1"}
    for stage, _ in MILESTONE_STAGES:
        r[f"{stage}_planned"] = ""
        r[f"{stage}_actual"] = ""
        r[f"{stage}_status"] = "Not Started"
    r.update(over)
    return r


# ── _grid_dataframe ─────────────────────────────────────────────────────────

def test_grid_columns_match_milestone_stages_in_order():
    df = v._grid_dataframe([_record()], v.GRID_PLANNED)
    expected = (["PO Number", "Style", "Factory"]
                + [lbl for _, lbl in MILESTONE_STAGES] + ["Done"])
    assert list(df.columns) == expected


def test_grid_binds_to_the_selected_mode():
    rec = _record(cutting_planned="2026-08-01", cutting_actual="2026-08-05")
    label = dict(MILESTONE_STAGES)["cutting"]

    planned = v._grid_dataframe([rec], v.GRID_PLANNED)
    actual  = v._grid_dataframe([rec], v.GRID_ACTUAL)
    assert v._date_str(planned.iloc[0][label]) == "2026-08-01"
    assert v._date_str(actual.iloc[0][label]) == "2026-08-05"


def test_done_count_counts_actual_dates_only():
    rec = _record(cutting_actual="2026-08-05", sewing_planned="2026-08-09")
    df = v._grid_dataframe([rec], v.GRID_PLANNED)
    assert df.iloc[0]["Done"] == f"1/{len(MILESTONE_STAGES)}"


# ── _status_strip_df ────────────────────────────────────────────────────────

def test_status_strip_marks_done_planned_and_empty():
    rec = _record(cutting_actual="2026-08-05", sewing_planned="2026-08-09")
    row = v._status_strip_df([rec]).iloc[0]
    labels = dict(MILESTONE_STAGES)
    assert row[labels["cutting"]] == "✅"
    assert row[labels["sewing"]] == "📅"
    assert row[labels["packing"]] == "⬜"


# ── _grid_diff ──────────────────────────────────────────────────────────────

def test_diff_emits_only_changed_cells():
    rec = _record()
    original = v._grid_dataframe([rec], v.GRID_PLANNED)
    edited = original.copy()
    label = dict(MILESTONE_STAGES)["fabric_purchase"]
    edited.loc[0, label] = pd.Timestamp("2026-08-01")

    diff = v._grid_diff(original, edited, v.GRID_PLANNED, [rec])
    assert diff == {("PO1", "STY1"): {"fabric_purchase_planned": "2026-08-01"}}


def test_diff_is_empty_when_nothing_edited():
    rec = _record(cutting_planned="2026-08-01")
    original = v._grid_dataframe([rec], v.GRID_PLANNED)
    assert v._grid_diff(original, original.copy(), v.GRID_PLANNED, [rec]) == {}


def test_actual_mode_marks_stage_done():
    rec = _record()
    original = v._grid_dataframe([rec], v.GRID_ACTUAL)
    edited = original.copy()
    edited.loc[0, dict(MILESTONE_STAGES)["cutting"]] = pd.Timestamp("2026-08-05")

    fields = v._grid_diff(original, edited, v.GRID_ACTUAL, [rec])[("PO1", "STY1")]
    assert fields["cutting_actual"] == "2026-08-05"
    assert fields["cutting_status"] == "Done"


def test_clearing_actual_downgrades_a_done_stage():
    """Status must never claim Done with no completion date."""
    rec = _record(cutting_actual="2026-08-05", cutting_status="Done")
    original = v._grid_dataframe([rec], v.GRID_ACTUAL)
    edited = original.copy()
    edited.loc[0, dict(MILESTONE_STAGES)["cutting"]] = None

    fields = v._grid_diff(original, edited, v.GRID_ACTUAL, [rec])[("PO1", "STY1")]
    assert fields["cutting_actual"] == ""
    assert fields["cutting_status"] == "In Progress"


def test_planned_mode_never_touches_status():
    rec = _record(cutting_status="Done", cutting_actual="2026-08-05")
    original = v._grid_dataframe([rec], v.GRID_PLANNED)
    edited = original.copy()
    edited.loc[0, dict(MILESTONE_STAGES)["cutting"]] = pd.Timestamp("2026-09-01")

    fields = v._grid_diff(original, edited, v.GRID_PLANNED, [rec])[("PO1", "STY1")]
    assert fields == {"cutting_planned": "2026-09-01"}   # no _status key


def test_diff_writes_the_columns_the_buy_plan_index_reads():
    """Regression guard for the Index feed: the grid must write exactly the
    `{stage}_planned` columns _INDEX_MILESTONE_MAP consumes."""
    from po_extractor.exporters.sky_east_buyplan_export import _INDEX_MILESTONE_MAP
    index_stages = {src for src, kind in _INDEX_MILESTONE_MAP.values()
                    if kind == "stage"}
    grid_stages = {s for s, _ in MILESTONE_STAGES}
    assert index_stages == grid_stages


def test_date_str_normalises_every_cell_shape():
    import datetime as _dt
    assert v._date_str(None) == ""
    assert v._date_str("") == ""
    assert v._date_str("2026-08-01") == "2026-08-01"
    assert v._date_str(_dt.date(2026, 8, 1)) == "2026-08-01"
    assert v._date_str(pd.Timestamp("2026-08-01")) == "2026-08-01"
    assert v._date_str(pd.NaT) == ""
