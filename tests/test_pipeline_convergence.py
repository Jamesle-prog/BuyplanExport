"""Tests for the GIII/Sky East pipeline structural convergence.

Phase 1 — both pipelines go through the same front door: config format id,
universal file detection, and the parsers facade.
"""
from __future__ import annotations

import openpyxl
import pytest


# ── Phase 1: facade ──────────────────────────────────────────────────────────

def test_facade_exports_canonical_sky_east_parser():
    from po_extractor.parsers import parse_sky_east_order
    from po_extractor.parsers.sky_east_order import parse
    assert callable(parse_sky_east_order)
    # Facade delegates to the canonical (dynamic-layout) parser module.
    assert parse_sky_east_order.__module__ == "po_extractor.parsers"
    assert callable(parse)


def test_legacy_sky_east_parser_no_longer_exported():
    import po_extractor.parsers as parsers
    assert "parse_sky_east" not in parsers.__all__
    assert not hasattr(parsers, "parse_sky_east")


def test_format_sky_east_constant_exists():
    from po_extractor.config import FORMAT_SKY_EAST
    assert FORMAT_SKY_EAST == "sky_east"


# ── Phase 1: detection ───────────────────────────────────────────────────────

def _make_sky_east_xlsx(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contract"
    ws["A1"] = "SKY EAST INTERNATIONAL TRADING LIMITED"
    ws["A3"] = "PURCHASE CONTRACT"
    ws["A4"] = "PC NO."
    ws["B4"] = "HHPPC038"
    wb.save(path)


def _make_plain_xlsx(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "just some spreadsheet"
    wb.save(path)


def test_detect_file_recognises_sky_east_contract(tmp_path):
    from po_extractor.detectors import detect_file
    p = tmp_path / "se_contract.xlsx"
    _make_sky_east_xlsx(str(p))
    result = detect_file(str(p))
    assert result.format_id == "sky_east"
    assert result.file_type == "excel"
    assert result.confidence == "high"
    assert "Sky East" in result.companies


def test_detect_file_plain_excel_still_unknown(tmp_path):
    from po_extractor.detectors import detect_file
    p = tmp_path / "plain.xlsx"
    _make_plain_xlsx(str(p))
    result = detect_file(str(p))
    assert result.format_id == "excel_unknown"


def test_looks_like_sky_east_contract_readonly_mode(tmp_path):
    """The signature helper must work on read-only workbooks (detector mode)."""
    from po_extractor.parsers.sky_east_order import looks_like_sky_east_contract
    p = tmp_path / "se.xlsx"
    _make_sky_east_xlsx(str(p))
    wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
    try:
        assert looks_like_sky_east_contract(wb) is True
    finally:
        wb.close()

    p2 = tmp_path / "plain.xlsx"
    _make_plain_xlsx(str(p2))
    wb2 = openpyxl.load_workbook(str(p2), read_only=True, data_only=True)
    try:
        assert looks_like_sky_east_contract(wb2) is False
    finally:
        wb2.close()


def test_facade_parses_sky_east_end_to_end(tmp_path):
    """detect → facade parse, the same flow GIII PDFs get via parse_pdf."""
    from po_extractor.detectors import detect_file
    from po_extractor.parsers import parse_sky_east_order
    p = tmp_path / "se_contract.xlsx"
    _make_sky_east_xlsx(str(p))
    assert detect_file(str(p)).format_id == "sky_east"
    contract = parse_sky_east_order(str(p), processed_by="test")
    # Minimal fixture: header-only contract parses without raising and
    # carries traceability fields.
    assert contract.processed_by == "test"
    assert contract.source_file_hash
