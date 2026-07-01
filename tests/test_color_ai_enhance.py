"""Tests for the optional "Local + AI Enhance" colour recognition module.

The API must only ever be reached for genuine colour-lookup misses (never
for anything else), must degrade to an empty result on any failure rather
than raising, and must not re-spend a call on a raw string it has already
seen.

The ``openai`` package is an optional dependency not installed in every dev
environment (the DeepSeek integration it backs already tolerates its
absence) -- these tests inject a fake module into ``sys.modules`` rather
than assuming the real package is present.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from po_extractor.lookups import color_ai_enhance


@pytest.fixture(autouse=True)
def _clear_cache():
    color_ai_enhance._cache.clear()
    yield
    color_ai_enhance._cache.clear()


def test_recognize_colors_returns_empty_without_api_key():
    assert color_ai_enhance.recognize_colors("dark blue with white trim", "") == ()


def test_recognize_colors_returns_empty_for_blank_input():
    assert color_ai_enhance.recognize_colors("", "sk-fake") == ()


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
    """Inject a fake ``openai`` module whose ``OpenAI(...).chat.completions
    .create(**kwargs)`` calls *create_fn* -- works whether or not the real
    ``openai`` package is installed in this environment.
    """
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


def test_recognize_colors_parses_successful_response(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"colors": ["Dark Blue", "White"]}))

    _install_fake_openai(monkeypatch, _create)

    result = color_ai_enhance.recognize_colors(
        "dark blue with white strap", "sk-fake", "deepseek-chat",
    )
    assert result == ("Dark Blue", "White")
    assert len(calls) == 1


def test_recognize_colors_caches_by_raw_string(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"colors": ["Navy"]}))

    _install_fake_openai(monkeypatch, _create)

    first  = color_ai_enhance.recognize_colors("navy", "sk-fake")
    second = color_ai_enhance.recognize_colors("navy", "sk-fake")
    assert first == second == ("Navy",)
    assert len(calls) == 1   # second call served from cache, no new API hit


def test_recognize_colors_returns_empty_on_api_error(monkeypatch):
    def _create(**kwargs):
        raise RuntimeError("network down")

    _install_fake_openai(monkeypatch, _create)
    assert color_ai_enhance.recognize_colors("mystery hue", "sk-fake") == ()


def test_recognize_colors_returns_empty_on_malformed_json(monkeypatch):
    def _create(**kwargs):
        return _FakeResponse("not json at all")

    _install_fake_openai(monkeypatch, _create)
    assert color_ai_enhance.recognize_colors("garbled", "sk-fake") == ()
