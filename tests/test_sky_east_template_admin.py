"""Tests for the Sky East template-management API exposed for the Admin UI."""
from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from po_extractor.exporters.sky_east_buyplan_export import (
    SE_TEMPLATE_CATALOG, list_sky_east_templates,
    read_sky_east_config_text, read_sky_east_template,
    replace_sky_east_template, write_sky_east_config_text,
)


def _make_xlsx_bytes(sheet_value: str = "hello") -> bytes:
    """Build a minimal valid xlsx in memory."""
    wb = Workbook()
    wb.active["A1"] = sheet_value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Catalog & listing
# ---------------------------------------------------------------------------

def test_catalog_has_main_and_nukuryou():
    assert set(SE_TEMPLATE_CATALOG.keys()) == {"main", "nukuryou"}


def test_list_returns_one_entry_per_catalog_kind():
    rows = list_sky_east_templates()
    kinds = {r["kind"] for r in rows}
    assert kinds == {"main", "nukuryou"}
    for r in rows:
        # Each entry has the metadata keys the Admin UI relies on.
        for key in ("kind", "label", "file", "path", "exists", "size_bytes", "modified"):
            assert key in r


# ---------------------------------------------------------------------------
# Replace round-trip with backup/restore so we don't trash the real templates
# ---------------------------------------------------------------------------

@pytest.fixture
def _backup_main_template():
    """Snapshot the main Sky East template, restore after the test."""
    try:
        original = read_sky_east_template("main")
    except FileNotFoundError:
        original = None
    yield
    if original is not None:
        replace_sky_east_template("main", original)


def test_replace_then_read_round_trip(_backup_main_template):
    new_bytes = _make_xlsx_bytes("from-test")
    replace_sky_east_template("main", new_bytes)
    assert read_sky_east_template("main") == new_bytes


def test_replace_unknown_kind_raises():
    with pytest.raises(ValueError):
        replace_sky_east_template("garbage", _make_xlsx_bytes())


def test_replace_rejects_non_xlsx_payload(_backup_main_template):
    with pytest.raises(ValueError):
        replace_sky_east_template("main", b"not-an-xlsx")


def test_read_unknown_kind_raises():
    with pytest.raises(ValueError):
        read_sky_east_template("garbage")


# ---------------------------------------------------------------------------
# Config file write/read with JSON validation
# ---------------------------------------------------------------------------

@pytest.fixture
def _backup_config():
    original = read_sky_east_config_text()
    yield
    write_sky_east_config_text(original)


def test_write_config_round_trip(_backup_config):
    write_sky_east_config_text('{"foo": 1}')
    assert read_sky_east_config_text() == '{"foo": 1}'


def test_write_invalid_json_raises(_backup_config):
    import json
    with pytest.raises(json.JSONDecodeError):
        write_sky_east_config_text("not json at all")


def test_write_empty_string_deletes_config(_backup_config):
    write_sky_east_config_text('{"x": 2}')
    assert read_sky_east_config_text() == '{"x": 2}'
    write_sky_east_config_text("   ")  # whitespace counts as empty
    assert read_sky_east_config_text() == ""
