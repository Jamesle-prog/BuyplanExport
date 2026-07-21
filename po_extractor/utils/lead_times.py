"""Lead-time planning for the milestone grid (🏭 Tracking).

Filling nine milestone dates per style by hand is the bulk of the work, so
the grid drafts them from ONE date the business already knows:

  * **backward** (倒推) — from the style's 离厂时间 / ex-factory date, which
    the client PO already carries
  * **forward**  (正推) — from a production start date

Both directions read the SAME offsets table, so they can never disagree.
Each milestone is stored as "days before ex-factory"; the cycle length is
the largest of those, so a forward plan is simply
``start + (cycle - days_before)`` and ex-factory itself lands on
``start + cycle``.

Everything here is pure (dates in, dates out) — no DB, no Streamlit — so
the arithmetic is unit-testable and the UI stays thin.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from ..store._factory_progress_schema import MILESTONE_STAGES

# Anchor dates arrive in whatever the client's file used: Sky East stores ISO,
# GIII's po_metadata keeps the US "7/30/2026" form. Same list the Sky East
# validator accepts, so one order file can't parse two different ways.
_ANCHOR_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y",
                        "%Y/%m/%d", "%d.%m.%Y")


def parse_anchor_date(raw) -> date | None:
    """Parse an ex-factory date from any client's stored format, or None.

    Ambiguous d/m vs m/d values resolve as the format list orders them —
    ISO first, then US (GIII's format), which is the only ambiguity that
    occurs in practice here.
    """
    if isinstance(raw, date):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in _ANCHOR_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None

# Days BEFORE the ex-factory date that each milestone should complete.
# Ordered earliest-first; shipping is the anchor itself (0). These are
# starting points a merchandiser is expected to tune per client/factory —
# see ``load_lead_days`` / ``save_lead_days``.
DEFAULT_LEAD_DAYS: dict[str, int] = {
    "fabric_purchase":    45,   # 面料到厂
    "trim_purchase":      40,   # 辅料到厂
    "pp_sample":          35,   # 样衣确认
    "base_size_pattern":  30,   # 大货版
    "full_sized_pattern": 25,   # 全码版
    "cutting":            20,   # 裁剪完成
    "sewing":             10,   # 车位完成
    "packing":             5,   # 后道完成
    "shipping":            0,   # 工厂交期 (the anchor)
}

# app_settings key holding the JSON offsets override.
KEY_LEAD_TIMES = "tracking_lead_days"


def normalise_lead_days(raw: dict | None) -> dict[str, int]:
    """Return a complete offsets dict: every MILESTONE_STAGE present, ints,
    never negative. Unknown keys are dropped and missing ones fall back to
    :data:`DEFAULT_LEAD_DAYS`, so a partial/edited setting can't produce a
    half-filled plan."""
    out: dict[str, int] = {}
    raw = raw or {}
    for stage, _label in MILESTONE_STAGES:
        try:
            val = int(raw.get(stage, DEFAULT_LEAD_DAYS.get(stage, 0)))
        except (TypeError, ValueError):
            val = DEFAULT_LEAD_DAYS.get(stage, 0)
        out[stage] = max(val, 0)
    return out


def load_lead_days(settings_store=None) -> dict[str, int]:
    """Offsets from app settings, falling back to the defaults. Never raises
    — a missing/corrupt setting simply yields the defaults."""
    try:
        if settings_store is None:
            from ..store import get_app_settings_store
            settings_store = get_app_settings_store()
        raw = settings_store.get(KEY_LEAD_TIMES, "") or ""
        return normalise_lead_days(json.loads(raw) if raw else None)
    except Exception:
        return normalise_lead_days(None)


def save_lead_days(days: dict[str, int], settings_store=None) -> None:
    """Persist the offsets table (normalised first)."""
    if settings_store is None:
        from ..store import get_app_settings_store
        settings_store = get_app_settings_store()
    settings_store.set(KEY_LEAD_TIMES, json.dumps(normalise_lead_days(days)))


def cycle_length(lead_days: dict[str, int]) -> int:
    """Total production cycle in days = the earliest milestone's offset."""
    return max(lead_days.values()) if lead_days else 0


def plan_backward(ex_factory: date, lead_days: dict[str, int]) -> dict[str, str]:
    """倒推 — milestone dates counted back from *ex_factory*.

    Returns ``{stage: 'YYYY-MM-DD'}`` for every milestone.
    """
    ld = normalise_lead_days(lead_days)
    return {
        stage: (ex_factory - timedelta(days=ld[stage])).isoformat()
        for stage, _ in MILESTONE_STAGES
    }


def plan_forward(start: date, lead_days: dict[str, int]) -> dict[str, str]:
    """正推 — milestone dates counted forward from a production *start*.

    Uses the same offsets as :func:`plan_backward`: the implied ex-factory
    date is ``start + cycle_length``, so both directions agree exactly.
    """
    ld = normalise_lead_days(lead_days)
    cycle = cycle_length(ld)
    return {
        stage: (start + timedelta(days=cycle - ld[stage])).isoformat()
        for stage, _ in MILESTONE_STAGES
    }


def shift_plan(planned: dict[str, str], days: int) -> dict[str, str]:
    """Move every non-empty date in *planned* by *days* (may be negative).

    Blank milestones stay blank — shifting must not invent a plan for a
    milestone that was never scheduled.
    """
    out: dict[str, str] = {}
    for stage, value in (planned or {}).items():
        text = (value or "").strip()
        if not text:
            out[stage] = ""
            continue
        try:
            out[stage] = (date.fromisoformat(text) + timedelta(days=days)).isoformat()
        except ValueError:
            out[stage] = text        # unparseable → leave exactly as found
    return out
