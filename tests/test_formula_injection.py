"""Text that arrives in the data must not become a live Excel formula.

A vendor controls the text in the PO PDFs we parse. openpyxl turns a string
starting with "=" into a formula, so that text lands as a formula in the
workbook a colleague opens. Only "=" does this -- "+", "-" and "@" are stored
as plain text whatever the usual spreadsheet-injection advice says, and
escaping those would corrupt legitimate values like "-" and "-1".
"""
from __future__ import annotations

import io

import openpyxl
import pytest

from po_extractor.exporters._excel_helpers import neutralise_foreign_formulas


def _roundtrip(wb):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return openpyxl.load_workbook(buf).active


def test_only_equals_makes_a_formula():
    """The premise. If openpyxl ever changes this, the helper below is wrong."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, v in enumerate(["=1+1", "+1+1", "-1+1", "@SUM(A1)", "-"], start=1):
        ws.cell(i, 1, v)
    got = _roundtrip(wb)
    assert got.cell(1, 1).data_type == "f"
    assert [got.cell(r, 1).data_type for r in (2, 3, 4, 5)] == ["s"] * 4


@pytest.mark.parametrize("payload", [
    "=cmd|'/c calc'!A1",
    "=1+1",
    "=HYPERLINK(\"http://evil\",\"click\")",
    "=IMPORTXML(\"http://evil\",\"//x\")",
])
def test_injected_text_is_stored_as_text(payload):
    wb = openpyxl.Workbook()
    wb.active.cell(1, 1, payload)
    assert neutralise_foreign_formulas(wb) == 1
    got = _roundtrip(wb)
    assert got.cell(1, 1).data_type == "s"
    assert got.cell(1, 1).value == payload      # characters kept, exactly


@pytest.mark.parametrize("formula", [
    "=SUM(B1:B9)",
    "=SUM(E2:E10,F2:F10)",
    "='Sheet 2'!A1",
    "='003_060 Wine'!G14",
])
def test_the_exporters_own_formulas_survive(formula):
    """These are the only two shapes this codebase writes. Neutralising them
    would blank every total in every buy plan."""
    wb = openpyxl.Workbook()
    wb.active.cell(1, 1, formula)
    assert neutralise_foreign_formulas(wb) == 0
    assert _roundtrip(wb).cell(1, 1).data_type == "f"


def test_plain_values_are_left_alone():
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, v in enumerate(["-1", "-", "+44 123", "@factory", 42, None], start=1):
        ws.cell(i, 1, v)
    assert neutralise_foreign_formulas(wb) == 0


def test_every_sheet_is_covered():
    wb = openpyxl.Workbook()
    wb.active.cell(1, 1, "=evil()")
    wb.create_sheet("second").cell(1, 1, "=alsoevil()")
    assert neutralise_foreign_formulas(wb) == 2


def test_a_real_buy_plan_export_defuses_injected_text(tmp_path):
    """End to end through an actual exporter, not just the helper."""
    from po_extractor.exporters.tracking_grid_xlsx import build_tracking_grid_xlsx
    records = [{"po_number": "=cmd|'/c calc'!A1", "style": "ST1",
                "factory": "F1"}]
    for stage in ("fabric_purchase", "cutting", "packing"):
        records[0][f"{stage}_planned"] = ""
        records[0][f"{stage}_actual"] = ""
    data = build_tracking_grid_xlsx(records)
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    hits = [c for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.startswith("=cmd")]
    assert hits, "the payload should still be present as text"
    assert all(c.data_type == "s" for c in hits)


# ── Markdown injection in the email inbox ───────────────────────────────────

def test_a_sender_cannot_inject_a_link_or_beacon_into_the_inbox():
    """Filenames and summaries are written by whoever sent the mail. Rendered
    as Markdown, a link works and an image is fetched from inside the network
    the moment the inbox is opened."""
    from ui.email_view import _md_escape
    for payload in ["[invoice](http://evil)",
                    "![x](http://evil/beacon.png)",
                    "**not really bold**"]:
        out = _md_escape(payload)
        assert "](" not in out
        assert out != payload
    # A plain filename survives readably (escapes are invisible once rendered).
    assert _md_escape("PO_2360361C.pdf").replace("\\", "") == "PO_2360361C.pdf"
    assert _md_escape(None) == ""
