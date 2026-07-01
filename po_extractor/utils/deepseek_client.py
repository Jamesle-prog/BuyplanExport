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
