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
