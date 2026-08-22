"""Design-system guards: one source for each colour, one log-line component.

The audit that led to these found the app defining ``.badge-ok`` / ``.badge-err``
in ``app.py`` while fourteen log lines across four files hand-wrote their own
``style="color:#dc3545"`` — and Streamlit's widgets in the default red while
the login page was Threadline pink.  These tests keep both from drifting back.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from ui.log_markup import LOG_KINDS, badge, err, ok, warn

REPO = Path(__file__).resolve().parent.parent
UI_FILES = [p for p in (REPO / "ui").rglob("*.py") if "__pycache__" not in p.parts]


# ── The component ───────────────────────────────────────────────────────────

def test_badge_emits_a_class_never_an_inline_colour():
    out = badge("ok", "PO-1.pdf")
    assert out == '<span class="badge-ok">✅ PO-1.pdf</span>'
    assert "style=" not in out and "#" not in out


@pytest.mark.parametrize("kind,glyph", [("ok", "✅"), ("warn", "⚠️"), ("err", "❌")])
def test_each_kind_has_one_class_and_one_glyph(kind, glyph):
    out = badge(kind, "x")
    assert f'class="badge-{kind}"' in out
    assert glyph in out


def test_glyph_can_be_suppressed_when_the_caller_supplies_one():
    assert badge("ok", "🔁 PO-1.pdf", glyph=False) == '<span class="badge-ok">🔁 PO-1.pdf</span>'


def test_badge_does_not_escape_by_default_so_trusted_markup_survives():
    assert "<b>PC1</b>" in badge("ok", "file -> PC <b>PC1</b>")


def test_badge_escapes_on_request():
    hostile = '<img src=x onerror="alert(1)">'
    out = badge("err", hostile, escape=True)
    assert "<img" not in out and "&lt;img" in out


def test_unknown_kind_is_an_error_not_a_silent_default():
    with pytest.raises(ValueError):
        badge("info", "x")


def test_shorthands_match_badge():
    assert ok("a") == badge("ok", "a")
    assert warn("a") == badge("warn", "a")
    assert err("a") == badge("err", "a")


# ── No producer writes a colour by hand ─────────────────────────────────────

def test_no_ui_module_writes_an_inline_log_colour():
    offenders = []
    for p in UI_FILES:
        if p.name == "log_markup.py":
            continue                       # its docstring describes the old state
        src = io.open(p, encoding="utf-8-sig").read()
        for m in re.finditer(r'style="color:#[0-9a-fA-F]{6}"', src):
            offenders.append(f"{p.relative_to(REPO).as_posix()}: {m.group(0)}")
    assert not offenders, "inline log colours — use ui.log_markup.badge():\n  " + "\n  ".join(offenders)


def test_every_badge_kind_has_css_in_both_themes():
    """The classes badge() emits must exist, and each must be re-coloured for
    dark mode — light-mode amber on a dark page was the original complaint."""
    css = io.open(REPO / "app.py", encoding="utf-8-sig").read()
    for kind in LOG_KINDS:
        assert f".badge-{kind}" in css, f".badge-{kind} is not styled"
        assert f"--tl-{kind}:" in css, f"--tl-{kind} token missing"
    dark = css.split("@media (prefers-color-scheme: dark)", 1)[1]
    for kind in LOG_KINDS:
        assert f"--tl-{kind}:" in dark, f"--tl-{kind} has no dark-mode value"


# ── One primary colour ──────────────────────────────────────────────────────

def _hex(s: str) -> str:
    return s.strip().lower()


def test_streamlit_primary_colour_equals_the_brand_token():
    """Widgets (config.toml) and hand-drawn UI (app.py) must agree."""
    cfg = io.open(REPO / ".streamlit" / "config.toml", encoding="utf-8").read()
    m = re.search(r'primaryColor\s*=\s*"(#[0-9a-fA-F]{6})"', cfg)
    assert m, "primaryColor missing from .streamlit/config.toml"
    css = io.open(REPO / "app.py", encoding="utf-8-sig").read()
    t = re.search(r"--tl-brand:\s*(#[0-9a-fA-F]{6})", css)
    assert t, "--tl-brand token missing from app.py"
    assert _hex(m.group(1)) == _hex(t.group(1))


def test_brand_colour_is_written_once_in_app_css():
    """Every other use must read the token, not repeat the hex."""
    css = io.open(REPO / "app.py", encoding="utf-8-sig").read()
    brand = re.search(r"--tl-brand:\s*(#[0-9a-fA-F]{6})", css).group(1)
    assert css.lower().count(brand.lower()) == 1
    assert "#ff4b4b" not in css.lower(), "Streamlit's default red must not be hard-coded"


# ── One width API ───────────────────────────────────────────────────────────

def test_no_deprecated_use_container_width():
    """Streamlit replaced ``use_container_width=`` with ``width="stretch"`` /
    ``"content"``; the codebase had 177 of the old form next to 60 of the new.
    One API, or the next Streamlit release breaks half the buttons."""
    offenders = []
    for p in UI_FILES + [REPO / "app.py"]:
        if p.name == "changelog_view.py":
            continue                       # release notes mention the old name
        src = io.open(p, encoding="utf-8-sig").read()
        for i, line in enumerate(src.splitlines(), 1):
            if "use_container_width" in line:
                offenders.append(f"{p.relative_to(REPO).as_posix()}:{i}")
    assert not offenders, "use width=\"stretch\" / \"content\":\n  " + "\n  ".join(offenders)


# ── Session-state keys go through SK ────────────────────────────────────────

def _literal_session_keys(path: Path) -> list[tuple[int, str]]:
    """(lineno, key) for every session_state access that spells its key as a
    string literal or attribute instead of an SK constant."""
    import ast
    tree = ast.parse(io.open(path, encoding="utf-8-sig").read())
    out: list[tuple[int, str]] = []
    methods = ("get", "pop", "setdefault")
    for n in ast.walk(tree):
        if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute)
                and n.value.attr == "session_state"
                and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str)):
            out.append((n.lineno, n.slice.value))
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in methods
                and isinstance(n.func.value, ast.Attribute)
                and n.func.value.attr == "session_state"
                and n.args and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            out.append((n.lineno, n.args[0].value))
        if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute)
                and n.value.attr == "session_state"
                and n.attr not in methods + ("update", "keys", "items", "values", "clear", "to_dict")):
            out.append((n.lineno, n.attr))
        if (isinstance(n, ast.Compare) and isinstance(n.left, ast.Constant)
                and isinstance(n.left.value, str) and len(n.comparators) == 1
                and isinstance(n.comparators[0], ast.Attribute)
                and n.comparators[0].attr == "session_state"):
            out.append((n.lineno, n.left.value))
    return out


@pytest.mark.parametrize("path", [p for p in UI_FILES if p.name != "session_keys.py"] + [REPO / "app.py"],
                         ids=lambda p: p.relative_to(REPO).as_posix())
def test_session_state_keys_are_sk_constants(path: Path):
    """CLAUDE.md: session state uses SK constants, never raw literals.  The
    sweep that introduced this found 152 literal accesses across 24 files."""
    bad = _literal_session_keys(path)
    assert not bad, (
        "add a constant to ui/session_keys.py and use SK.<NAME>:\n  "
        + "\n  ".join(f"line {ln}: {key!r}" for ln, key in bad[:10])
    )


def test_session_key_detector_catches_every_form(tmp_path):
    f = tmp_path / "v.py"
    f.write_text(
        "import streamlit as st\n"
        "st.session_state['a'] = 1\n"          # subscript
        "st.session_state.get('b')\n"          # get
        "st.session_state.pop('c', None)\n"    # pop
        "x = st.session_state.d\n"             # attribute
        "if 'e' in st.session_state: pass\n"   # membership
        "st.session_state[SK.F] = 1\n"         # fine
        "st.session_state.get(SK.G)\n"         # fine
        "st.session_state.update({})\n",       # method, fine
        encoding="utf-8",
    )
    assert [k for _, k in _literal_session_keys(f)] == ["a", "b", "c", "d", "e"]
