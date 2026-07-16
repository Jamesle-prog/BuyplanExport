"""Regression test for ui/admin_settings.py (Fix 9).

"auto" extraction mode also calls the DeepSeek API (per the tab's own help
text: "Auto ... Needs the API key below"), so it must get the live model
list the same way "deepseek" mode does. Before the fix, only
chosen_method == "deepseek" fetched _live_deepseek_models(...), so "auto"
users only ever saw the small hardcoded FALLBACK_MODELS list.
"""
from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.admin_settings as asettings


class _FakeStore:
    def get(self, key, default=""):
        return default


def _run_deepseek_settings(monkeypatch, chosen_method: str, live_calls: list):
    def _fake_live_models(_key_fp):
        live_calls.append(_key_fp)
        return ["deepseek-live-model"]

    monkeypatch.setattr(asettings, "_live_deepseek_models", _fake_live_models)

    def _fake_radio(label, *args, **kwargs):
        if kwargs.get("key") == "admin_extraction_method":
            return chosen_method
        return kwargs.get("index", 0)

    def _fake_text_input(label, *args, **kwargs):
        if kwargs.get("key") == "admin_deepseek_key":
            return "sk-test-key"
        return ""

    def _fake_selectbox(label, options, *args, **kwargs):
        return options[0] if options else None

    monkeypatch.setattr(asettings.st, "radio", _fake_radio)
    monkeypatch.setattr(asettings.st, "text_input", _fake_text_input)
    monkeypatch.setattr(asettings.st, "selectbox", _fake_selectbox)
    monkeypatch.setattr(asettings.st, "toggle", lambda *a, **k: False)
    monkeypatch.setattr(asettings.st, "button", lambda *a, **k: False)

    asettings._show_deepseek_settings(_FakeStore())


def test_auto_method_fetches_live_deepseek_models(monkeypatch):
    calls: list = []
    _run_deepseek_settings(monkeypatch, "auto", calls)
    assert calls, "'auto' extraction method must fetch the live DeepSeek model list"


def test_deepseek_method_fetches_live_deepseek_models(monkeypatch):
    calls: list = []
    _run_deepseek_settings(monkeypatch, "deepseek", calls)
    assert calls, "'deepseek' extraction method must still fetch the live model list"


def test_regex_method_does_not_fetch_live_models(monkeypatch):
    calls: list = []
    _run_deepseek_settings(monkeypatch, "regex", calls)
    assert not calls, "'regex' mode never calls the DeepSeek API"
