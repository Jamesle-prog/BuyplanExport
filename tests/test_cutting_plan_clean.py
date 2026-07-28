"""Cut-plan house cleanup — port of the hand-run Excel macro.

Pins the macro's behaviour, including the parts that look odd but are
deliberate (substring matching, rule order), so a later "tidy-up" can't
silently change what the cutting room reads.
"""
from __future__ import annotations

import io

import openpyxl
import pytest

from po_extractor.exporters.cutting_plan_clean import (
    clean_value, clean_workbook, strip_path_and_ext, translate_text,
)


# ── translate ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("src,want", [
    ("Plies number", "层数"),
    ("Colors", "颜色"),
    ("Marker Ratio", "裁剪配比"),
    ("Marker", "版"),
    ("Fabric Length", "面料长度"),
    ("Fabric Weight", "面料重量"),
    ("Order", "订单数"),
    ("Real", "裁剪数"),
])
def test_exact_labels(src, want):
    assert translate_text(src) == want


def test_specific_marker_rules_win_over_the_bare_one():
    """'Marker Length'/'Marker Ratio' must be replaced before plain 'Marker'.

    If the short rule ran first these would come out as '版 Length' / '版 Ratio'
    — the macro's rule order exists precisely to prevent that.
    """
    assert translate_text("Marker Length") == "版长"
    assert translate_text("Marker Ratio") == "裁剪配比"
    # and with the unit suffix the exporter actually writes
    assert translate_text("Marker Length,cm") == "版长,cm"


def test_substring_and_case_insensitive():
    """LookAt:=xlPart + MatchCase:=False — matches inside words, any case."""
    assert translate_text("N Markers") == "N 版s"
    assert translate_text("Order demands") == "订单数 demands"
    assert translate_text("MARKER") == "版"
    assert translate_text("colors") == "颜色"


def test_untouched_labels_pass_through():
    for s in ["Material", "Solution", "Spreading Plies", "Total Efficiency",
              "Min Plies", "Client", "Date", "Sum"]:
        assert translate_text(s) == s


def test_replacements_do_not_cascade():
    """Every replacement is Chinese and every search term ASCII, so no rule
    can re-match an earlier rule's output."""
    assert translate_text("Marker Length") == "版长"
    assert translate_text(translate_text("Marker Length")) == "版长"


# ── path / extension ─────────────────────────────────────────────────────────

def test_strips_windows_path_and_mrk():
    assert strip_path_and_ext(r"D:\Markers\SS26\ABC-1234.mrk") == "ABC-1234"


def test_strips_path_without_extension():
    assert strip_path_and_ext(r"D:\Markers\SS26\ABC-1234") == "ABC-1234"


def test_strips_extension_without_path():
    assert strip_path_and_ext("ABC-1234.mrk") == "ABC-1234"


def test_extension_check_is_case_insensitive():
    """The macro's Right()= comparison missed .MRK; this does not."""
    assert strip_path_and_ext("ABC.MRK") == "ABC"


def test_plain_text_untouched():
    assert strip_path_and_ext("ABC-1234") == "ABC-1234"
    assert strip_path_and_ext("") == ""


def test_only_last_backslash_segment_kept():
    assert strip_path_and_ext(r"\\server\share\deep\path\M1.mrk") == "M1"


# ── cell-level ───────────────────────────────────────────────────────────────

def test_non_text_values_pass_through():
    for v in (None, 12, 30.5, True):
        assert clean_value(v) is v


def test_formulas_are_never_rewritten():
    assert clean_value("=SUM(A1:A9)") == "=SUM(A1:A9)"


def test_translate_then_strip_on_one_cell():
    assert clean_value(r"D:\Markers\SS26\ABC.mrk") == "ABC"


# ── workbook pass ────────────────────────────────────────────────────────────

def test_clean_workbook_reports_and_applies():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "Marker Ratio"
    ws["A2"] = r"D:\Markers\M1.mrk"
    ws["A3"] = "Material"          # unchanged
    ws["A4"] = 42                  # untouched non-text
    changed = clean_workbook(wb)
    assert ws["A1"].value == "裁剪配比"
    assert ws["A2"].value == "M1"
    assert ws["A3"].value == "Material"
    assert ws["A4"].value == 42
    assert changed == 2


# ── integration with the exporter ────────────────────────────────────────────

def _build(clean: bool) -> list[str]:
    from po_extractor.exporters.cutting_plan_export import build_standard_cut_plan
    data = build_standard_cut_plan(
        header={"order_name": "PO-99", "client": "GIII", "operator": "LI",
                "output_folder": r"D:\Markers\SS26",
                "styles": [{"name": "ST1", "file": r"D:\Styles\ST1.sty"}]},
        groups=[("ST1", ["S", "M"])],
        colors=["NAVY"],
        demand_qty={("ST1", "NAVY", "S"): 10, ("ST1", "NAVY", "M"): 20},
        materials=[{
            "material": "Twill",
            "markers": [{"marker_no": 1,
                         "file_name": r"D:\Markers\SS26\ABC-1234.mrk",
                         "ratio": [{"style": "ST1", "size": "S", "qty": 1}]}],
            "spreads": [{"marker_no": 1,
                         "file_name": r"D:\Markers\SS26\ABC-1234.mrk",
                         "rows": []}],
        }],
        clean=clean,
    )
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    return [str(c.value) for r in ws.iter_rows() for c in r
            if isinstance(c.value, str)]


def test_export_cleaned_when_requested():
    vals = _build(clean=True)
    assert "颜色" in vals and "裁剪配比" in vals and "层数" in vals
    assert "ABC-1234" in vals                       # marker path reduced
    assert not any(".mrk" in v for v in vals)
    assert not any(v == "Marker Ratio" for v in vals)


def test_export_default_stays_english_and_reparseable():
    """The canonical layout must stay English — the parser finds its blocks by
    English anchor text and the app round-trips its own export."""
    vals = _build(clean=False)
    assert "Colors" in vals and "Marker Ratio" in vals
    assert any(".mrk" in v for v in vals)           # raw path retained
    assert not any("颜色" == v for v in vals)
