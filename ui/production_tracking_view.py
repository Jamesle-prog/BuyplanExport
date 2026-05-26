"""Streamlit view for the 🏭 Production Tracking tab.

This module is built incrementally:
  - **Stage 4 (current)**: navigation shell, access-control gate, metrics row,
    placeholder panels.  No forms yet.
  - Stage 5: Add New workflow.
  - Stage 6: Edit workflow.
  - Stage 7: Dashboard cards + Overview table.
  - Stage 8: Plan tab.
  - Stage 9: QC inspection plumbing in the Edit form.

Navigation rationale
--------------------
We use ``st.radio(horizontal=True)`` for sub-tab selection — not
``st.tabs()`` — because programmatic switching (e.g. the Dashboard "✏️ Edit"
shortcut button) needs session-state control over which panel is shown.
``st.tabs()`` has no session-state index; ``st.segmented_control`` has the
same widget-key-wins-over-index problem.  See
``docs/build_plan_production_tracking_by_stages.md`` §"Stage 4".
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from ui.session_keys import SK
from ui.stores import get_production_tracking_store, get_store


# Order matters — the index in this list is what PT_ACTIVE_TAB stores.
_TAB_LABELS: list[str] = [
    "📊 Dashboard",
    "📋 Overview",
    "✏️ Edit Record",
    "➕ Add New",
    "📅 Plan",
]

# Indexes used by the dashboard Edit shortcut and similar cross-panel jumps.
TAB_DASHBOARD = 0
TAB_OVERVIEW  = 1
TAB_EDIT      = 2
TAB_ADD       = 3
TAB_PLAN      = 4


def show_production_tracking_tab(
    user_cos: list[str],
    username: str,
    admin_mode: bool,
) -> None:
    """Entry point for the 🏭 Tracking tab.

    Parameters
    ----------
    user_cos
        The company codes the user is allowed to see.  Empty list for users
        who have no companies assigned.
    username
        Currently logged-in user (written to ``updated_by`` on saves).
    admin_mode
        Pre-computed admin flag from the caller.  We never call
        ``is_admin()`` inside this view — privilege checks live at one
        call site (``app.py``).
    """
    store    = get_production_tracking_store()
    po_store = get_store()
    today    = date.today()

    # ── Access control gate ────────────────────────────────────────────────
    # Non-admin users with no assigned companies see nothing — never let
    # admin status leak through the "no filter" path of list_all().
    if not admin_mode and not user_cos:
        st.info(
            "No companies assigned to your account. "
            "Contact an administrator to be granted access."
        )
        return

    records = store.list_all(
        companies=user_cos if not admin_mode else None,
        allow_all=admin_mode,
    )
    readiness_map = {r["id"]: store.compute_readiness(r) for r in records}
    reminder_map  = {
        r["id"]: store.compute_inspection_reminders(r, today)
        for r in records
    }

    # ── Top metrics row ────────────────────────────────────────────────────
    _render_metrics(records, readiness_map, reminder_map, today)

    # ── Sub-tab navigation (st.radio with session-state-controlled index) ──
    # The dashboard Edit shortcut works by setting BOTH PT_ACTIVE_TAB AND
    # the radio's own session-state key ("pt_tab_radio") before st.rerun().
    # Setting only PT_ACTIVE_TAB would silently fail because Streamlit
    # ignores `index=` once the widget key has a value in session_state.
    active_label = st.radio(
        "Sub-section",
        _TAB_LABELS,
        horizontal=True,
        index=st.session_state.get(SK.PT_ACTIVE_TAB, TAB_DASHBOARD),
        key="pt_tab_radio",
        label_visibility="collapsed",
    )
    st.session_state[SK.PT_ACTIVE_TAB] = _TAB_LABELS.index(active_label)

    st.divider()

    # ── Dispatch ───────────────────────────────────────────────────────────
    if active_label == _TAB_LABELS[TAB_DASHBOARD]:
        _render_dashboard_tab(records, readiness_map, reminder_map, today)
    elif active_label == _TAB_LABELS[TAB_OVERVIEW]:
        _render_overview_table(records, readiness_map, reminder_map, today)
    elif active_label == _TAB_LABELS[TAB_EDIT]:
        _render_edit_tab(records, readiness_map, store, username, today)
    elif active_label == _TAB_LABELS[TAB_ADD]:
        _render_add_tab(store, po_store, username)
    elif active_label == _TAB_LABELS[TAB_PLAN]:
        _render_plan_tab(records, store)


# ─────────────────────────────────────────────────────────────────────────────
# Metrics row (Stage 4 — minimal counts; Stage 7 fleshes out formatting)
# ─────────────────────────────────────────────────────────────────────────────

def _render_metrics(records, readiness_map, reminder_map, today) -> None:
    """Five summary metrics at the top of the Tracking tab."""
    from po_extractor.store._production_tracking_schema import STAGES

    total = len(records)

    delayed_stages = sum(
        1
        for r in records
        for s in STAGES
        if (r.get(f"{s}_status") or "") == "Delayed"
    )

    blocked = sum(
        1
        for r in records
        if any(
            readiness_map[r["id"]][t].startswith("waiting")
            for t in ("pp_sample", "cutting")
        )
    )

    today_iso = today.isoformat()
    completed_today = sum(
        1
        for r in records
        for s in STAGES
        if (r.get(f"{s}_actual") or "") == today_iso
    )

    qc_due = sum(1 for r in records if reminder_map[r["id"]])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Tracked",  total)
    c2.metric("Delayed Stages", delayed_stages)
    c3.metric("Blocked",        blocked)
    c4.metric("Completed Today", completed_today)
    c5.metric("QC Bookings Due", qc_due)


# ─────────────────────────────────────────────────────────────────────────────
# Panel stubs — each gets fleshed out in its dedicated build stage
# ─────────────────────────────────────────────────────────────────────────────

def _render_dashboard_tab(records, readiness_map, reminder_map, today) -> None:
    """Stage 7 will render the per-PO progress cards.  For now: count summary."""
    if not records:
        st.info("No tracked records yet. Use **➕ Add New** to start tracking a PO/style.")
        return
    st.caption(
        f"📊 Dashboard placeholder — {len(records)} record(s) loaded. "
        "Card grid lands in Stage 7."
    )


def _render_overview_table(records, readiness_map, reminder_map, today) -> None:
    """Stage 7 will render the wide emoji-badge table."""
    if not records:
        st.info("No tracked records yet.")
        return
    st.caption(
        f"📋 Overview placeholder — {len(records)} record(s) loaded. "
        "Full table lands in Stage 7."
    )


def _render_edit_tab(records, readiness_map, store, username, today) -> None:
    """Stage 6 will render the full Edit form."""
    if not records:
        st.info("No tracked records yet. Use **➕ Add New** first.")
        return
    st.caption(
        f"✏️ Edit Record placeholder — {len(records)} record(s) available. "
        "Form lands in Stage 6."
    )


def _render_add_tab(store, po_store, username) -> None:
    """Stage 5 will render the Add New picker + initial form."""
    untracked = store.list_untracked_pos(po_store)
    if not untracked:
        st.info("All POs are already being tracked.")
        return
    st.caption(
        f"➕ Add New placeholder — {len(untracked)} untracked PO/style row(s). "
        "Picker + form land in Stage 5."
    )


def _render_plan_tab(records, store) -> None:
    """Stage 8 will render the planning what-if interface."""
    if not records:
        st.info("No tracked records yet — nothing to plan.")
        return
    st.caption(
        f"📅 Plan placeholder — {len(records)} record(s) available. "
        "Schedule calculator lands in Stage 8."
    )
