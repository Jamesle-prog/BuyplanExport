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
    color_ai_enhance._match_cache.clear()
    yield
    color_ai_enhance._cache.clear()
    color_ai_enhance._match_cache.clear()


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


# ---------------------------------------------------------------------------
# match_color_to_candidates — constrained match against colours on file
# ---------------------------------------------------------------------------

def test_match_color_to_candidates_returns_empty_without_api_key():
    assert color_ai_enhance.match_color_to_candidates("Dark Blue", ["Navy"], "") == ""


def test_match_color_to_candidates_returns_empty_with_no_candidates():
    assert color_ai_enhance.match_color_to_candidates("Dark Blue", [], "sk-fake") == ""


def test_match_color_to_candidates_picks_typo_correction(monkeypatch):
    """The intended use case: a typo/misspelling of the SAME name, not a
    different-but-related colour name -- "Daek Blue" -> "Dark Blue" is a
    spelling correction; "Navy" -> "Dark Blue" would be guessing across two
    genuinely different colour names, which the prompt explicitly forbids.
    """
    def _create(**kwargs):
        return _FakeResponse(json.dumps({"match": "Dark Blue"}))

    _install_fake_openai(monkeypatch, _create)
    result = color_ai_enhance.match_color_to_candidates(
        "Daek Blue", ["Dark Blue", "Black"], "sk-fake",
    )
    assert result == "Dark Blue"


def test_match_color_to_candidates_rejects_hallucinated_answer(monkeypatch):
    """The model must never return a colour that isn't one of the candidates
    -- an answer outside the candidate set is treated as no match.
    """
    def _create(**kwargs):
        return _FakeResponse(json.dumps({"match": "Teal"}))   # not a candidate

    _install_fake_openai(monkeypatch, _create)
    result = color_ai_enhance.match_color_to_candidates(
        "Dark Blue", ["Navy", "Black"], "sk-fake",
    )
    assert result == ""


def test_match_color_to_candidates_empty_match_returns_empty(monkeypatch):
    def _create(**kwargs):
        return _FakeResponse(json.dumps({"match": ""}))

    _install_fake_openai(monkeypatch, _create)
    assert color_ai_enhance.match_color_to_candidates(
        "Chartreuse", ["Navy", "Black"], "sk-fake",
    ) == ""


def test_match_color_to_candidates_is_cached(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"match": "Navy"}))

    _install_fake_openai(monkeypatch, _create)
    a = color_ai_enhance.match_color_to_candidates("Dark Blue", ["Navy"], "sk-fake")
    b = color_ai_enhance.match_color_to_candidates("Dark Blue", ["Navy"], "sk-fake")
    assert a == b == "Navy"
    assert len(calls) == 1   # second question served from cache


def test_match_color_to_candidates_returns_empty_on_api_error(monkeypatch):
    def _create(**kwargs):
        raise RuntimeError("network down")

    _install_fake_openai(monkeypatch, _create)
    assert color_ai_enhance.match_color_to_candidates(
        "Dark Blue", ["Navy"], "sk-fake",
    ) == ""


def test_match_prompt_forbids_cross_name_synonym_matching():
    """Regression guard on the prompt text itself: "Navy" and "Dark Blue"
    are different colour names (different dye lots/codes), not spelling
    variants of one name -- matching them silently assigns the wrong colour
    code to an order. The prompt must explicitly forbid this, not just
    permit typo/abbreviation correction.
    """
    prompt = color_ai_enhance._MATCH_SYSTEM_PROMPT
    assert "Navy" in prompt and "Dark Blue" in prompt
    assert "NOT the same colour" in prompt or "NOT the same" in prompt
    assert "Treat synonyms as the same" not in prompt


# ---------------------------------------------------------------------------
# deepseek-reasoner support — temperature must be omitted, not sent as 0
# ---------------------------------------------------------------------------

def test_recognize_colors_omits_temperature_for_reasoning_model(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"colors": ["Navy"]}))

    _install_fake_openai(monkeypatch, _create)
    color_ai_enhance.recognize_colors("navy", "sk-fake", "deepseek-reasoner")
    assert "temperature" not in calls[0]


def test_recognize_colors_includes_temperature_for_chat_model(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"colors": ["Navy"]}))

    _install_fake_openai(monkeypatch, _create)
    color_ai_enhance.recognize_colors("navy", "sk-fake", "deepseek-chat")
    assert calls[0]["temperature"] == 0


def test_match_color_to_candidates_omits_temperature_for_reasoning_model(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"match": "Navy"}))

    _install_fake_openai(monkeypatch, _create)
    color_ai_enhance.match_color_to_candidates(
        "Dark Blue", ["Navy"], "sk-fake", "deepseek-reasoner",
    )
    assert "temperature" not in calls[0]


# ---------------------------------------------------------------------------
# Failures must never be cached — only a genuine success is memoised, so a
# transient/config problem doesn't permanently block retries.
# ---------------------------------------------------------------------------

def test_recognize_colors_does_not_cache_api_errors(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("transient failure")
        return _FakeResponse(json.dumps({"colors": ["Navy"]}))

    _install_fake_openai(monkeypatch, _create)
    first  = color_ai_enhance.recognize_colors("navy", "sk-fake")
    second = color_ai_enhance.recognize_colors("navy", "sk-fake")
    assert first == ()
    assert second == ("Navy",)
    assert len(calls) == 2   # second call actually retried, not served from cache


def test_match_color_to_candidates_does_not_cache_failures(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("transient failure")
        return _FakeResponse(json.dumps({"match": "Navy"}))

    _install_fake_openai(monkeypatch, _create)
    first  = color_ai_enhance.match_color_to_candidates("Dark Blue", ["Navy"], "sk-fake")
    second = color_ai_enhance.match_color_to_candidates("Dark Blue", ["Navy"], "sk-fake")
    assert first == ""
    assert second == "Navy"
    assert len(calls) == 2   # second call actually retried, not served from cache


def test_match_color_to_candidates_does_not_cache_no_match(monkeypatch):
    """A genuine "no candidate applies" answer is also a miss -- must be
    retried next time too, since the candidate set (or the API's judgement)
    could differ on a later call.
    """
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"match": ""}))

    _install_fake_openai(monkeypatch, _create)
    color_ai_enhance.match_color_to_candidates("Chartreuse", ["Navy"], "sk-fake")
    color_ai_enhance.match_color_to_candidates("Chartreuse", ["Navy"], "sk-fake")
    assert len(calls) == 2
