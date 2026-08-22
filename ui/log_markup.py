"""Markup for processing-log lines — the one place their status colours live.

``show_processing_log`` renders each line with ``unsafe_allow_html=True`` so
producers can colour a filename green or red.  Before this module every
producer hand-wrote its own ``<span style="color:#dc3545">`` — four files, two
different warning colours (amber in GIII, orange in Sky East), two warning
glyphs (``⚠`` / ``⚠️``), and none of it adapted to dark mode, where amber on
charcoal is unreadable.  The CSS classes this module emits are defined once in
``app.py`` with light *and* dark values.

No Streamlit import: this is pure string building, so it can be unit-tested
without a running app and imported from anywhere.

Escaping contract
-----------------
``badge()`` does **not** escape ``text``.  Producers interpolate attacker-
controlled values (uploaded filenames, supplier cell contents) and already
wrap each one in ``html.escape()`` — a rule ``tests/test_log_html_escaping.py``
enforces on every ``log.append`` call, ``badge()`` arguments included.  Keeping
escaping at the call site means the helper can carry trusted markup such as
``<b>`` without double-encoding it.  Pass ``escape=True`` when the whole text
is a single untrusted value and you want the helper to do it.
"""
from __future__ import annotations

import html as _html

# kind -> (CSS class, glyph).  The glyph is part of the vocabulary: a line's
# meaning must survive being copied into an email or a ticket as plain text,
# where the colour is gone.
_KINDS: dict[str, tuple[str, str]] = {
    "ok":   ("badge-ok",   "✅"),
    "warn": ("badge-warn", "⚠️"),
    "err":  ("badge-err",  "❌"),
}

# Public, so the CSS in app.py and any test can enumerate them.
LOG_KINDS = tuple(_KINDS)


def badge(kind: str, text: str, *, glyph: bool = True,
          escape: bool = False) -> str:
    """Wrap *text* in the status span for *kind* (``ok`` / ``warn`` / ``err``).

    >>> badge("ok", "PO-123.pdf")
    '<span class="badge-ok">✅ PO-123.pdf</span>'
    >>> badge("err", "<bad>", escape=True)
    '<span class="badge-err">❌ &lt;bad&gt;</span>'
    """
    try:
        css, mark = _KINDS[kind]
    except KeyError:
        raise ValueError(f"unknown log kind {kind!r}; expected one of {LOG_KINDS}") from None
    body = _html.escape(str(text)) if escape else str(text)
    if glyph and mark:
        body = f"{mark} {body}"
    return f'<span class="{css}">{body}</span>'


def ok(text: str, **kw) -> str:
    """``badge("ok", text)``."""
    return badge("ok", text, **kw)


def warn(text: str, **kw) -> str:
    """``badge("warn", text)``."""
    return badge("warn", text, **kw)


def err(text: str, **kw) -> str:
    """``badge("err", text)``."""
    return badge("err", text, **kw)


__all__ = ["badge", "ok", "warn", "err", "LOG_KINDS"]
