"""Guard the i18n rule: every user-facing widget label goes through ``t()``.

CLAUDE.md says all user-facing text is translated, and the Chinese UI is only
as good as that rule's coverage.  It had drifted to 226 English-only labels
before v2.132.0 — a Master PO View that was half English under the 中文
toggle.  Rather than trusting review, this module asserts the invariant
mechanically, the same way ``test_log_html_escaping`` does for escaping:
**a Streamlit widget call may not receive an English string literal (or an
f-string with English literal parts) as its label.**

What counts as translated: ``t(...)``, ``_t(...)``, ``_th(...)``, or an
f-string whose placeholders include one of those calls.  Emoji-only,
Chinese-only and file-extension-only literals are not text and are ignored.
"""
from __future__ import annotations

import ast
import io
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Streamlit calls whose first positional argument (or ``label=``) is shown to
# the user.  Any attribute call with one of these names is checked, so
# ``col.button(...)`` on a column object counts as well as ``st.button(...)``.
WIDGETS = {
    "button", "subheader", "header", "title", "info", "warning", "error",
    "success", "caption", "text_input", "selectbox", "multiselect",
    "checkbox", "expander", "radio", "number_input", "text_area", "toggle",
    "download_button", "file_uploader", "metric", "popover",
    "form_submit_button", "date_input", "link_button", "segmented_control",
    "pills", "color_picker", "slider", "select_slider",
}

# Files that are allowed English literals.
SKIP = {
    "ui/changelog_view.py",     # release notes are authored English prose
}

# Free-text calls: the first argument is prose when it is a string literal.
PROSE_CALLS = {"markdown", "write"}

# Keyword arguments that are shown to the user.  ``placeholder`` is only
# checked when it reads as a prompt ("Select…", "Choose…") — most placeholders
# are example values ("e.g. MQ-BD181446", "you@example.com") and those must
# stay in the form the user is expected to type.
TEXT_KWARGS = {"help", "placeholder"}
_PROMPT = re.compile(r"^(Select|Choose|Enter|Type|Pick|Search)\b")

TRANSLATORS = {"t", "_t", "_th"}
_ASCII_WORD = re.compile(r"[A-Za-z]{2,}")
_EXT_HINT = re.compile(r"\(\.\w+\)")      # "(.xlsx)" is a file type, not text
_VALUE_LIKE = re.compile(r"e\.g\.|@|://|\\|^&nbsp;$|^[A-Z]{4}-[A-Z]{2}-[A-Z]{2}$")


# PO, PC, SKU, GSM, CM, HHN, PDF… — Latin-letter lookarounds rather than \b,
# because CJK characters count as \w and "克重GSM" has no word boundary.
_ABBREV = re.compile(r"(?<![A-Za-z])[A-Z]{2,4}(?![A-Za-z])")


def _is_text(text: str) -> bool:
    """True when a literal is prose a user reads, not a value or markup.

    Not text: HTML/CSS, example values, paths, ``&nbsp;``, date formats,
    documentation blocks carrying code fences, and strings whose only Latin
    content is unit/ID abbreviations (``克重GSM``, ``PO `{po}```).
    """
    s = text.strip()
    if not s or s.startswith("<") or "```" in s or _VALUE_LIKE.search(s):
        return False
    return bool(_ASCII_WORD.search(_ABBREV.sub("", _EXT_HINT.sub("", s))))


def _label_arg(call: ast.Call):
    for kw in call.keywords:
        if kw.arg == "label":
            return kw.value
    return call.args[0] if call.args else None


def _literal_text(node) -> str | None:
    """English text of a str literal / f-string's literal parts, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        for part in node.values:
            if isinstance(part, ast.FormattedValue):
                v = part.value
                if (isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                        and v.func.id in TRANSLATORS):
                    return None          # f"{t('…')} …" — translated
        return "".join(p.value for p in node.values
                       if isinstance(p, ast.Constant) and isinstance(p.value, str))
    return None


def untranslated_labels(path: Path) -> list[tuple[int, str, str]]:
    """[(lineno, where, text)] for English literals a user would read.

    Covers widget labels, ``help=`` / prompt-style ``placeholder=`` keywords on
    any call, and the first argument of ``st.markdown`` / ``st.write``.
    """
    tree = ast.parse(io.open(path, encoding="utf-8-sig").read())
    out: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name = node.func.attr
        # Keyword text on any call (column_config.TextColumn(help=…) included).
        for kw in node.keywords:
            if kw.arg in TEXT_KWARGS:
                text = _literal_text(kw.value)
                if text is None or not _is_text(text):
                    continue
                if kw.arg == "placeholder" and not _PROMPT.match(text.strip()):
                    continue
                out.append((node.lineno, f"{name}({kw.arg}=)", text.strip()))
        if name in WIDGETS:
            label = _label_arg(node)
        elif name in PROSE_CALLS and node.args:
            label = node.args[0]
        else:
            continue
        if label is None:
            continue
        text = _literal_text(label)
        if text is None or not _is_text(text):
            continue
        out.append((node.lineno, name, text.strip()))
    return out


def _ui_files() -> list[Path]:
    files = [p for p in (REPO / "ui").rglob("*.py") if "__pycache__" not in p.parts]
    files.append(REPO / "app.py")
    return sorted(p for p in files if p.relative_to(REPO).as_posix() not in SKIP)


@pytest.mark.parametrize("path", _ui_files(), ids=lambda p: p.relative_to(REPO).as_posix())
def test_widget_labels_are_translated(path: Path):
    bad = untranslated_labels(path)
    assert not bad, (
        f"{path.relative_to(REPO).as_posix()}: {len(bad)} widget label(s) bypass t() "
        f"— wrap each in t(...) and seed its Chinese in ui_translation_store._SEED: "
        + "; ".join(f"line {ln} {w}: {txt[:60]!r}" for ln, w, txt in bad[:8])
    )


def test_detector_catches_a_planted_violation(tmp_path):
    """The guard must actually fail on an English literal, not pass vacuously."""
    bad = tmp_path / "bad_view.py"
    bad.write_text(
        "import streamlit as st\n"
        "st.button('Download report')\n"
        "st.caption(f'{n} row(s) found')\n"
        "c = st.columns(2)\n"
        "c[0].button(label='Save')\n"
        "st.text_input(t('Name'), help='Shown on the report')\n"
        "st.multiselect(t('PCs'), opts, placeholder='Select one or more PC Nos...')\n"
        "st.markdown('**Delete POs from history**')\n"
        "st.write('Generating buy plan Excel…')\n",
        encoding="utf-8",
    )
    found = untranslated_labels(bad)
    assert [ln for ln, _w, _t in found] == [2, 3, 5, 6, 7, 8, 9]

    good = tmp_path / "good_view.py"
    good.write_text(
        "import streamlit as st\n"
        "from ui.i18n import t\n"
        "st.button(t('Download report'))\n"
        "st.caption(t('{n} row(s) found').format(n=3))\n"
        "st.caption(f\"{t('Rows')}: {n}\")\n"
        "st.button('📥')\n"                    # emoji only
        "st.caption('克重')\n"                 # Chinese only, no English words
        "st.download_button(f'{label} (.xlsx)')\n"   # extension hint only
        "st.text_input('x', key='only_key')\n"        # single letter, not a word
        "st.text_input(t('Email'), placeholder='you@example.com')\n"   # example value
        "st.text_input(t('Path'), placeholder=r'D:\\CutPlans\\2026')\n"  # example value
        "st.text_input(t('Code'), placeholder='e.g. MQ-BD181446')\n"   # example value
        "st.column_config.TextColumn(t('Date'), help='YYYY-MM-DD')\n"  # a format, not prose
        "st.markdown('<style>.x{color:red}</style>', unsafe_allow_html=True)\n"
        "st.markdown(f'**{label}**')\n"        # variable only, no literal words
        "st.markdown('&nbsp;')\n",
        encoding="utf-8",
    )
    assert untranslated_labels(good) == []


def test_every_translated_key_has_a_chinese_seed_or_is_placeholder_free():
    """Keys introduced by the sweep must be seeded; otherwise 中文 shows English.

    Only keys containing a ``{placeholder}`` are checked strictly — those were
    all introduced by the sweep and are the ones most likely to be forgotten
    because they never existed as plain strings before.
    """
    from po_extractor.store.ui_translation_store import _SEED

    seeded = {row[0] for row in _SEED}
    missing: list[str] = []
    for path in _ui_files():
        tree = ast.parse(io.open(path, encoding="utf-8-sig").read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in TRANSLATORS and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                key = node.args[0].value
                if "{" in key and key not in seeded:
                    missing.append(f"{path.relative_to(REPO).as_posix()}: {key[:70]!r}")
    assert not missing, "placeholder keys without a Chinese seed:\n  " + "\n  ".join(missing[:20])
