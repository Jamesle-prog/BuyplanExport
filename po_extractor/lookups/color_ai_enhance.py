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

# Process-lifetime cache: raw colour string -> resolved candidate tuple.
# Deliberately module-level (not per-export) so re-running an export for the
# same file, or the next file with overlapping colours, doesn't re-spend
# tokens on a string already seen.
_cache: dict[str, tuple[str, ...]] = {}

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


def recognize_colors(
    raw_color: str, api_key: str, model: str = "deepseek-chat",
) -> tuple[str, ...]:
    """Return normalised English colour-name candidates for *raw_color*.

    Returns an empty tuple when *raw_color* or *api_key* is blank, or on any
    API/parse error — callers must treat that as "no enhancement available"
    and keep their existing not-found result. This function never raises.
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
            temperature=0,
            max_tokens=128,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        colors = tuple(
            str(c).strip() for c in (data.get("colors") or []) if str(c).strip()
        )
    except Exception:
        colors = ()

    _cache[raw_color] = colors
    return colors
