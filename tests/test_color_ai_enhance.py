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
def _clear_cache(monkeypatch):
    # Persistence off by default: these tests stub the API and must neither
    # read real cached answers from the canonical DB nor write to it.
    monkeypatch.setattr(color_ai_enhance, "_persist_enabled", False)
    # Same reasoning for the learned-corrections table: these tests must not
    # be answered by a correction recorded on real data, nor teach one.
    monkeypatch.setattr(color_ai_enhance, "_learn_enabled", False)
    color_ai_enhance._cache.clear()
    color_ai_enhance._match_cache.clear()
    yield
    color_ai_enhance._cache.clear()
    color_ai_enhance._match_cache.clear()


def test_persistent_cache_round_trip(monkeypatch, tmp_path):
    """A genuine result survives a simulated process restart (in-memory
    caches cleared) via the SQLite layer; failures are never persisted."""
    import po_extractor.config as cfg
    monkeypatch.setattr(cfg, "DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setattr(color_ai_enhance, "_persist_enabled", True)
    monkeypatch.setattr(color_ai_enhance, "_persist_ready", False)

    calls = []

    def _create(**kwargs):
        calls.append(1)
        return _FakeResponse('{"colors": ["Dark Blue"]}')
    _install_fake_openai(monkeypatch, _create)

    assert color_ai_enhance.recognize_colors("daek blue", "k", "m1") == ("Dark Blue",)
    assert len(calls) == 1

    # Simulated restart: memory gone, DB remains -> no second API call.
    color_ai_enhance._cache.clear()
    assert color_ai_enhance.recognize_colors("daek blue", "k", "m1") == ("Dark Blue",)
    assert len(calls) == 1

    # A different model re-asks (model is part of the PERSISTENT key; the
    # in-memory cache is keyed by raw string only, so clear it first).
    color_ai_enhance._cache.clear()
    assert color_ai_enhance.recognize_colors("daek blue", "k", "m2") == ("Dark Blue",)
    assert len(calls) == 2


def test_persistent_cache_match_round_trip(monkeypatch, tmp_path):
    import po_extractor.config as cfg
    monkeypatch.setattr(cfg, "DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setattr(color_ai_enhance, "_persist_enabled", True)
    monkeypatch.setattr(color_ai_enhance, "_persist_ready", False)

    calls = []

    def _create(**kwargs):
        calls.append(1)
        return _FakeResponse('{"match": "Daek Blue"}')
    _install_fake_openai(monkeypatch, _create)

    assert color_ai_enhance.match_color_to_candidates(
        "dark blue", ["Daek Blue"], "k", "m1") == "Daek Blue"
    color_ai_enhance._match_cache.clear()
    assert color_ai_enhance.match_color_to_candidates(
        "dark blue", ["Daek Blue"], "k", "m1") == "Daek Blue"
    assert len(calls) == 1
    # Stored pick no longer among candidates -> ignored, fresh call made.
    assert color_ai_enhance.match_color_to_candidates(
        "dark blue", ["Navy"], "k", "m1") == ""
    assert len(calls) == 2


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
# Reasoning models spend part of max_tokens on a hidden reasoning trace --
# a budget sized for a chat-model answer gets fully consumed by reasoning,
# truncating the response before any answer is written (finish_reason ==
# "length", empty content). Confirmed live: 64 tokens produced empty content
# with all 64 spent on reasoning; 1024 completed normally with the correct
# answer. Reasoning models must get a much larger max_tokens budget.
# ---------------------------------------------------------------------------

def test_recognize_colors_raises_max_tokens_for_reasoning_model(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"colors": ["Navy"]}))

    _install_fake_openai(monkeypatch, _create)
    color_ai_enhance.recognize_colors("navy", "sk-fake", "deepseek-reasoner")
    assert calls[0]["max_tokens"] >= 1024


def test_recognize_colors_keeps_small_max_tokens_for_chat_model(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"colors": ["Navy"]}))

    _install_fake_openai(monkeypatch, _create)
    color_ai_enhance.recognize_colors("navy", "sk-fake", "deepseek-chat")
    assert calls[0]["max_tokens"] == 128


def test_match_color_to_candidates_raises_max_tokens_for_reasoning_model(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"match": "Navy"}))

    _install_fake_openai(monkeypatch, _create)
    color_ai_enhance.match_color_to_candidates(
        "Dark Blue", ["Navy"], "sk-fake", "deepseek-reasoner",
    )
    assert calls[0]["max_tokens"] >= 1024


def test_match_color_to_candidates_keeps_small_max_tokens_for_chat_model(monkeypatch):
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"match": "Navy"}))

    _install_fake_openai(monkeypatch, _create)
    color_ai_enhance.match_color_to_candidates(
        "Dark Blue", ["Navy"], "sk-fake", "deepseek-chat",
    )
    assert calls[0]["max_tokens"] == 64


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


def test_match_color_to_candidates_caches_genuine_no_match(monkeypatch):
    """POLICY (v2.84.0): a genuine "no candidate applies" answer IS cached --
    the same honest miss re-asked on every generation was the dominant
    recurring cost on datasets with many unresolvable colours. The candidate
    set is part of the cache key, so a changed set still re-asks; only
    transport/parse failures stay uncached (previous two tests)."""
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"match": ""}))

    _install_fake_openai(monkeypatch, _create)
    assert color_ai_enhance.match_color_to_candidates("Chartreuse", ["Navy"], "sk-fake") == ""
    assert color_ai_enhance.match_color_to_candidates("Chartreuse", ["Navy"], "sk-fake") == ""
    assert len(calls) == 1                      # served from cache
    # A DIFFERENT candidate set is a different question -> re-asked.
    color_ai_enhance.match_color_to_candidates("Chartreuse", ["Green"], "sk-fake")
    assert len(calls) == 2


def test_recognize_colors_caches_genuine_empty_answer(monkeypatch):
    """POLICY (v2.84.0): a successful "no colour identified" answer is cached
    (memory + persistent) -- see test above for rationale."""
    calls = []

    def _create(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(json.dumps({"colors": []}))

    _install_fake_openai(monkeypatch, _create)
    assert color_ai_enhance.recognize_colors("fabric code XJ-99", "sk-fake") == ()
    assert color_ai_enhance.recognize_colors("fabric code XJ-99", "sk-fake") == ()
    assert len(calls) == 1


def test_persistent_cache_stores_negative_answers(monkeypatch, tmp_path):
    """Negative answers survive a simulated restart too -- that's the point:
    an unresolvable colour must never be re-purchased from the API."""
    import po_extractor.config as cfg
    monkeypatch.setattr(cfg, "DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setattr(color_ai_enhance, "_persist_enabled", True)
    monkeypatch.setattr(color_ai_enhance, "_persist_ready", False)

    calls = []

    def _create(**kwargs):
        calls.append(1)
        return _FakeResponse(json.dumps({"match": ""}))
    _install_fake_openai(monkeypatch, _create)

    assert color_ai_enhance.match_color_to_candidates("Puce", ["Navy"], "k", "m1") == ""
    color_ai_enhance._match_cache.clear()       # simulated restart
    assert color_ai_enhance.match_color_to_candidates("Puce", ["Navy"], "k", "m1") == ""
    assert len(calls) == 1
