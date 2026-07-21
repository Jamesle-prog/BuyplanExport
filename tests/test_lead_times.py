"""Tests for the milestone lead-time planner (🏭 Tracking auto-plan).

The whole point of this module is that a merchandiser types ONE date and
gets nine. Both directions must read the same offsets table so a backward
plan (from 离厂时间) and a forward plan (from a start date) can never
disagree about the same order.
"""
from __future__ import annotations

from datetime import date

import pytest

from po_extractor.utils.lead_times import (
    DEFAULT_LEAD_DAYS,
    cycle_length,
    normalise_lead_days,
    plan_backward,
    plan_forward,
    shift_plan,
)
from po_extractor.store._factory_progress_schema import MILESTONE_STAGES


def test_defaults_cover_every_milestone():
    assert set(DEFAULT_LEAD_DAYS) == {s for s, _ in MILESTONE_STAGES}


def test_backward_plan_counts_back_from_ex_factory():
    plan = plan_backward(date(2026, 9, 20), DEFAULT_LEAD_DAYS)
    assert plan["shipping"] == "2026-09-20"          # anchor itself (offset 0)
    assert plan["cutting"] == "2026-08-31"           # 20 days before
    assert plan["fabric_purchase"] == "2026-08-06"   # 45 days before


def test_forward_plan_lands_on_the_same_ex_factory_date():
    """Forward and backward must agree: a forward plan from `start` implies
    ex-factory = start + cycle, and re-planning backward from that date must
    reproduce the identical schedule."""
    start = date(2026, 8, 6)
    fwd = plan_forward(start, DEFAULT_LEAD_DAYS)
    implied_exfty = date.fromisoformat(fwd["shipping"])
    assert implied_exfty == start + __import__("datetime").timedelta(
        days=cycle_length(DEFAULT_LEAD_DAYS)
    )
    assert plan_backward(implied_exfty, DEFAULT_LEAD_DAYS) == fwd


def test_plans_cover_every_milestone():
    for plan in (plan_backward(date(2026, 9, 20), DEFAULT_LEAD_DAYS),
                 plan_forward(date(2026, 8, 1), DEFAULT_LEAD_DAYS)):
        assert set(plan) == {s for s, _ in MILESTONE_STAGES}
        assert all(isinstance(v, str) and len(v) == 10 for v in plan.values())


def test_custom_offsets_are_honoured():
    custom = dict(DEFAULT_LEAD_DAYS, cutting=30)
    plan = plan_backward(date(2026, 9, 20), custom)
    assert plan["cutting"] == "2026-08-21"


# ── normalise_lead_days: a partial/corrupt setting must never half-fill ────

def test_normalise_fills_gaps_and_drops_unknown_keys():
    out = normalise_lead_days({"cutting": 33, "bogus_stage": 5})
    assert out["cutting"] == 33
    assert set(out) == {s for s, _ in MILESTONE_STAGES}
    assert "bogus_stage" not in out
    assert out["fabric_purchase"] == DEFAULT_LEAD_DAYS["fabric_purchase"]


@pytest.mark.parametrize("bad", ["abc", None, -5])
def test_normalise_survives_bad_values(bad):
    out = normalise_lead_days({"cutting": bad})
    assert out["cutting"] >= 0


def test_normalise_of_nothing_is_the_defaults():
    assert normalise_lead_days(None) == DEFAULT_LEAD_DAYS
    assert normalise_lead_days({}) == DEFAULT_LEAD_DAYS


# ── shift_plan ─────────────────────────────────────────────────────────────

def test_shift_moves_dates_both_ways_and_keeps_blanks_blank():
    plan = {"cutting": "2026-08-31", "sewing": "", "packing": "2026-09-15"}
    later = shift_plan(plan, 7)
    assert later == {"cutting": "2026-09-07", "sewing": "", "packing": "2026-09-22"}
    assert shift_plan(later, -7) == plan


def test_shift_leaves_unparseable_values_untouched():
    assert shift_plan({"cutting": "not a date"}, 5) == {"cutting": "not a date"}


# ── settings round-trip (uses a real AppSettingsStore on a temp DB) ────────

def test_lead_days_round_trip_through_settings(tmp_path):
    from po_extractor.store.app_settings_store import AppSettingsStore
    from po_extractor.utils.lead_times import load_lead_days, save_lead_days

    store = AppSettingsStore(str(tmp_path / "settings.db"))
    assert load_lead_days(store) == DEFAULT_LEAD_DAYS      # nothing saved yet

    save_lead_days(dict(DEFAULT_LEAD_DAYS, cutting=27), store)
    assert load_lead_days(store)["cutting"] == 27

    store.set("tracking_lead_days", "{not json")           # corrupt → defaults
    assert load_lead_days(store) == DEFAULT_LEAD_DAYS


# ── parse_anchor_date: ex-factory dates arrive in each client's own format ──

def test_parse_anchor_date_handles_every_client_format():
    from po_extractor.utils.lead_times import parse_anchor_date
    assert parse_anchor_date("2026-07-30") == date(2026, 7, 30)   # Sky East / ISO
    assert parse_anchor_date("7/30/2026") == date(2026, 7, 30)    # GIII / US
    assert parse_anchor_date("30.07.2026") == date(2026, 7, 30)
    assert parse_anchor_date("2026/07/30") == date(2026, 7, 30)
    assert parse_anchor_date(date(2026, 7, 30)) == date(2026, 7, 30)


@pytest.mark.parametrize("bad", ["", None, "   ", "not a date", "2026-13-45"])
def test_parse_anchor_date_returns_none_for_unusable(bad):
    from po_extractor.utils.lead_times import parse_anchor_date
    assert parse_anchor_date(bad) is None


def test_backward_plan_from_a_us_format_anchor():
    """The GIII path end to end: a '7/30/2026' factory_ship_date must give
    the same plan as the ISO equivalent."""
    from po_extractor.utils.lead_times import parse_anchor_date
    us = plan_backward(parse_anchor_date("7/30/2026"), DEFAULT_LEAD_DAYS)
    iso = plan_backward(date(2026, 7, 30), DEFAULT_LEAD_DAYS)
    assert us == iso
    assert us["fabric_purchase"] == "2026-06-15"
