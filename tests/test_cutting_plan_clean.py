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
    build_color_map, build_reverse_color_map, clean_value, clean_workbook,
    find_color_conflicts, has_chinese, strip_path_and_ext, translate_text,
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


def test_cut_length_and_material_cost_labels():
    assert translate_text("Cut Length,m") == "裁剪长度,m"
    assert translate_text("Material Cost,CNY") == "材料成本,CNY"


def test_total_cut_length_is_not_half_translated():
    """'Total cut length' must be replaced before the 'Cut Length' rule, or it
    would come out as 'Total 裁剪长度'."""
    assert translate_text("Total cut length") == "总裁剪长度"


def test_bare_material_label_is_left_alone():
    """Only 'Material Cost' is mapped — the Marker Definition block's plain
    'Material' column holds the fabric name and must not be touched."""
    assert translate_text("Material") == "Material"


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


# ── colour translation from the PO colour data ───────────────────────────────

# Shape returned by ColorTranslationStore.build_lookup_dict().
_LOOKUP = {
    ("GIII", "DKNY", "Navy"): "藏青",
    ("GIII", "DKNY", "Clay"): "泥粉",
    ("Sky East", "Zalando", "Navy"): "深蓝",
    ("GIII", "DKNY", "Blank"): "",          # half-filled row
}


def test_build_color_map_flattens_and_normalises():
    m = build_color_map(_LOOKUP)
    assert m["navy"] in {"藏青", "深蓝"}
    assert m["clay"] == "泥粉"
    assert "blank" not in m                 # empty cn never mapped


def test_client_rows_win_over_other_clients():
    assert build_color_map(_LOOKUP, client="GIII")["navy"] == "藏青"
    assert build_color_map(_LOOKUP, client="Sky East")["navy"] == "深蓝"


def test_colour_cell_translated_case_insensitively():
    m = build_color_map(_LOOKUP, client="GIII")
    for src in ("NAVY", "navy", " Navy "):
        assert clean_value(src, m) == "藏青"


def test_colour_already_chinese_is_left_alone():
    m = build_color_map(_LOOKUP, client="GIII")
    assert clean_value("藏青", m) == "藏青"


def test_unknown_colour_falls_through_unchanged():
    m = build_color_map(_LOOKUP, client="GIII")
    assert clean_value("PUCE", m) == "PUCE"


def test_colour_match_is_whole_cell_only():
    """A substring rule here would corrupt any text containing a colour word."""
    m = build_color_map(_LOOKUP, client="GIII")
    assert clean_value("Navy Blazer 2pc", m) == "Navy Blazer 2pc"


def test_colour_mapping_does_not_disturb_labels():
    m = build_color_map(_LOOKUP, client="GIII")
    assert clean_value("Marker Ratio", m) == "裁剪配比"
    assert clean_value(r"D:\Markers\M1.mrk", m) == "M1"


def test_has_chinese():
    assert has_chinese("藏青") and not has_chinese("Navy")


# ── plan-vs-PO colour disagreement (report, don't rewrite) ───────────────────

def _wb_with(*values):
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, v in enumerate(values, start=1):
        ws.cell(i, 1, v)
    return wb


def test_reverse_map_recognises_each_clients_spelling():
    rev = build_reverse_color_map(_LOOKUP)
    assert rev["藏青"] == "navy" and rev["深蓝"] == "navy"
    assert rev["泥粉"] == "clay"


def test_conflict_reported_when_plan_uses_another_spelling():
    """Plan says 深蓝; for GIII the PO calls Navy 藏青 — flag it."""
    cmap = build_color_map(_LOOKUP, client="GIII")
    rev = build_reverse_color_map(_LOOKUP)
    got = find_color_conflicts(_wb_with("深蓝"), cmap, rev)
    assert len(got) == 1
    assert got[0]["plan_cn"] == "深蓝"
    assert got[0]["po_cn"] == "藏青"
    assert got[0]["english"] == "navy"


def test_no_conflict_when_names_agree():
    cmap = build_color_map(_LOOKUP, client="GIII")
    rev = build_reverse_color_map(_LOOKUP)
    assert find_color_conflicts(_wb_with("藏青"), cmap, rev) == []


def test_unknown_chinese_text_is_not_a_conflict():
    """Chinese that isn't a known colour (labels, notes) must never be flagged."""
    cmap = build_color_map(_LOOKUP, client="GIII")
    rev = build_reverse_color_map(_LOOKUP)
    assert find_color_conflicts(_wb_with("裁剪配比", "层数"), cmap, rev) == []


def test_conflicts_are_deduped():
    cmap = build_color_map(_LOOKUP, client="GIII")
    rev = build_reverse_color_map(_LOOKUP)
    assert len(find_color_conflicts(_wb_with("深蓝", "深蓝", "深蓝"),
                                    cmap, rev)) == 1


def test_detection_does_not_modify_the_workbook():
    """The whole point: reporting must leave the plan's own names in place."""
    cmap = build_color_map(_LOOKUP, client="GIII")
    rev = build_reverse_color_map(_LOOKUP)
    wb = _wb_with("深蓝")
    find_color_conflicts(wb, cmap, rev)
    assert wb.active["A1"].value == "深蓝"


def test_cleaning_alone_never_rewrites_a_chinese_colour():
    cmap = build_color_map(_LOOKUP, client="GIII")
    wb = _wb_with("深蓝")
    clean_workbook(wb, cmap)                    # no overrides approved
    assert wb.active["A1"].value == "深蓝"


def test_approved_override_rewrites_it():
    wb = _wb_with("深蓝")
    clean_workbook(wb, None, {"深蓝": "藏青"})
    assert wb.active["A1"].value == "藏青"


def test_cleaned_copy_leaves_the_source_bytes_untouched():
    """The PDF cleanup works on a throwaway copy — the stored workbook that
    the user can still download must be byte-identical afterwards."""
    from ui.cutting_plan._shared import _cleaned_copy
    wb = _wb_with("Marker Ratio", r"D:\Markers\M1.mrk")
    buf = io.BytesIO()
    wb.save(buf)
    original = buf.getvalue()

    cleaned = _cleaned_copy(original)
    assert original == buf.getvalue()          # source not mutated
    ws = openpyxl.load_workbook(io.BytesIO(cleaned)).active
    assert ws["A1"].value == "裁剪配比"
    assert ws["A2"].value == "M1"


def test_cleaned_copy_falls_back_to_the_original_on_failure():
    """A cleanup problem must cost the translation, never the PDF."""
    from ui.cutting_plan._shared import _cleaned_copy
    junk = b"not a workbook"
    assert _cleaned_copy(junk) is junk


def test_apply_color_overrides_round_trips_through_bytes():
    from po_extractor.exporters.cutting_plan_clean import apply_color_overrides
    wb = _wb_with("深蓝", "Material")
    buf = io.BytesIO()
    wb.save(buf)
    out = apply_color_overrides(buf.getvalue(), {"深蓝": "藏青"})
    ws = openpyxl.load_workbook(io.BytesIO(out)).active
    assert ws["A1"].value == "藏青"
    assert ws["A2"].value == "Material"         # untouched


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

def _build(clean: bool, color_map=None) -> list[str]:
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
        clean=clean, color_map=color_map,
    )
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    return [str(c.value) for r in ws.iter_rows() for c in r
            if isinstance(c.value, str)]


def test_export_cleaned_when_requested():
    vals = _build(clean=True)
    assert "颜色" in vals and "裁剪配比" in vals and "层数" in vals
    assert "裁剪长度,m" in vals and "材料成本,CNY" in vals
    assert "ABC-1234" in vals                       # marker path reduced
    assert not any(".mrk" in v for v in vals)
    assert not any(v == "Marker Ratio" for v in vals)


def test_export_translates_colours_from_the_po_data():
    """NAVY is a demand-block colour row; with the PO colour map it ships in
    Chinese, without one it stays as it was."""
    cmap = build_color_map(_LOOKUP, client="GIII")
    assert "藏青" in _build(clean=True, color_map=cmap)
    assert "NAVY" in _build(clean=True, color_map=None)


def test_export_default_stays_english_and_reparseable():
    """The canonical layout must stay English — the parser finds its blocks by
    English anchor text and the app round-trips its own export."""
    vals = _build(clean=False)
    assert "Colors" in vals and "Marker Ratio" in vals
    assert any(".mrk" in v for v in vals)           # raw path retained
    assert not any("颜色" == v for v in vals)
