"""Regression test for ui/fabric_db/browse.py (Fix 6).

weight_gsm / cuttable_width_cm of 0 is a real (if unusual) value and must
render as "0", not "—" — the bug was a truthiness check (`if rec.get(...)`)
that treated 0 the same as missing/None.
"""
from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.fabric_db.browse as browse


class _FakeMetric:
    """Captures the values passed to st.columns(...)[i].metric(...)."""

    def __init__(self, sink: list):
        self._sink = sink

    def metric(self, label, value=None, *a, **k):
        self._sink.append((label, value))


def _run_detail_card(monkeypatch, rec: dict) -> dict:
    """Call _fabric_db_detail_card with a fake store/text_input and capture
    every metric label -> displayed value."""
    metrics: list = []

    class _FakeStore:
        def get_by_quality_no(self, qno):
            return rec

    monkeypatch.setattr(browse.st, "text_input", lambda *a, **k: "Q1")
    monkeypatch.setattr(browse.st, "columns", lambda n: [_FakeMetric(metrics) for _ in range(n)])
    monkeypatch.setattr(browse.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(browse.st, "divider", lambda *a, **k: None)
    monkeypatch.setattr(browse.st, "dataframe", lambda *a, **k: None)

    class _NoopExpander:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(browse.st, "expander", lambda *a, **k: _NoopExpander())

    browse._fabric_db_detail_card(_FakeStore())
    return dict(metrics)


def test_zero_weight_and_width_display_as_zero_not_dash(monkeypatch):
    rec = {
        "composition_en": "100% Cotton",
        "weight_gsm": 0,
        "cuttable_width_cm": 0,
        "shrinkage_rate": 1.5,
        "short_rate": 0.5,
        "notes_cn": "",
        "display_key": "K1",
    }
    values = _run_detail_card(monkeypatch, rec)
    assert values["克重 GSM"] == "0"
    assert values["有效门幅 CM"] == "0"


def test_missing_weight_and_width_still_display_as_dash(monkeypatch):
    rec = {
        "composition_en": "100% Cotton",
        "weight_gsm": None,
        "cuttable_width_cm": None,
        "shrinkage_rate": None,
        "short_rate": None,
        "notes_cn": "",
        "display_key": "K1",
    }
    values = _run_detail_card(monkeypatch, rec)
    assert values["克重 GSM"] == "—"
    assert values["有效门幅 CM"] == "—"
