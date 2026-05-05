"""Regression tests for save-result formatting."""
from po_extractor.ui_helpers.save_log import format_save_results


def test_empty_results():
    out = format_save_results([])
    assert out.counts == {"new": 0, "duplicate": 0, "updated": 0, "skipped": 0}
    assert out.lines == []
    assert "0 new" in out.summary_plain
    assert out.skipped_po_numbers == []


def test_new_status():
    out = format_save_results([("PO1", "new", None)])
    assert out.counts["new"] == 1
    assert "saved to history" in out.lines[0].plain
    assert "<b>PO1</b>" in out.lines[0].html


def test_duplicate_status():
    out = format_save_results([("PO1", "duplicate", None)])
    assert out.counts["duplicate"] == 1
    assert "identical" in out.lines[0].plain.lower()


def test_updated_status_with_positive_delta():
    diff = {"old": {"version": 1, "total_units": 100},
            "new": {"version": 2, "total_units": 150}}
    out = format_save_results([("PO1", "updated", diff)])
    line = out.lines[0]
    assert out.counts["updated"] == 1
    assert "version 1 → 2" in line.plain
    assert "[+50]" in line.plain
    assert "(+50)" in line.html


def test_updated_status_with_negative_delta():
    diff = {"old": {"version": 2, "total_units": 200},
            "new": {"version": 3, "total_units": 150}}
    out = format_save_results([("PO1", "updated", diff)])
    assert "[-50]" in out.lines[0].plain
    assert "(-50)" in out.lines[0].html


def test_skipped_collected_for_exception_save():
    out = format_save_results([("", "skipped", None)])
    assert out.counts["skipped"] == 1
    assert out.skipped_po_numbers == [""]


def test_unknown_status_ignored():
    out = format_save_results([("PO1", "weird_status", None)])
    assert out.counts == {"new": 0, "duplicate": 0, "updated": 0, "skipped": 0}
    assert out.lines == []


def test_summary_aggregates_counts():
    diff = {"old": {"version": 1, "total_units": 10},
            "new": {"version": 2, "total_units": 12}}
    out = format_save_results([
        ("PO1", "new", None),
        ("PO2", "new", None),
        ("PO3", "duplicate", None),
        ("PO4", "updated", diff),
    ])
    assert "2 new" in out.summary_plain
    assert "1 updated" in out.summary_plain
    assert "1 duplicate" in out.summary_plain
