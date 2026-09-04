"""Tests for display_date / display_dates (ui/shared.py).

PO dates reach the DB in whichever shape their parser produced — the Infor
Nexus parser stores ISO, the legacy G-III parser stores US M/D/YYYY — so a PO
list shows a mix of the two unless the display normalises them.
"""
from __future__ import annotations

import datetime

import pandas as pd
import pytest

from ui.shared import display_date, display_dates


@pytest.mark.parametrize("raw,expected", [
    # Already ISO — the Infor Nexus parser's output, unchanged.
    ("2026-07-15", "2026-07-15"),
    ("2026-7-5",   "2026-07-05"),   # single-digit parts get padded
    # US M/D/YYYY — the legacy G-III parser's output.
    ("7/30/2026",  "2026-07-30"),
    ("12/5/2026",  "2026-12-05"),
    ("8/01/26",    "2026-08-01"),   # 2-digit year
])
def test_known_formats_normalise_to_iso(raw, expected):
    assert display_date(raw) == expected


@pytest.mark.parametrize("empty", [None, "", "   ", "nan", "None", "NaT"])
def test_empty_values_render_blank(empty):
    assert display_date(empty) == ""


def test_missing_pandas_values_render_blank():
    assert display_date(pd.NaT) == ""
    assert display_date(float("nan")) == ""


@pytest.mark.parametrize("obj,expected", [
    (datetime.date(2026, 7, 15), "2026-07-15"),
    (datetime.datetime(2026, 7, 15, 9, 30), "2026-07-15"),
    (pd.Timestamp("2026-07-15"), "2026-07-15"),
])
def test_date_objects_normalise(obj, expected):
    assert display_date(obj) == expected


@pytest.mark.parametrize("passthrough", [
    "2025/8/28->9/4",   # an ex-factory revision, not a date
    "TBA",
    "13/40/2026",       # not a real date — must not be invented into one
    "2026-02-30",
])
def test_unparseable_values_pass_through_untouched(passthrough):
    """Anything that is not cleanly a date is left exactly as stored.

    Guessing would be worse than showing the raw text: an ex-factory cell
    like "2025/8/28->9/4" records that a ship date MOVED, and mangling it
    into one date would destroy that.
    """
    assert display_date(passthrough) == passthrough


def test_slash_dates_are_read_month_first():
    """M/D, not D/M — the legacy parser reads US PO documents.

    Reading D/M would silently swap month and day for every day before the
    13th, which is the kind of error nobody notices until a shipment is
    planned for the wrong month.
    """
    assert display_date("3/4/2026") == "2026-03-04"


def test_display_dates_normalises_only_named_columns():
    df = pd.DataFrame([
        {"po_number": "A1", "xport_date": "7/30/2026", "note": "7/30/2026"},
        {"po_number": "A2", "xport_date": "2026-07-15", "note": "x"},
    ])
    out = display_dates(df, ("xport_date", "issue_date"))
    assert list(out["xport_date"]) == ["2026-07-30", "2026-07-15"]
    assert list(out["note"]) == ["7/30/2026", "x"]      # untouched
    assert list(df["xport_date"]) == ["7/30/2026", "2026-07-15"]  # no mutation


def test_display_dates_skips_absent_columns():
    """The PO table's column set changes with the "show all" toggle, so a
    single call has to tolerate columns that are not present."""
    df = pd.DataFrame([{"po_number": "A1"}])
    assert display_dates(df, ("xport_date", "issue_date")).equals(df)
