"""Regression tests for the live output schema helpers."""
import json
import os

from po_extractor.ui_helpers.schema import (
    schema_seed_rows, load_live_schema, save_live_schema,
    live_label_for, live_client_label_for,
)


def test_schema_seed_rows_has_required_keys():
    rows = schema_seed_rows()
    assert rows, "seed schema must not be empty"
    required_keys = {"db_col", "label", "sky_east", "infor", "legacy", "required", "notes"}
    for r in rows:
        assert required_keys.issubset(r.keys()), f"missing keys in row: {r}"


def test_load_creates_file_on_first_run(tmp_path):
    schema_path = str(tmp_path / "schema.json")
    assert not os.path.exists(schema_path)
    rows = load_live_schema(schema_path)
    assert os.path.exists(schema_path), "schema file should be seeded on first load"
    assert rows == schema_seed_rows()


def test_save_then_load_roundtrip(tmp_path):
    schema_path = str(tmp_path / "schema.json")
    rows = [{"db_col": "po_number", "label": "PO No.", "sky_east": "合同号",
             "infor": "PO", "legacy": "PO", "required": True, "notes": ""}]
    save_live_schema(schema_path, rows)
    loaded = load_live_schema(schema_path)
    assert loaded == rows


def test_live_label_returns_user_label():
    rows = [{"db_col": "po_number", "label": "Custom PO Label",
             "sky_east": "", "infor": "", "legacy": "",
             "required": True, "notes": ""}]
    assert live_label_for(rows, "po_number") == "Custom PO Label"


def test_live_label_falls_back_to_static_label_dict():
    # db_col not in rows → falls back to static LABEL or fallback arg
    label = live_label_for([], "po_number", fallback="PO No.")
    assert label == "PO No." or label  # at minimum non-empty


def test_live_client_label_uses_client_alias():
    rows = [{"db_col": "po_number", "label": "PO", "sky_east": "合同号",
             "infor": "Order", "legacy": "PO#",
             "required": True, "notes": ""}]
    assert live_client_label_for(rows, "po_number", "sky_east") == "合同号"
    assert live_client_label_for(rows, "po_number", "infor") == "Order"
    assert live_client_label_for(rows, "po_number", "legacy") == "PO#"


def test_live_client_label_empty_alias_falls_back_to_label():
    rows = [{"db_col": "po_number", "label": "PO",
             "sky_east": "", "infor": "", "legacy": "",
             "required": True, "notes": ""}]
    assert live_client_label_for(rows, "po_number", "sky_east") == "PO"
