"""Pins every flag combination of po_extractor/utils/normalize.py to the
semantics of the per-module private copies it replaced (v2.125.1)."""
from datetime import date, datetime

import pytest

from po_extractor.utils.normalize import (
    cell_date_text, cell_text, dispimg_id, norm_header_key, normalize_header,
    normalize_key, normalize_text, to_float, to_int, yes_no,
)


# ── keys / headers ──────────────────────────────────────────────────────────

def test_normalize_header_folds_fullwidth_and_collapses_ws():
    assert normalize_header("  克重（GSM）\n Weight ") == "克重(gsm) weight"
    assert normalize_header(None) == ""


def test_normalize_text_is_literal_on_punctuation():
    assert normalize_text("  Style   No.\n") == "style no."
    assert normalize_text("（A）") == "（a）"   # no bracket folding
    assert normalize_text(None) == ""


def test_norm_header_key_removes_all_ws_and_folds_brackets():
    assert norm_header_key("发票金额\n(报关金额）") == "发票金额(报关金额)"
    assert norm_header_key(" Unit  Price ") == "unitprice"
    assert norm_header_key(None) == ""


def test_normalize_key_alnum_upper():
    assert normalize_key(" s24-ddr_010 ") == "S24DDR010"
    assert normalize_key(12345) == "12345"


# ── cell text ───────────────────────────────────────────────────────────────

def test_cell_text_defaults_match_plain_str_strip():
    assert cell_text(None) == ""
    assert cell_text("  x ") == "x"
    assert cell_text(3.0) == "3.0"                      # no int_floats
    assert cell_text("nan") == "nan"                    # no drop_nan
    assert cell_text("#N/A") == "#N/A"                  # no drop_excel_errors


def test_cell_text_dates_flag():
    assert cell_text(datetime(2026, 8, 1, 10, 5), dates=True) == "2026-08-01"
    assert cell_text(date(2026, 8, 1), dates=True) == "2026-08-01"
    assert cell_text(datetime(2026, 8, 1), dates=False).startswith("2026-08-01 ")


def test_cell_text_int_floats_flag():
    assert cell_text(12.0, int_floats=True) == "12"
    assert cell_text(12.5, int_floats=True) == "12.5"
    assert cell_text(12, int_floats=True) == "12"


def test_cell_text_drop_flags():
    assert cell_text("NaN", drop_nan=True) == ""
    assert cell_text("None", drop_nan=True) == ""
    assert cell_text("#n/a", drop_excel_errors=True) == ""
    assert cell_text("#REF!", drop_excel_errors=True) == ""
    assert cell_text("#Other", drop_excel_errors=True) == "#Other"


def test_cell_date_text():
    assert cell_date_text(None) == ""
    assert cell_date_text("") == ""
    assert cell_date_text(datetime(2026, 8, 1, 9)) == "2026-08-01"
    assert cell_date_text(date(2026, 8, 1)) == "2026-08-01"
    assert cell_date_text(" 2026-08-01 ") == "2026-08-01"


def test_dispimg_id():
    assert dispimg_id('=DISPIMG("ID_ABC123",1)') == "ID_ABC123"
    assert dispimg_id("plain") == ""
    assert dispimg_id(None) == ""


# ── numbers ─────────────────────────────────────────────────────────────────

def test_to_float_defaults():
    assert to_float(None) is None
    assert to_float(None, default=0.0) == 0.0
    assert to_float(3) == 3.0
    assert to_float("1,234.5") == 1234.5          # commas on by default
    assert to_float("1,234.5", commas=False) is None
    assert to_float("abc") is None
    assert to_float("") is None
    assert to_float(True) is None                  # bools off by default
    assert to_float(True, bools=True) == 1.0


def test_to_float_currency_and_percent():
    assert to_float("$1,200") == 1200.0 or to_float("$1,200") is None  # no strip → None
    assert to_float("$1,200") is None
    assert to_float("¥ 1,200", strip_currency=True) == 1200.0
    assert to_float("3.25%") is None
    assert to_float("3.25%", percent="ratio") == pytest.approx(0.0325)
    assert to_float("3.25%", percent="strip") == pytest.approx(3.25)
    assert to_float("-", none_tokens=("nan", "none", "-")) is None
    assert to_float("NaN", none_tokens=("nan",), default=0.0) == 0.0


def test_to_int_rounding_modes():
    assert to_int("12.7") == 13
    assert to_int("12.7", rounding="trunc") == 12
    assert to_int("1,234", default=0) == 1234
    assert to_int("x", default=0) == 0
    assert to_int(None) is None
    assert to_int("¥12.9", default=0, strip_currency=True, rounding="trunc") == 12


def test_to_int_strict():
    assert to_int(7, strict=True) == 7
    assert to_int(7.0, strict=True) == 7
    assert to_int("42", strict=True) == 42
    assert to_int("12.5", strict=True) is None
    assert to_int("-3", strict=True) is None
    assert to_int(True, strict=True) is None
    assert to_int(None, strict=True, default=0) == 0


def test_yes_no():
    assert yes_no(None) == ""
    assert yes_no(1) == "Y"
    assert yes_no(0) == "N"
    assert yes_no("") == "N"
