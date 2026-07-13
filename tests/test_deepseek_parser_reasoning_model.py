"""Regression: _call_deepseek() must omit temperature for reasoning models.

deepseek-reasoner rejects the temperature parameter that deepseek-chat
accepts -- passing it unconditionally broke PO PDF extraction whenever a
reasoning model was selected in Admin Settings.
"""
from __future__ import annotations

import json
import sys
import types

from po_extractor.parsers.deepseek_parser import _call_deepseek


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _install_fake_openai(monkeypatch, create_fn):
    class _FakeCompletions:
        def create(self, **kwargs):
            return create_fn(**kwargs)

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self, **kwargs):
            pass
        chat = _FakeChat()

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = lambda **kwargs: _FakeClient(**kwargs)
    monkeypatch.setitem(sys.modules, "openai", fake_module)


def test_call_deepseek_omits_temperature_for_reasoning_model(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"po_number": "PO1"}))

    _install_fake_openai(monkeypatch, _create)
    _call_deepseek("some PO text", "sk-fake", "deepseek-reasoner")
    assert "temperature" not in calls[0]


def test_call_deepseek_includes_temperature_for_chat_model(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"po_number": "PO1"}))

    _install_fake_openai(monkeypatch, _create)
    _call_deepseek("some PO text", "sk-fake", "deepseek-chat")
    assert calls[0]["temperature"] == 0


def test_new_v4_models_treated_as_chat_not_reasoning():
    """deepseek-v4-pro/flash accept temperature (verified live) — they must
    NOT be classified as reasoning models (which would drop the param)."""
    from po_extractor.utils.deepseek_client import is_reasoning_model, chat_kwargs
    for m in ("deepseek-v4-flash", "deepseek-v4-pro"):
        assert not is_reasoning_model(m)
        assert chat_kwargs(m) == {"temperature": 0}
    assert is_reasoning_model("deepseek-reasoner")


def test_list_models_empty_without_key():
    from po_extractor.parsers.deepseek_parser import list_models, FALLBACK_MODELS
    assert list_models("") == []
    # the new v4 models are in the static fallback so they show even offline
    assert "deepseek-v4-pro" in FALLBACK_MODELS
    assert "deepseek-v4-flash" in FALLBACK_MODELS


def test_list_models_returns_ids_from_api(monkeypatch):
    class _M:
        def __init__(self, i): self.id = i
    class _List:
        data = [_M("deepseek-v4-pro"), _M("deepseek-v4-flash")]
    class _Models:
        def list(self): return _List()
    class _Client:
        def __init__(self, **kw): pass
        models = _Models()
    fake = types.ModuleType("openai")
    fake.OpenAI = lambda **kw: _Client(**kw)
    monkeypatch.setitem(sys.modules, "openai", fake)
    from po_extractor.parsers.deepseek_parser import list_models
    assert list_models("sk-fake") == ["deepseek-v4-pro", "deepseek-v4-flash"]
