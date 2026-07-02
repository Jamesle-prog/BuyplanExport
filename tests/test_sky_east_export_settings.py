"""Tests for ``_resolve_ai_enhance_settings`` — the shared helper both Sky East
exporters use to resolve the "Local + AI Enhance" mode / DeepSeek key / model.

Previously this ~19-line block was copy-pasted into both exporters; the helper
removes the duplication, so these tests cover it once:
  • explicit (non-None) arguments pass straight through, never touching the
    settings store,
  • any None argument is read from the admin AppSettings,
  • a store/import failure degrades to safe defaults instead of raising.
"""
from __future__ import annotations

import pytest

import po_extractor.exporters.sky_east_buyplan_export as _mod


def test_explicit_values_pass_through_without_touching_settings(monkeypatch):
    def _boom():
        raise AssertionError("settings store must not be consulted")
    monkeypatch.setattr("po_extractor.store.get_app_settings_store", _boom)

    assert _mod._resolve_ai_enhance_settings(True, "sk-x", "deepseek-reasoner") == (
        True, "sk-x", "deepseek-reasoner",
    )
    assert _mod._resolve_ai_enhance_settings(False, "", "deepseek-chat") == (
        False, "", "deepseek-chat",
    )


def test_none_values_read_from_app_settings(monkeypatch, tmp_path):
    from po_extractor.store.app_settings_store import (
        AppSettingsStore, KEY_COLOR_AI_ENHANCE,
        KEY_DEEPSEEK_API_KEY, KEY_DEEPSEEK_MODEL,
    )

    store = AppSettingsStore(str(tmp_path / "settings.db"))
    store.set(KEY_COLOR_AI_ENHANCE, "local_ai_enhance")
    store.set(KEY_DEEPSEEK_API_KEY, "sk-xyz")
    store.set(KEY_DEEPSEEK_MODEL, "deepseek-reasoner")
    monkeypatch.setattr("po_extractor.store.get_app_settings_store", lambda: store)

    assert _mod._resolve_ai_enhance_settings(None, None, None) == (
        True, "sk-xyz", "deepseek-reasoner",
    )


def test_mode_local_means_ai_disabled(monkeypatch, tmp_path):
    from po_extractor.store.app_settings_store import (
        AppSettingsStore, KEY_COLOR_AI_ENHANCE,
    )
    store = AppSettingsStore(str(tmp_path / "settings.db"))
    store.set(KEY_COLOR_AI_ENHANCE, "local")
    monkeypatch.setattr("po_extractor.store.get_app_settings_store", lambda: store)

    ai_enhance, _, _ = _mod._resolve_ai_enhance_settings(None, None, None)
    assert ai_enhance is False


def test_explicit_override_wins_over_settings(monkeypatch, tmp_path):
    # ai_enhance explicit, key/model from settings — only the None ones read.
    from po_extractor.store.app_settings_store import (
        AppSettingsStore, KEY_DEEPSEEK_API_KEY, KEY_DEEPSEEK_MODEL,
    )
    store = AppSettingsStore(str(tmp_path / "settings.db"))
    store.set(KEY_DEEPSEEK_API_KEY, "sk-from-db")
    store.set(KEY_DEEPSEEK_MODEL, "deepseek-chat")
    monkeypatch.setattr("po_extractor.store.get_app_settings_store", lambda: store)

    assert _mod._resolve_ai_enhance_settings(True, None, None) == (
        True, "sk-from-db", "deepseek-chat",
    )


def test_settings_failure_falls_back_to_safe_defaults(monkeypatch):
    def _boom():
        raise RuntimeError("settings store unavailable")
    monkeypatch.setattr("po_extractor.store.get_app_settings_store", _boom)

    with pytest.warns(UserWarning):
        result = _mod._resolve_ai_enhance_settings(None, None, None)
    assert result == (False, "", "deepseek-chat")
