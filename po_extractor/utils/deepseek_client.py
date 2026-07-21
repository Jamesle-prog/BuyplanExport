"""Shared helpers for calling DeepSeek's OpenAI-compatible API.

Every caller (PO PDF extraction, the admin "Test API key" button, colour
recognition/matching) hits the same DeepSeek quirk: the reasoning models
("thinking mode") reject sampling parameters the chat models accept.
Passing ``temperature`` to ``deepseek-reasoner`` can return a hard 400
error rather than being silently ignored — version-dependent, so don't
gamble on leniency. Route every call through :func:`chat_kwargs` instead
of hardcoding ``temperature=0``.
"""
from __future__ import annotations

# DeepSeek reasoning ("thinking mode") model name prefixes. These reject
# sampling params (temperature, top_p, presence_penalty, frequency_penalty,
# logprobs, top_logprobs) that the chat models accept.
_REASONING_MODEL_PREFIXES = ("deepseek-reasoner", "deepseek-reasoning")


def is_reasoning_model(model: str) -> bool:
    return bool(model) and model.startswith(_REASONING_MODEL_PREFIXES)


def chat_kwargs(model: str, *, temperature: float = 0) -> dict:
    """Return extra ``chat.completions.create`` kwargs safe for *model*.

    Omits ``temperature`` for reasoning models; includes it (at
    *temperature*) for chat models.
    """
    if is_reasoning_model(model):
        return {}
    return {"temperature": temperature}


# Reasoning models spend part of ``max_tokens`` on a hidden reasoning trace
# before writing the visible answer -- a budget sized for a short chat-model
# answer (e.g. 64-128 tokens) can be entirely consumed by reasoning, cutting
# the response off (``finish_reason == "length"``) before any answer is
# written at all. Confirmed live against deepseek-reasoner: a 64-token budget
# produced empty content with 64/64 reasoning tokens spent; 1024 was enough
# for the same request to finish normally.
_REASONING_MIN_MAX_TOKENS = 1024

# Newer DeepSeek model line whose hidden reasoning trace runs far heavier
# than deepseek-reasoner's -- confirmed live: deepseek-v4-pro spent 96/100
# tokens on a trivial "say hello" prompt, and 12235 reasoning tokens on one
# real, moderately complex prompt. Unlike deepseek-reasoner it does NOT
# reject the ``temperature`` param (see is_reasoning_model), so it's tracked
# separately with its own, larger floor rather than folded into
# _REASONING_MODEL_PREFIXES.
#
# The prefix covers the WHOLE v4 line, not just -pro: deepseek-v4-flash also
# reasons invisibly (confirmed live on the colour candidate-match prompt: 44
# reasoning tokens inside a 64-token budget, and intermittently MORE -- the
# same call nondeterministically truncated to an empty answer whenever the
# trace outgrew the cap, so AI colour matches randomly failed). max_tokens is
# a cap, not a spend -- a generous floor costs nothing when the answer is
# short, so one floor for every v4 variant is the safe default.
_HIGH_REASONING_MODEL_PREFIXES = ("deepseek-v4",)
_HIGH_REASONING_MIN_MAX_TOKENS = 8192


def max_tokens_for(model: str, base: int) -> int:
    """Return a ``max_tokens`` value safe for *model*, at least *base*.

    Reasoning models get a floor so the hidden reasoning trace has room to
    finish before the visible answer is written; chat models get *base*
    unchanged.
    """
    if bool(model) and model.startswith(_HIGH_REASONING_MODEL_PREFIXES):
        return max(base, _HIGH_REASONING_MIN_MAX_TOKENS)
    if is_reasoning_model(model):
        return max(base, _REASONING_MIN_MAX_TOKENS)
    return base
