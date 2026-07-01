"""Tests for the shared DeepSeek chat-completion kwargs helper.

Regression: deepseek-reasoner (and other DeepSeek "thinking mode" models)
reject sampling params like temperature that the chat models accept --
passing temperature=0 unconditionally caused every AI-enhance / DeepSeek
Test API key / PO extraction call to fail outright whenever a reasoning
model was selected.
"""
from __future__ import annotations

from po_extractor.utils.deepseek_client import chat_kwargs, is_reasoning_model


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
