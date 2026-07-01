"""Optional AI-assisted colour recognition — "Local + AI Enhance" mode.

Called ONLY as a last resort, after a colour has already failed to resolve
against the selected local source (大货进度表 / internal colour DB). The API
is asked to recognise the colour name(s) actually present in the raw string
and return normalised English candidates to retry the *same* local lookup
with — it never supplies a Chinese translation or colour code itself, so a
wrong guess can't inject bad data; at worst it just fails to unlock a match
that was already sitting in the trusted DB.

Never invoked for anything else (PO fields, dates, other extraction data) —
scoped exclusively to the colour-lookup-miss path, and memoised per raw
string so a colour repeated across many order-file rows costs one API call,
not one per row.
"""
from __future__ import annotations

import json

from ..utils.deepseek_client import chat_kwargs as _chat_kwargs

# Process-lifetime cache: raw colour string -> resolved candidate tuple.
# Deliberately module-level (not per-export) so re-running an export for the
# same file, or the next file with overlapping colours, doesn't re-spend
# tokens on a string already seen.
_cache: dict[str, tuple[str, ...]] = {}

# Separate cache for the constrained candidate-match path, keyed by
# (client_colour, sorted candidate tuple) so the same (colour, candidate-set)
# question is only ever asked once.
_match_cache: dict[tuple, str] = {}

_SYSTEM_PROMPT = """\
You identify colour names in short garment colour description strings.
Return ONLY a JSON object: {"colors": ["<name1>", "<name2>", ...]}

Rules:
- List each distinct colour name mentioned, in English, normalised to
  Title Case (e.g. "Dark Blue", "White").
- Strip non-colour qualifiers (fabric, trims, "with", "stripe", pattern
  words) unless removing them would lose the colour itself.
- If only one colour is present, return a single-item list.
- If you cannot identify any colour, return {"colors": []}.
- Return exactly one JSON object, nothing else.
"""

_MATCH_SYSTEM_PROMPT = """\
You match a garment colour string to a known list of colour names for the
same style, but ONLY when they are the SAME NAME written differently — a
typo, an abbreviation, extra/missing spacing or punctuation, or a case
difference. You are NOT deciding whether two colours look similar or belong
to the same colour family.

You are given a CLIENT colour (from an order form) and a list of CANDIDATE
colours (the colours actually recorded for that exact style).

Return ONLY a JSON object: {"match": "<exact candidate string, or empty>"}

Rules — a match is ONLY valid when the candidate is the same underlying name:
- Obvious typo/misspelling of the identical name: "Daek Blue" = "Dark Blue".
- Abbreviation that expands to the identical name: "DK Brown" = "Dark Brown".
- Formatting-only differences: case, spacing, punctuation, a numeric colour
  code prefix ("52# Navy" = "Navy").

Do NOT match on any of these — they are DIFFERENT colours even if related
or visually similar, and treating them as the same could assign the wrong
dye lot/colour code to the wrong item:
- Different colour-family names: "Navy" vs "Dark Blue", "Cream" vs "White",
  "Maroon" vs "Burgundy" are NOT the same colour — they are genuinely
  different names, not spelling variants of one name.
- Different shades or modifiers: "Dark Blue" vs "Blue", "Light Grey" vs
  "Grey" are NOT the same colour.
- Guessing based on visual similarity or general colour-family membership.

When in doubt, or when the candidate is a different colour name rather than
a spelling/formatting variant of the same name, return {"match": ""} — an
incorrect match is worse than no match, since it silently assigns the wrong
colour code to the order.

The "match" value MUST be one of the CANDIDATE strings copied verbatim, or
an empty string. Return exactly one JSON object, nothing else.
"""


def recognize_colors(
    raw_color: str, api_key: str, model: str = "deepseek-chat",
) -> tuple[str, ...]:
    """Return normalised English colour-name candidates for *raw_color*.

    Returns an empty tuple when *raw_color* or *api_key* is blank, or on any
    API/parse error — callers must treat that as "no enhancement available"
    and keep their existing not-found result. This function never raises.

    Only a genuine (non-empty) result is cached — a failure (API error,
    malformed response, no colour recognised) is never cached, so a
    transient problem (network blip, a since-fixed config issue) doesn't
    permanently block every future attempt for the same string within this
    process's lifetime.
    """
    if not raw_color or not api_key:
        return ()
    if raw_color in _cache:
        return _cache[raw_color]

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": raw_color[:200]},
            ],
            max_tokens=128,
            response_format={"type": "json_object"},
            **_chat_kwargs(model),
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        colors = tuple(
            str(c).strip() for c in (data.get("colors") or []) if str(c).strip()
        )
    except Exception:
        colors = ()

    if colors:
        _cache[raw_color] = colors
    return colors


def match_color_to_candidates(
    client_color: str, candidates: list[str], api_key: str,
    model: str = "deepseek-chat",
) -> str:
    """Ask the API which *candidate* colour is the same as *client_color*.

    Used when an order-file colour doesn't exact-match any 大货进度表 colour
    for a given 客人PC NO + 款式, but that combo *does* have colour(s) on
    file: rather than guessing an open-ended normalisation, the API is asked
    to pick which of the *actual* recorded colours is the SAME NAME written
    differently — a typo ("Daek Blue" -> "Dark Blue") or an abbreviation of
    the identical name ("DK Brown" -> "Dark Brown"). It is explicitly told
    NOT to match different-but-related colour names (e.g. "Navy" is a
    different colour from "Dark Blue", not a synonym) — a wrong pick would
    silently assign the wrong colour code to the order, which is worse than
    an honest 未找到.

    Returns the chosen candidate **verbatim** (guaranteed to be one of
    *candidates*), or ``""`` when nothing matches / on any error / when the
    inputs are blank. The returned name is only ever used to re-key the
    trusted local lookup — the API never supplies a Chinese name or code, so
    a wrong pick can at worst surface the wrong *existing* row's colour, never
    fabricate data. Never raises.

    Only a genuine match is cached — a miss (no candidate applies, an API
    error, a malformed response) is never cached, so a transient problem
    doesn't permanently block every future attempt for the same
    (colour, candidate-set) pair within this process's lifetime.
    """
    if not client_color or not candidates or not api_key:
        return ""
    cache_key = (client_color, tuple(sorted(candidates)))
    if cache_key in _match_cache:
        return _match_cache[cache_key]

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        user_msg = (
            f'CLIENT colour: "{client_color[:200]}"\n'
            f'CANDIDATE colours: {list(candidates)}'
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _MATCH_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=64,
            response_format={"type": "json_object"},
            **_chat_kwargs(model),
        )
        raw = response.choices[0].message.content or "{}"
        picked = str(json.loads(raw).get("match", "")).strip()
        # Only accept an answer that is exactly one of the candidates — guards
        # against the model inventing a colour that isn't on file.
        picked = picked if picked in candidates else ""
    except Exception:
        picked = ""

    if picked:
        _match_cache[cache_key] = picked
    return picked
