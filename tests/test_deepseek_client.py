"""Tests for the shared DeepSeek chat-completion kwargs helper.

Regression: deepseek-reasoner (and other DeepSeek "thinking mode" models)
reject sampling params like temperature that the chat models accept --
passing temperature=0 unconditionally caused every AI-enhance / DeepSeek
Test API key / PO extraction call to fail outright whenever a reasoning
model was selected.

Regression: deepseek-reasoner spends part of ``max_tokens`` on a hidden
reasoning trace before writing the visible answer. A budget sized for a
short chat-model answer (e.g. 64 tokens) got fully consumed by reasoning,
truncating the response (``finish_reason == "length"``) before any JSON
answer was written -- confirmed live: a 64-token budget produced empty
content with 64/64 reasoning tokens spent, while 1024 completed normally.
"""
from __future__ import annotations

from po_extractor.utils.deepseek_client import (
    chat_kwargs, is_reasoning_model, max_tokens_for,
)


def test_is_reasoning_model_true_for_deepseek_reasoner():
    assert is_reasoning_model("deepseek-reasoner") is True


def test_is_reasoning_model_false_for_deepseek_chat():
    assert is_reasoning_model("deepseek-chat") is False


def test_is_reasoning_model_false_for_blank():
    assert is_reasoning_model("") is False
    assert is_reasoning_model(None) is False


def test_chat_kwargs_omits_temperature_for_reasoning_model():
    assert chat_kwargs("deepseek-reasoner") == {}


def test_chat_kwargs_includes_temperature_for_chat_model():
    assert chat_kwargs("deepseek-chat") == {"temperature": 0}


def test_chat_kwargs_respects_custom_temperature_for_chat_model():
    assert chat_kwargs("deepseek-chat", temperature=0.7) == {"temperature": 0.7}


def test_max_tokens_for_raises_floor_for_reasoning_model():
    assert max_tokens_for("deepseek-reasoner", 64) == 1024
    assert max_tokens_for("deepseek-reasoner", 128) == 1024


def test_max_tokens_for_keeps_base_when_already_above_floor():
    assert max_tokens_for("deepseek-reasoner", 2000) == 2000


def test_max_tokens_for_leaves_chat_model_base_unchanged():
    assert max_tokens_for("deepseek-chat", 64) == 64
    assert max_tokens_for("deepseek-chat", 128) == 128


def test_deepseek_v4_pro_not_treated_as_temperature_rejecting():
    """Unlike deepseek-reasoner, deepseek-v4-pro accepts temperature fine
    (confirmed live) -- it must not be folded into is_reasoning_model()."""
    assert is_reasoning_model("deepseek-v4-pro") is False
    assert chat_kwargs("deepseek-v4-pro") == {"temperature": 0}


def test_max_tokens_for_raises_higher_floor_for_deepseek_v4_pro():
    """Regression: deepseek-v4-pro's hidden reasoning trace is far heavier
    than deepseek-reasoner's (confirmed live: 96/100 tokens spent on a
    trivial prompt, 12235 on one real moderately-complex prompt) -- the
    existing 1024 floor silently produced empty responses for every
    price-mask / AI-colour-enhance call once an admin selected this model."""
    assert max_tokens_for("deepseek-v4-pro", 64) == 8192
    assert max_tokens_for("deepseek-v4-pro", 128) == 8192
    assert max_tokens_for("deepseek-v4-pro", 20000) == 20000
