"""Tests for price masking — PDF token pattern + Excel column masking."""
from __future__ import annotations

import openpyxl
import pytest

from po_extractor.utils.price_mask import _PRICE_RE, mask_prices_excel


# ── PDF token pattern ────────────────────────────────────────────────────────

@pytest.mark.parametrize("token", [
    "4.17", "69.00", "1234.00",
    "1,234.00", "12,345.67",          # thousands separators (was missed before)
    "$4.17", "€1,000.00", "£99.99", "¥50.00",   # currency prefixes
])
def test_price_regex_matches_prices(token):
    assert _PRICE_RE.match(token), f"{token!r} should be treated as a price"


@pytest.mark.parametrize("token", [
    "69",          # bare integer — quantity/PO#, must NOT mask
    "123456789012",  # UPC
    "2026",        # year
    "4.1", "4.175",  # not two decimals
    "abc", "", ".00",   # non-numeric / no leading digit
])
def test_price_regex_rejects_non_prices(token):
    assert not _PRICE_RE.match(token), f"{token!r} should NOT be masked"


# ── Excel column masking ─────────────────────────────────────────────────────

def _build_xlsx(tmp_path, rows):
    p = tmp_path / "in.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(p)
    return str(p)


def _read_masked(out_path):
    wb = openpyxl.load_workbook(out_path)
    ws = wb.active
    return [[c.value for c in row] for row in ws.iter_rows()]


def test_excel_masks_keyword_columns_and_keeps_others(tmp_path):
    src = _build_xlsx(tmp_path, [
        ["Style", "Qty", "FOB Price", "MSRP", "Line Total ($)"],
        ["ST1",   100,   4.17,        "$69.00", "1,234.00"],
        ["ST2",   50,    3.75,        59.00,    617.00],
    ])
    out = mask_prices_excel(src, str(tmp_path))
    rows = _read_masked(out)

    # Header row untouched
    assert rows[0] == ["Style", "Qty", "FOB Price", "MSRP", "Line Total ($)"]
    # Style + Qty preserved (Qty has no price keyword)
    assert rows[1][0] == "ST1" and rows[1][1] == 100
    assert rows[2][0] == "ST2" and rows[2][1] == 50
    # FOB Price (float), MSRP (currency string + float), Line Total ($ header) masked
    for r in (1, 2):
        assert rows[r][2] == "***"   # FOB Price
        assert rows[r][3] == "***"   # MSRP  (was "$69.00" and 59.00)
        assert rows[r][4] == "***"   # Line Total ($)


def test_excel_leaves_text_cells_in_price_columns(tmp_path):
    # A "Retail" column matches a keyword but holds text — must stay.
    src = _build_xlsx(tmp_path, [
        ["Retail Partner", "Unit Price"],
        ["Macy's",         12.50],
    ])
    out = mask_prices_excel(src, str(tmp_path))
    rows = _read_masked(out)
    assert rows[1][0] == "Macy's"   # text preserved despite "retail" keyword
    assert rows[1][1] == "***"      # numeric price masked


def test_excel_no_price_columns_is_noop(tmp_path):
    src = _build_xlsx(tmp_path, [["Style", "Color", "Qty"], ["ST1", "BLACK", 100]])
    out = mask_prices_excel(src, str(tmp_path))
    rows = _read_masked(out)
    assert rows[1] == ["ST1", "BLACK", 100]


def test_excel_rejects_legacy_xls(tmp_path):
    p = tmp_path / "old.xls"
    p.write_bytes(b"not a real xls")
    with pytest.raises(ValueError, match="legacy .xls"):
        mask_prices_excel(str(p), str(tmp_path))
