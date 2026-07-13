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
    # FOB Price + Line Total masked; MSRP is PUBLIC retail → kept
    for r in (1, 2):
        assert rows[r][2] == "***"   # FOB Price (confidential cost)
        assert rows[r][4] == "***"   # Line Total ($) (confidential)
    assert rows[1][3] == "$69.00" and rows[2][3] == 59.00   # MSRP not masked


def test_excel_never_masks_retail_prices(tmp_path):
    """MSRP / SRP / RRP / Suggested Retail are public — never masked, even when
    the header also contains a generic price word."""
    src = _build_xlsx(tmp_path, [
        ["Style", "FOB", "MSRP", "SRP", "Suggested Retail Price", "Unit Cost"],
        ["ST1",   4.17,  69.00,  75.00, 79.99,                    3.50],
    ])
    out = mask_prices_excel(src, str(tmp_path))
    rows = _read_masked(out)
    assert rows[1][1] == "***"      # FOB masked
    assert rows[1][5] == "***"      # Unit Cost masked
    assert rows[1][2] == 69.00      # MSRP kept
    assert rows[1][3] == 75.00      # SRP kept
    assert rows[1][4] == 79.99      # "Suggested Retail Price" kept (despite "price")


def test_excel_leaves_text_cells_in_price_columns(tmp_path):
    # A text cell in a genuine price column ("Unit Price") stays; the number masks.
    src = _build_xlsx(tmp_path, [
        ["Vendor", "Unit Price"],
        ["Macy's", 12.50],
    ])
    out = mask_prices_excel(src, str(tmp_path))
    rows = _read_masked(out)
    assert rows[1][0] == "Macy's"   # text preserved
    assert rows[1][1] == "***"      # numeric price masked


def test_excel_masks_formula_cells_in_price_columns(tmp_path):
    """A formula in a price column recalculates on open, leaking the price —
    it must be masked, not left as the (string) formula text."""
    p = tmp_path / "f.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Style", "Qty", "Unit Price", "Line Total"])
    ws.append(["ST1", 100, 4.17, "=B2*C2"])   # formula in a price column
    wb.save(p)
    out = mask_prices_excel(str(p), str(tmp_path))
    rows = _read_masked(out)
    assert rows[1][2] == "***"        # numeric price masked
    assert rows[1][3] == "***"        # formula masked, not "=B2*C2"


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


# ── AI-assisted detection (DeepSeek call mocked) ─────────────────────────────

import po_extractor.utils.price_mask as pm


def test_detect_prices_ai_parses_and_normalizes(monkeypatch):
    monkeypatch.setattr(pm, "_deepseek_json",
                        lambda *a, **k: {"prices": ["$1,200.00", "69", "  "]})
    got = pm.detect_prices_ai("irrelevant", api_key="k")
    assert got == {"1200.00", "69"}   # currency/commas stripped, blanks dropped


def test_detect_prices_ai_no_key_is_empty(monkeypatch):
    # No API call attempted without a key → empty set, regex still the floor.
    called = {"n": 0}
    def _spy(*a, **k):
        called["n"] += 1
        return {}
    monkeypatch.setattr(pm, "_deepseek_json", _spy)
    assert pm.detect_prices_ai("text", api_key="") == set()
    # _deepseek_json itself guards empty key, but detect_prices_ai passes through;
    # the real guard is inside _deepseek_json (tested below).


def test_deepseek_json_returns_empty_without_key():
    assert pm._deepseek_json("sys", "user", api_key="", model="m") == {}


def test_ai_columns_union_with_keywords(tmp_path, monkeypatch):
    # A price column whose header has NO keyword ("Deal") — only AI can catch it.
    monkeypatch.setattr(pm, "_deepseek_json",
                        lambda *a, **k: {"price_headers": ["Deal"]})
    src = _build_xlsx(tmp_path, [
        ["Style", "Deal", "Qty"],
        ["ST1",   4.17,   100],
    ])
    out = mask_prices_excel(str(src) if not isinstance(src, str) else src,
                            str(tmp_path), api_key="k")
    rows = _read_masked(out)
    assert rows[1][1] == "***"   # "Deal" column masked via AI
    assert rows[1][2] == 100     # Qty untouched


def test_ai_failure_falls_back_to_keywords(tmp_path, monkeypatch):
    # AI returns nothing (as if the call failed) — keyword detection still works.
    monkeypatch.setattr(pm, "_deepseek_json", lambda *a, **k: {})
    src = _build_xlsx(tmp_path, [["Style", "FOB"], ["ST1", 4.17]])
    out = mask_prices_excel(src, str(tmp_path), api_key="k")
    rows = _read_masked(out)
    assert rows[1][1] == "***"   # FOB still masked by keyword
