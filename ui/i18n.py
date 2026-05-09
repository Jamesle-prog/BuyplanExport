"""Lightweight i18n layer — ``t()`` function with session-level cache.

Usage
-----
>>> from ui.i18n import t
>>> t("Save")           # → "保存" when UI_LANG == "zh", else "Save"
>>> t("Save", lang="en") # always English

The cache is a per-language dict built once per Streamlit session from the
``UITranslationStore``.  It is automatically invalidated when the user
switches languages (``SK.UI_LANG`` changes) by keying on the language code.

Calling ``clear_cache()`` forces a fresh DB read on the next ``t()`` call —
use this in the admin UI after editing translations.
"""
from __future__ import annotations

import streamlit as st

from ui.session_keys import SK

# Session-state key prefix: one entry per language, e.g. "_i18n_zh"
_CACHE_PREFIX = "_i18n_"


def _active_lang() -> str:
    return st.session_state.get(SK.UI_LANG, "en")


def _cache_key(lang: str) -> str:
    return f"{_CACHE_PREFIX}{lang}"


def _get_cache(lang: str) -> dict[str, str]:
    """Return (possibly cached) lookup dict for *lang*."""
    ck = _cache_key(lang)
    if ck not in st.session_state:
        from ui.stores import get_ui_translation_store
        st.session_state[ck] = get_ui_translation_store().build_lookup(lang)
    return st.session_state[ck]


def t(text: str, *, lang: str | None = None) -> str:
    """Translate *text* to the active UI language.

    Parameters
    ----------
    text : str
        The English source string (also used as the DB lookup key).
    lang : str | None
        Override the session language.  ``None`` → read ``SK.UI_LANG``.

    Returns
    -------
    str
        Translated string, or *text* when no translation is found or the
        active language is English.
    """
    if not text:
        return text
    active = lang if lang is not None else _active_lang()
    if active == "en":
        return text
    return _get_cache(active).get(text, text)


def clear_cache(lang: str | None = None) -> None:
    """Invalidate the translation cache so the next ``t()`` call re-reads the DB.

    Parameters
    ----------
    lang : str | None
        Clear cache for this language only.  ``None`` → clear all languages.
    """
    if lang is not None:
        st.session_state.pop(_cache_key(lang), None)
    else:
        for key in list(st.session_state.keys()):
            if key.startswith(_CACHE_PREFIX):
                del st.session_state[key]


def supported_langs() -> list[str]:
    """Return the list of non-English language codes the system knows about."""
    from po_extractor.store.ui_translation_store import _LANG_COL
    return list(_LANG_COL.keys())
