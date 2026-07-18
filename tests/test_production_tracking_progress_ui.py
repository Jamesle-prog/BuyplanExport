"""Tests for the pure status/filter helpers behind the Tracking tab's
Dashboard/Overview (Stage 7) — _is_delayed, _is_blocked, _is_at_risk,
_status_badges, _group_b_stages_for. These are the single source of truth
the Dashboard cards, Overview table, and Edit form all read from, so a bug
here would make the three views silently disagree about a record's state.
"""
from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.production_tracking_view as v


def _record(**overrides) -> dict:
    base = {"po_number": "PO1", "style": "STY1", "company": "GIII", "factory": "F1"}
    base.update(overrides)
    return base


def test_is_delayed_true_when_any_applicable_stage_delayed():
    assert v._is_delayed(_record(cutting_status="Delayed")) is True
    assert v._is_delayed(_record(cutting_status="In Progress")) is False


def test_is_delayed_ignores_inapplicable_optional_sample():
    rec = _record(proto_sample_status="Delayed", proto_sample_applicable=0)
    assert v._is_delayed(rec) is False
    rec2 = _record(proto_sample_status="Delayed", proto_sample_applicable=1)
    assert v._is_delayed(rec2) is True


def test_is_blocked_reads_readiness_waiting_prefix():
    assert v._is_blocked({"pp_sample": "waiting:Trim Purchase", "cutting": "ready"}) is True
    assert v._is_blocked({"pp_sample": "ready", "cutting": "ready"}) is False
    assert v._is_blocked({"pp_sample": "no_prereqs", "cutting": "no_prereqs"}) is False


def test_is_at_risk_true_if_either_delayed_or_blocked():
    delayed = _record(cutting_status="Delayed")
    assert v._is_at_risk(delayed, {"pp_sample": "ready", "cutting": "ready"}) is True

    on_track = _record()
    assert v._is_at_risk(on_track, {"pp_sample": "waiting:X", "cutting": "ready"}) is True
    assert v._is_at_risk(on_track, {"pp_sample": "ready", "cutting": "ready"}) is False


def test_status_badges_priority_and_on_track_fallback():
    readiness_ready = {"pp_sample": "ready", "cutting": "ready"}

    # Nothing wrong -> On Track only.
    badges = v._status_badges(_record(), readiness_ready, [])
    assert any("On Track" in b or "进度正常" in b for b in badges)

    # Delayed takes priority and still appears alongside a QC reminder.
    rec = _record(cutting_status="Delayed")
    reminders = [{"key": "insp_final", "label": "Final Inspection",
                  "deadline": None, "overdue": True}]
    badges = v._status_badges(rec, readiness_ready, reminders)
    assert any("Delayed" in b or "延误" in b for b in badges)
    assert any("QC" in b for b in badges)
    assert not any("On Track" in b or "进度正常" in b for b in badges)


def test_group_b_stages_for_includes_pp_sample_plus_applicable_optionals():
    rec = _record(proto_sample_applicable=1, fit_sample_applicable=0)
    stages = v._group_b_stages_for(rec)
    assert "pp_sample" in stages
    assert "proto_sample" in stages
    assert "fit_sample" not in stages


def test_all_companies_and_factories_dedupe_and_sort():
    records = [
        {"company": "GIII", "factory": "F2"},
        {"company": "Sky East", "factory": "F1"},
        {"company": "GIII", "factory": "F1"},
        {"company": "", "factory": ""},
    ]
    assert v._all_companies(records) == ["GIII", "Sky East"]
    assert v._all_factories(records) == ["F1", "F2"]
