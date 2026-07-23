"""Buyer DSP file → dspTrims[] parser + per-context routing."""
from __future__ import annotations

import io

import openpyxl
import pytest

from po_extractor.parsers.dsp_trims import parse_dsp_trims, trims_for_request


def _xlsx(rows, sheet="DSP", prefix_rows=0):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for _ in range(prefix_rows):
        ws.append(["some title banner"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_HDR = ["Style No", "Material Name", "Material Code", "Supplier",
        "Placement", "Qty/PC", "Colour", "PO"]


def test_parses_english_headers_and_rows():
    content = _xlsx([
        _HDR,
        ["DU5105", "Woven label", "LAB04472", "Trimco", "Neck", 1, "Black", ""],
        ["DU5105", "Hang tag", "HT-9", "Trimco", "Waist", 2, "", "A1, A2"],
    ])
    out = parse_dsp_trims(content)
    assert out["issues"] == []
    assert len(out["trims"]) == 2
    t0, t1 = out["trims"]
    assert t0 == {"style": "DU5105", "materialName": "Woven label",
                  "materialCode": "LAB04472", "supplier": "Trimco",
                  "placement": "Neck", "qtyPerPc": 1.0, "color": "Black"}
    assert t1["appliesToOrders"] == ["A1", "A2"]


def test_parses_chinese_headers_and_title_banner():
    content = _xlsx([
        ["款号", "辅料名称", "料号", "供应商", "部位", "单件用量", "颜色"],
        ["DU9", "织唛", "ZM-1", "华艺", "后领", "0.5", "黑"],
    ], prefix_rows=3)
    out = parse_dsp_trims(content)
    assert len(out["trims"]) == 1
    tr = out["trims"][0]
    assert tr["materialName"] == "织唛" and tr["qtyPerPc"] == 0.5
    assert tr["style"] == "DU9"


def test_blank_qty_becomes_zero_for_api_tp_rendering():
    content = _xlsx([_HDR, ["DU1", "Button", "", "", "", "", "", ""]])
    out = parse_dsp_trims(content)
    assert out["trims"][0]["qtyPerPc"] == 0        # API renders 按TP


def test_bad_qty_reported_and_sent_as_zero():
    content = _xlsx([_HDR, ["DU1", "Button", "", "", "", "two", "", ""]])
    out = parse_dsp_trims(content)
    assert out["trims"][0]["qtyPerPc"] == 0
    assert any("not a number" in i for i in out["issues"])


def test_row_without_material_name_is_reported():
    content = _xlsx([_HDR, ["DU1", "", "X", "", "", 1, "", ""]])
    out = parse_dsp_trims(content)
    assert out["trims"] == []
    assert any("no material name" in i for i in out["issues"])


def test_unreadable_file_raises_valueerror():
    with pytest.raises(ValueError):
        parse_dsp_trims(b"not a workbook")


def test_no_recognisable_header_raises():
    content = _xlsx([["just", "random", "cells"], ["a", "b", "c"]])
    with pytest.raises(ValueError):
        parse_dsp_trims(content)


# ── PDF path (pure core — pdfplumber page structures) ───────────────────────

from po_extractor.parsers.dsp_trims import trims_from_pdf_pages  # noqa: E402


def test_pdf_table_with_headers():
    pages = [{
        "text": "DSP PACKAGE\nSTYLE: DU5105\nSeason FA26",
        "tables": [[
            ["Material Name", "Material Code", "Supplier", "Qty/PC"],
            ["Woven label", "LAB04472", "Trimco", "1"],
            ["Hang tag", "HT-9", "Trimco", "2"],
        ]],
    }]
    out = trims_from_pdf_pages(pages)
    assert len(out["trims"]) == 2
    # No style column → the style stated in the page text applies.
    assert all(tr["style"] == "DU5105" for tr in out["trims"])
    assert out["trims"][0]["materialCode"] == "LAB04472"


def test_pdf_continuation_page_reuses_columns():
    header = ["Material Name", "Qty/PC"]
    pages = [
        {"text": "STYLE: DU1", "tables": [[header, ["Label", "1"]]]},
        # Page 2: table WITHOUT its own header row — continuation.
        {"text": "STYLE: DU1", "tables": [[["Zipper", "2"]]]},
    ]
    out = trims_from_pdf_pages(pages)
    assert [t["materialName"] for t in out["trims"]] == ["Label", "Zipper"]


def test_pdf_repeated_header_row_is_skipped():
    header = ["Material Name", "Qty/PC"]
    pages = [{"text": "", "tables": [[header, ["Button", "4"],
                                      header, ["Thread", "0.1"]]]}]
    out = trims_from_pdf_pages(pages)
    assert [t["materialName"] for t in out["trims"]] == ["Button", "Thread"]


def test_pdf_style_column_beats_page_style():
    pages = [{
        "text": "STYLE: PAGEONLY",
        "tables": [[
            ["Style", "Material Name", "Qty/PC"],
            ["DU7", "Snap", "6"],
            ["", "Care label", "1"],       # blank cell falls back to page style
        ]],
    }]
    out = trims_from_pdf_pages(pages)
    assert out["trims"][0]["style"] == "DU7"
    assert out["trims"][1]["style"] == "PAGEONLY"


def test_pdf_without_any_table_raises():
    with pytest.raises(ValueError):
        trims_from_pdf_pages([{"text": "cover page only", "tables": []}])


def test_pdf_magic_bytes_dispatch():
    """A %PDF payload must route to the PDF parser (which then rejects this
    junk PDF cleanly), never to openpyxl."""
    with pytest.raises(ValueError):
        parse_dsp_trims(b"%PDF-1.7 not really a pdf")


# ── routing to order contexts ───────────────────────────────────────────────

_RQ = {"label": "DKNY", "raw": {},
       "pos": [{"order": "A1", "style": "DU5105"},
               {"order": "A2", "style": "DU9"}]}


def test_routing_by_style():
    trims = [{"style": "DU5105", "materialName": "Label", "qtyPerPc": 1},
             {"style": "ZZ999", "materialName": "Other", "qtyPerPc": 1}]
    routed = trims_for_request(trims, _RQ)
    assert [t["materialName"] for t in routed] == ["Label"]


def test_explicit_orders_override_style_match():
    trims = [{"style": "ZZ999", "materialName": "Tag", "qtyPerPc": 1,
              "appliesToOrders": ["A2"]}]
    assert trims_for_request(trims, _RQ) == trims       # order matches


def test_contextless_trim_matches_everywhere():
    trims = [{"style": "", "materialName": "Polybag", "qtyPerPc": 1}]
    assert trims_for_request(trims, _RQ) == trims
