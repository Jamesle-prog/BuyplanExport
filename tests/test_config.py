"""Tests for po_extractor/config.py — fabric DB path resolution/persistence.

Covers the fix for a malformed data/fabric_config.json crashing the app:
a JSON array (``_cfg.get`` raises AttributeError) or a non-string
``fabric_db_path`` value (``.strip()`` raises AttributeError) used to only be
guarded by ``OSError``/``JSONDecodeError`` — both now fall back to the
default path instead of propagating.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point config's fabric_config.json + DATA_DIR at a scratch folder and
    make sure the FABRIC_DB_PATH env var isn't shadowing the file lookup."""
    import po_extractor.config as cfg

    cfg_file = tmp_path / "fabric_config.json"
    monkeypatch.setattr(cfg, "_FABRIC_CONFIG_FILE", str(cfg_file))
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FABRIC_DB_PATH", raising=False)
    return cfg, cfg_file


def test_get_fabric_db_path_defaults_when_no_config(isolated_config):
    cfg, _cfg_file = isolated_config
    assert cfg.get_fabric_db_path() == str(cfg._ROOT / "data" / "fabric_master.db")


def test_get_fabric_db_path_reads_valid_config(isolated_config):
    cfg, cfg_file = isolated_config
    cfg_file.write_text(json.dumps({"fabric_db_path": "D:/custom/fabric.db"}),
                        encoding="utf-8")
    assert cfg.get_fabric_db_path() == "D:/custom/fabric.db"


def test_get_fabric_db_path_survives_json_array(isolated_config):
    """A JSON array instead of an object used to raise AttributeError on
    ``_cfg.get(...)`` — must now fall back to the default path."""
    cfg, cfg_file = isolated_config
    cfg_file.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    assert cfg.get_fabric_db_path() == str(cfg._ROOT / "data" / "fabric_master.db")


def test_get_fabric_db_path_survives_non_string_value(isolated_config):
    """A non-string fabric_db_path (e.g. an int) used to raise AttributeError
    on ``.strip()`` — must now be coerced or fall back cleanly."""
    cfg, cfg_file = isolated_config
    cfg_file.write_text(json.dumps({"fabric_db_path": 12345}), encoding="utf-8")
    assert cfg.get_fabric_db_path() == "12345"


def test_get_fabric_db_path_survives_malformed_json(isolated_config):
    cfg, cfg_file = isolated_config
    cfg_file.write_text("{not valid json", encoding="utf-8")
    assert cfg.get_fabric_db_path() == str(cfg._ROOT / "data" / "fabric_master.db")


def test_save_fabric_db_path_survives_json_array(isolated_config):
    """save_fabric_db_path must not crash when the existing file holds a
    JSON array — it should treat it as a fresh config, not raise on the
    dict-only ``cfg["fabric_db_path"] = ...`` assignment."""
    cfg, cfg_file = isolated_config
    cfg_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    cfg.save_fabric_db_path("E:/new/fabric.db")
    saved = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert saved == {"fabric_db_path": "E:/new/fabric.db"}
