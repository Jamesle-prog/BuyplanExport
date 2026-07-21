"""Streamlit view for the 🏭 Production Tracking tab.

This module is built incrementally:
  - **Stage 4**: navigation shell, access-control gate, metrics row,
    placeholder panels.
  - **Stage 5**: Add New workflow.
  - **Stage 6**: Edit Record workflow.
  - **Stage 7 (current)**: Dashboard cards + Overview table — the "track a
    PO's progress by style" view. Company/factory/at-risk filters shared by
    both; status badges/current-stage logic centralized (_status_badges,
    ProductionTrackingStore.current_stage) so Dashboard, Overview, and Edit
    never disagree about a record's state.
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

Widget-key scoping
------------------
Every form widget uses a key prefixed by the integer record id:
``_wkey(rid, base) = f"pt_edit_{rid}_{base}"``.  This ensures that when the
user switches to a different record the widgets start from that record's DB
values rather than carrying over values from the previously selected record.

_MISSING sentinel
-----------------
``_read(widget_key, record, record_key)`` uses a module-level ``_MISSING``
object to distinguish three states:

  1. Widget was never rendered (key absent from session_state) →
     return ``record[record_key]`` (DB fallback).
  2. Widget was rendered and user cleared a date field → value is ``None``
     → return ``None`` so the field is saved as "".
  3. Widget was rendered with a real value → return that value.

This is critical for preserve-on-save correctness for optional sample stages
that are toggled off (and therefore not rendered) on a given save cycle.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from ui.i18n import t
from ui.session_keys import SK
from ui.shared import fragment_rerun, guard_multiselect_state
from ui.stores import get_production_tracking_store, get_store

# ── Schema constants — imported once at module load, not on every render ──────
# Keeping these at module level avoids repeated sys.modules lookups inside the
# many small render functions that previously used local `from … import` calls.
from po_extractor.store._production_tracking_schema import (
    STAGES,
    STAGES_GROUP_A,
    STAGES_GROUP_B_OPTIONAL,
    STAGES_GROUP_C,
    STAGES_GROUP_D,
    OPTIONAL_SAMPLE_STAGES,
    STAGE_LABELS,
    STATUS_OPTIONS,
    PREREQ_VALID,
    DEFAULT_DEP_ON,
    QC_INSPECTIONS,
    QC_INSPECTION_LABELS,
    QC_RESULT_OPTIONS,
    QC_FIELDS,
    dep_col,
)


# ── Module-level sentinel ─────────────────────────────────────────────────────
_MISSING = object()

# Order matters — the index in this list is what PT_ACTIVE_TAB stores.
_TAB_LABELS: list[str] = [
    "📊 Dashboard",
    "📋 Overview",
    "✏️ Edit Record",
    "➕ Add New",
    "📅 Plan",
    "📨 Factory Updates",
]

# Indexes used by the dashboard Edit shortcut and similar cross-panel jumps.
TAB_DASHBOARD = 0
TAB_OVERVIEW  = 1
TAB_EDIT      = 2
TAB_ADD       = 3
TAB_PLAN      = 4
TAB_FACTORY   = 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wkey(rid: int, base: str) -> str:
    """Return a widget key scoped to one record id."""
    return f"pt_edit_{rid}_{base}"


def _to_iso_or_empty(val: Any) -> str:
    """Convert a date / datetime / ISO string / None to ISO string or ''."""
    if val is None:
        return ""
    if isinstance(val, (date,)):
        return val.isoformat()
    s = str(val).strip()
    # Already ISO-formatted or empty
    return s


def _read(widget_key: str, record: dict, record_key: str) -> Any:
    """Read the current value for a field, preferring the live widget state.

    If the widget has never been rendered (key not in session_state) we fall
    back to the stored DB value so that hidden widgets (e.g. an applicable=0
    sample stage) preserve their values on save.
    """
    v = st.session_state.get(widget_key, _MISSING)
    if v is _MISSING:
        return record.get(record_key)
    return v


def _parse_date(val: Any) -> date | None:
    """Parse an ISO date string or date object to a date, or None."""
    if isinstance(val, date):
        return val
    if not val:
        return None
    try:
        return date.fromisoformat(str(val).strip())
    except (ValueError, AttributeError):
        return None


# ── Stage column headers ──────────────────────────────────────────────────────

def _stage_col_headers() -> None:
    """Render a single-row header for the 6-column stage row layout."""
    h1, h2, h3, h4, h5, h6 = st.columns([2.5, 2, 2, 2, 1.5, 2.5])
    h1.caption(f"**{t('Stage')}**")
    h2.caption(f"**{t('Status')}**")
    h3.caption(f"**{t('Planned')}**")
    h4.caption(f"**{t('Actual')}**")
    h5.caption(f"**{t('Exp.Days')}**")
    h6.caption(f"**{t('Notes')}**")


# ── Per-stage row renderer ────────────────────────────────────────────────────

def _render_stage_row(stage: str, record: dict, rid: int) -> None:
    """Render the 6-column Status/Planned/Actual/ExpDays/Notes row for one stage."""
    label   = STAGE_LABELS[stage]
    col1, col2, col3, col4, col5, col6 = st.columns([2.5, 2, 2, 2, 1.5, 2.5])

    with col1:
        st.markdown(f"**{label}**")

    with col2:
        current_status = record.get(f"{stage}_status") or "Not Started"
        st.selectbox(
            "Status",
            STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0,
            key=_wkey(rid, f"{stage}_status"),
            label_visibility="collapsed",
        )

    with col3:
        planned_val = _parse_date(record.get(f"{stage}_planned"))
        st.date_input(
            "Planned",
            value=planned_val,
            key=_wkey(rid, f"{stage}_planned"),
            label_visibility="collapsed",
        )

    with col4:
        actual_val = _parse_date(record.get(f"{stage}_actual"))
        st.date_input(
            "Actual",
            value=actual_val,
            key=_wkey(rid, f"{stage}_actual"),
            label_visibility="collapsed",
        )

    with col5:
        exp_days = record.get(f"{stage}_expected_days")
        st.number_input(
            "Exp.Days",
            min_value=0,
            step=1,
            value=int(exp_days) if exp_days is not None else 0,
            key=_wkey(rid, f"{stage}_expected_days"),
            label_visibility="collapsed",
        )

    with col6:
        notes_val = record.get(f"{stage}_notes") or ""
        st.text_input(
            "Notes",
            value=notes_val,
            key=_wkey(rid, f"{stage}_notes"),
            label_visibility="collapsed",
        )


def _render_dep_row(stage: str, record: dict, rid: int) -> None:
    """Render the 'Required for:' dependency multiselect for one source stage."""
    targets = PREREQ_VALID.get(stage, [])
    if not targets:
        return

    # Build display-name ↔ key maps
    label_to_key = {STAGE_LABELS[t]: t for t in targets}
    options = list(label_to_key.keys())
    default_labels = [
        STAGE_LABELS[t]
        for t in targets
        if record.get(dep_col(stage, t), 0)
    ]

    # Seed-once + guard (never key= AND default= together — CLAUDE.md).
    wkey = _wkey(rid, f"dep_{stage}")
    if wkey not in st.session_state:
        st.session_state[wkey] = default_labels
    else:
        guard_multiselect_state(wkey, options)

    selected = st.multiselect(
        "Required for:",
        options=options,
        key=wkey,
    )
    # Store the resolved keys back in session_state so _collect_dep_fields
    # can read them without a second reverse-lookup pass.
    st.session_state[_wkey(rid, f"dep_{stage}_keys")] = [
        label_to_key[lbl] for lbl in selected
    ]


# ── Readiness badge ───────────────────────────────────────────────────────────

def _render_readiness_badge(label: str, readiness: str) -> None:
    """Render a readiness status callout for PP Sample or Cutting."""
    if readiness == "ready":
        st.success(f"✅ **{label}** — {t('Ready')}")
    elif readiness.startswith("waiting"):
        waiting_on = readiness[len("waiting:"):]
        st.warning(f"⏳ **{label}** — {t('Waiting on:')} {waiting_on}")
    else:  # no_prereqs
        st.info(f"⚪ **{label}** — {t('No prerequisites set')}")


# ── Section renderers ─────────────────────────────────────────────────────────

def _group_progress(record: dict, stages: list[str]) -> tuple[int, int]:
    """Return ``(done, total)`` across *stages* — status "Done" counts."""
    done = sum(
        1 for s in stages
        if (record.get(f"{s}_status") or "Not Started") == "Done"
    )
    return done, len(stages)


def _render_group_a_section(record: dict, rid: int, readiness: dict[str, str]) -> None:
    """Render Group A — Pre-Production (8 parallel stages).

    ``readiness`` is the full readiness map for this record.  Trim Purchase and
    Fabric Purchase show a badge because they are gated by Trim Layout and
    Fabric Color (LD) respectively.  Fully-done groups collapse so the ~40-row
    edit form stays focused on stages that still need work.
    """
    # Stages that receive a readiness badge inside Group A.
    _GATED = {"trim_purchase", "fabric_purchase"}

    _done, _total = _group_progress(record, list(STAGES_GROUP_A))
    with st.expander(
        f"🧵 {t('Group A — Pre-Production (Parallel)')} · {_done}/{_total} ✅",
        expanded=_done < _total,
    ):
        _stage_col_headers()
        for stage in STAGES_GROUP_A:
            if stage in _GATED and stage in readiness:
                _render_readiness_badge(
                    {
                        "trim_purchase":   "Trim Purchase",
                        "fabric_purchase": "Fabric Purchase",
                    }[stage],
                    readiness[stage],
                )
            _render_stage_row(stage, record, rid)
            _render_dep_row(stage, record, rid)
    st.divider()


def _render_optional_samples_section(record: dict, rid: int) -> None:
    """Render the optional sample stages inside an expander."""
    any_applicable = any(
        record.get(f"{s}_applicable", 0) for s in STAGES_GROUP_B_OPTIONAL
    )

    with st.expander(t("Optional Samples"), expanded=any_applicable):
        for stage in STAGES_GROUP_B_OPTIONAL:
            applicable = st.toggle(
                f"Include {STAGE_LABELS[stage]}",
                value=bool(record.get(f"{stage}_applicable", 0)),
                key=_wkey(rid, f"{stage}_applicable"),
            )
            if applicable:
                _stage_col_headers()
                _render_stage_row(stage, record, rid)
                # Optional samples can only target PP Sample
                pp_label = STAGE_LABELS["pp_sample"]
                is_dep = bool(record.get(dep_col(stage, "pp_sample"), 0))
                # Seed-once + guard (never key= AND default= together).
                dep_wkey = _wkey(rid, f"dep_{stage}_pp")
                if dep_wkey not in st.session_state:
                    st.session_state[dep_wkey] = [pp_label] if is_dep else []
                else:
                    guard_multiselect_state(dep_wkey, [pp_label])
                selected = st.multiselect(
                    "Required for:",
                    options=[pp_label],
                    key=dep_wkey,
                )
                st.session_state[_wkey(rid, f"dep_{stage}_keys")] = (
                    ["pp_sample"] if pp_label in selected else []
                )
            st.divider()


def _render_pp_sample_section(record: dict, rid: int, readiness: str) -> None:
    """Render the PP Sample section with readiness badge and substitute toggle.

    NOTE: unlike Groups A/C/D this section is NOT wrapped in an expander —
    it contains the "Optional Samples" expander and Streamlit forbids nested
    expanders. The subheader carries the same done-count instead.
    """
    _b_stages = ["pp_sample"] + [
        s for s in STAGES_GROUP_B_OPTIONAL if record.get(f"{s}_applicable", 0)
    ]
    _done, _total = _group_progress(record, _b_stages)
    st.subheader(f"🧪 {t('Group B — Samples')} · {_done}/{_total} ✅")

    # ── Substitute materials toggle ──────────────────────────────────────────
    use_sub = st.toggle(
        "🔄 Use Substitute Materials for Samples",
        value=bool(record.get("use_substitute_materials", 1)),
        key=_wkey(rid, "use_substitute_materials"),
        help=(
            "ON: Sample Trim/Fabric Purchase gate samples; bulk Group A "
            "runs in parallel.\n"
            "OFF: All bulk Group A stages must be Done before any sample starts."
        ),
    )
    if use_sub:
        st.info(
            "🔄 Substitute mode: Sample Trim/Fabric Purchase gate samples. "
            "Bulk confirmations run in parallel."
        )
    else:
        st.warning(
            "⚠️ Confirmed materials mode: Trim Purchase, Trim Layout, "
            "Fabric Purchase, and Fabric Color (LD) must all be Done before "
            "any sample can start."
        )

    _render_optional_samples_section(record, rid)

    st.markdown("#### PP Sample *(Compulsory)*")
    _render_readiness_badge("PP Sample", readiness)
    _stage_col_headers()
    _render_stage_row("pp_sample", record, rid)
    st.divider()


def _render_group_c_section(record: dict, rid: int, readiness_cutting: str) -> None:
    """Render Group C — Production (sequential); collapses when fully done."""
    _done, _total = _group_progress(record, list(STAGES_GROUP_C))
    with st.expander(
        f"🏭 {t('Group C — Production (Sequential)')} · {_done}/{_total} ✅",
        expanded=_done < _total,
    ):
        # Cutting gets a readiness badge
        st.markdown("#### Cutting")
        _render_readiness_badge("Cutting", readiness_cutting)
        _stage_col_headers()
        _render_stage_row("cutting", record, rid)

        # Remaining production stages
        for stage in STAGES_GROUP_C[1:]:  # sewing, top_sample, packing, qa, final_qa
            _stage_col_headers()
            _render_stage_row(stage, record, rid)

    st.divider()


def _render_group_d_section(record: dict, rid: int) -> None:
    """Render Group D — Post-Production (sequential); collapses when fully done."""
    _done, _total = _group_progress(record, list(STAGES_GROUP_D))
    with st.expander(
        f"📦 {t('Group D — Post-Production')} · {_done}/{_total} ✅",
        expanded=_done < _total,
    ):
        _stage_col_headers()
        for stage in STAGES_GROUP_D:
            _render_stage_row(stage, record, rid)
    st.divider()


def _render_qc_section(record: dict, rid: int, reminders: list[dict]) -> None:
    """Render the QC Inspections section."""
    st.subheader("🔍 QC Inspections")
    reminder_map = {r["key"]: r for r in reminders}

    for key in QC_INSPECTIONS:
        label = QC_INSPECTION_LABELS[key]

        # Re-Final: only show if Final result == 'Fail' (read current widget
        # value if rendered, else fall back to DB).
        if key == "insp_refinal":
            final_wkey = _wkey(rid, "insp_final_result")
            final_result = st.session_state.get(
                final_wkey, record.get("insp_final_result", "")
            )
            if final_result != "Fail":
                st.caption(
                    "🔁 Re-Final Inspection — appears when Final result is 'Fail'"
                )
                continue

        st.markdown(f"#### {label}")

        if key in reminder_map:
            rem = reminder_map[key]
            if rem["overdue"]:
                st.error(
                    f"⚠️ Booking OVERDUE — deadline was {rem['deadline']}"
                )
            else:
                st.warning(
                    f"⚠️ Book by {rem['deadline']} — reminder triggered"
                )

        # Row 1 — booking fields
        col1, col2, col3, col4 = st.columns([2.5, 1.5, 2, 2])
        with col1:
            st.date_input(
                t("Booking Deadline"),
                value=_parse_date(record.get(f"{key}_booking_deadline")),
                key=_wkey(rid, f"{key}_booking_deadline"),
            )
        with col2:
            st.number_input(
                t("Reminder Days"),
                min_value=1,
                step=1,
                value=int(record.get(f"{key}_reminder_days") or 7),
                key=_wkey(rid, f"{key}_reminder_days"),
            )
        with col3:
            st.checkbox(
                f"✅ {t('Booked')}",
                value=bool(record.get(f"{key}_booked", 0)),
                key=_wkey(rid, f"{key}_booked"),
            )
        with col4:
            st.date_input(
                t("Booking Date"),
                value=_parse_date(record.get(f"{key}_booking_date")),
                key=_wkey(rid, f"{key}_booking_date"),
            )

        # Row 2 — inspection result fields
        col5, col6, col7 = st.columns([2, 2, 4])
        with col5:
            st.date_input(
                t("Inspection Date"),
                value=_parse_date(record.get(f"{key}_inspection_date")),
                key=_wkey(rid, f"{key}_inspection_date"),
            )
        with col6:
            current_result = record.get(f"{key}_result") or "Pending"
            if current_result not in QC_RESULT_OPTIONS:
                current_result = "Pending"
            st.selectbox(
                t("Result"),
                QC_RESULT_OPTIONS,
                index=QC_RESULT_OPTIONS.index(current_result),
                key=_wkey(rid, f"{key}_result"),
            )
        with col7:
            st.text_input(
                t("Notes"),
                value=record.get(f"{key}_notes") or "",
                key=_wkey(rid, f"{key}_notes"),
            )


# ── Field collectors ──────────────────────────────────────────────────────────

def _collect_stage_fields(record: dict, rid: int) -> dict[str, Any]:
    """Read all per-stage widget values from session_state, DB-falling-back
    for hidden widgets (e.g. inapplicable optional sample stages)."""
    fields: dict[str, Any] = {}
    for stage in STAGES:
        # applicable toggle (optional sample stages only)
        if stage in OPTIONAL_SAMPLE_STAGES:
            appl_key = _wkey(rid, f"{stage}_applicable")
            fields[f"{stage}_applicable"] = int(
                bool(_read(appl_key, record, f"{stage}_applicable"))
            )

        for suffix in ("status", "planned", "actual", "expected_days", "notes"):
            wk = _wkey(rid, f"{stage}_{suffix}")
            val = _read(wk, record, f"{stage}_{suffix}")
            if suffix in ("planned", "actual"):
                val = _to_iso_or_empty(val)
            elif suffix == "expected_days":
                val = int(val) if val is not None else None
            fields[f"{stage}_{suffix}"] = val

    return fields


def _collect_dep_fields(record: dict, rid: int) -> dict[str, Any]:
    """Read all dependency widget values.  The pp_sample→cutting dep is
    always 1 (system-enforced)."""
    fields: dict[str, Any] = {}

    for source, targets in PREREQ_VALID.items():
        # pp_sample → cutting is system-enforced; never comes from a widget.
        if source == "pp_sample":
            fields[dep_col("pp_sample", "cutting")] = 1
            continue

        keys_key = _wkey(rid, f"dep_{source}_keys")
        selected_targets: list[str] = st.session_state.get(keys_key, _MISSING)  # type: ignore[assignment]

        if selected_targets is _MISSING:
            # Widget was not rendered this cycle — preserve DB values.
            # (loop var named `tgt`, not `t` — `t` is the i18n translator
            # imported into this module; a bare `for t in ...:` anywhere in a
            # function makes Python treat `t` as local for the WHOLE function,
            # breaking any `t(...)` call that runs earlier — see the
            # _render_add_tab UnboundLocalError this caused.)
            for tgt in targets:
                col = dep_col(source, tgt)
                fields[col] = record.get(col, 0)
        else:
            for tgt in targets:
                fields[dep_col(source, tgt)] = 1 if tgt in selected_targets else 0

    return fields


def _collect_qc_fields(record: dict, rid: int) -> dict[str, Any]:
    """Read all QC inspection widget values."""
    fields: dict[str, Any] = {}
    for key in QC_INSPECTIONS:
        for suffix in QC_FIELDS:
            col = f"{key}_{suffix}"
            wk = _wkey(rid, col)
            val = _read(wk, record, col)
            if suffix in ("booking_deadline", "booking_date", "inspection_date"):
                val = _to_iso_or_empty(val)
            elif suffix == "booked":
                val = int(bool(val))
            elif suffix == "reminder_days":
                val = int(val) if val is not None else 7
            fields[col] = val
    return fields


def _do_save(record: dict, store, username: str, rid: int) -> None:
    """Collect all widget values and call store.upsert()."""
    stage_fields = _collect_stage_fields(record, rid)
    dep_fields   = _collect_dep_fields(record, rid)
    qc_fields    = _collect_qc_fields(record, rid)

    overall_key = _wkey(rid, "overall_notes")
    overall_notes = _read(overall_key, record, "overall_notes") or ""

    sub_key = _wkey(rid, "use_substitute_materials")
    use_sub = _read(sub_key, record, "use_substitute_materials")
    if use_sub is None:
        use_sub = 1

    store.upsert(
        po_number=record["po_number"],
        style=record["style"],
        factory=record.get("factory") or "",
        company=record.get("company") or "",
        updated_by=username,
        overall_notes=str(overall_notes),
        use_substitute_materials=int(bool(use_sub)),
        stage_fields=stage_fields,
        dep_fields=dep_fields,
        qc_fields=qc_fields,
    )
    st.success("✅ Record saved.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

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
        st.info(t(
            "No companies assigned to your account. "
            "Contact an administrator to be granted access."
        ))
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
    # NOTE: options stay English (stable widget/session values, index math);
    # format_func translates at render time so language switches apply live.
    active_label = st.radio(
        "Sub-section",
        _TAB_LABELS,
        horizontal=True,
        index=st.session_state.get(SK.PT_ACTIVE_TAB, TAB_DASHBOARD),
        key="pt_tab_radio",
        format_func=t,
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
        _render_add_tab(store, po_store, username, user_cos=user_cos, admin_mode=admin_mode)
    elif active_label == _TAB_LABELS[TAB_PLAN]:
        _render_plan_tab(records, store)
    elif active_label == _TAB_LABELS[TAB_FACTORY]:
        _render_factory_updates_tab(records, username, admin_mode)


# ─────────────────────────────────────────────────────────────────────────────
# Metrics row
# ─────────────────────────────────────────────────────────────────────────────

def _render_metrics(records, readiness_map, reminder_map, today) -> None:
    """Five summary metrics at the top of the Tracking tab."""
    total = len(records)

    # Only count stages that are applicable — inapplicable optional samples
    # (applicable=0) must be excluded from Delayed to match the module rule
    # that inapplicable stages are invisible to all metrics.
    delayed_stages = sum(
        1
        for r in records
        for s in STAGES
        if (r.get(f"{s}_status") or "") == "Delayed"
        and (s not in OPTIONAL_SAMPLE_STAGES or r.get(f"{s}_applicable", 0))
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
        and (s not in OPTIONAL_SAMPLE_STAGES or r.get(f"{s}_applicable", 0))
    )

    qc_due = sum(1 for r in records if reminder_map[r["id"]])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(t("Total Tracked"),   f"{total:,}")
    c2.metric(t("Delayed Stages"),  f"{delayed_stages:,}")
    c3.metric(t("Blocked"),         f"{blocked:,}")
    c4.metric(t("Completed Today"), f"{completed_today:,}")
    c5.metric(t("QC Bookings Due"), f"{qc_due:,}")


# ─────────────────────────────────────────────────────────────────────────────
# Shared Dashboard/Overview helpers — filters, at-risk, status badges
# ─────────────────────────────────────────────────────────────────────────────

def _all_companies(records: list[dict]) -> list[str]:
    return sorted({r.get("company") or "" for r in records if r.get("company")})


def _all_factories(records: list[dict]) -> list[str]:
    return sorted({r.get("factory") or "" for r in records if r.get("factory")})


def _is_delayed(record: dict) -> bool:
    """True if any APPLICABLE stage is status='Delayed' — same applicable
    rule used by the top metrics row's Delayed count."""
    return any(
        (record.get(f"{s}_status") or "") == "Delayed"
        for s in STAGES
        if s not in OPTIONAL_SAMPLE_STAGES or record.get(f"{s}_applicable", 0)
    )


def _is_blocked(readiness: dict[str, str]) -> bool:
    """True if PP Sample or Cutting is waiting on a prerequisite — same rule
    the top metrics row's Blocked count uses."""
    return any(readiness.get(tgt, "").startswith("waiting") for tgt in ("pp_sample", "cutting"))


def _is_at_risk(record: dict, readiness: dict[str, str]) -> bool:
    return _is_delayed(record) or _is_blocked(readiness)


def _group_b_stages_for(record: dict) -> list[str]:
    """Group B stages applicable to *record* — pp_sample plus whichever
    optional samples are currently toggled on. Mirrors the Edit form's own
    Group B section (_render_pp_sample_section) so a card's/row's "B x/y"
    figure always matches what the Edit tab shows for the same record."""
    return ["pp_sample"] + [
        s for s in STAGES_GROUP_B_OPTIONAL if record.get(f"{s}_applicable", 0)
    ]


def _status_badges(record: dict, readiness: dict[str, str], reminders: list[dict]) -> list[str]:
    """Return the badge strings that apply to one record, most severe first.
    Shared by the Dashboard cards and the Overview table so the two views
    never disagree about a record's state (Stage 7 exit criterion)."""
    badges: list[str] = []
    if _is_delayed(record):
        badges.append(f"🔴 {t('Delayed')}")
    if _is_blocked(readiness):
        badges.append(f"⏳ {t('Blocked')}")
    if reminders:
        overdue = any(r["overdue"] for r in reminders)
        badges.append(f"🔔 {t('QC overdue') if overdue else t('QC due')}")
    if not badges:
        badges.append(f"✅ {t('On Track')}")
    return badges


def _jump_to_edit(rid: int) -> None:
    """Navigate to the Edit tab with *rid* pre-selected — same mechanism as
    the Add New → Edit handoff (see show_production_tracking_tab's note on
    why the radio's own widget key must be popped, not overwritten)."""
    st.session_state[SK.PT_SELECTED_EDIT] = rid
    st.session_state[SK.PT_ACTIVE_TAB]    = TAB_EDIT
    st.session_state.pop("pt_tab_radio", None)
    fragment_rerun()


def _render_progress_filters(
    records: list[dict], readiness_map: dict, key_prefix: str,
) -> list[dict]:
    """Company / factory / at-risk filter row, applied to *records*.

    *key_prefix* scopes widget keys per caller (Dashboard vs. Overview) so
    the two sub-tabs keep independent filter selections rather than fighting
    over one shared widget key.
    """
    companies = _all_companies(records)
    factories = _all_factories(records)

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        wkey = f"{key_prefix}_filter_company"
        guard_multiselect_state(wkey, companies)
        sel_companies = st.multiselect(
            t("Company"), options=companies, key=wkey,
            placeholder=t("All companies"),
        )
    with c2:
        wkey = f"{key_prefix}_filter_factory"
        guard_multiselect_state(wkey, factories)
        sel_factories = st.multiselect(
            t("Factory"), options=factories, key=wkey,
            placeholder=t("All factories"),
        )
    with c3:
        st.markdown("&nbsp;")  # align checkbox with the multiselect boxes
        only_at_risk = st.checkbox(
            f"⚠️ {t('Only at-risk')}", key=f"{key_prefix}_filter_at_risk",
        )

    out = []
    for r in records:
        if sel_companies and (r.get("company") or "") not in sel_companies:
            continue
        if sel_factories and (r.get("factory") or "") not in sel_factories:
            continue
        if only_at_risk and not _is_at_risk(r, readiness_map[r["id"]]):
            continue
        out.append(r)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard tab — Stage 7
# ─────────────────────────────────────────────────────────────────────────────

def _render_dashboard_tab(records, readiness_map, reminder_map, today) -> None:
    """Card grid: one card per tracked PO/style with overall + per-group
    progress, status badges, a QC alert line, and an Edit shortcut."""
    from po_extractor.store.production_tracking_store import ProductionTrackingStore

    if not records:
        st.info(t("No tracked records yet. Use **➕ Add New** to start tracking a PO/style."))
        return

    filtered = _render_progress_filters(records, readiness_map, key_prefix="pt_dash")
    if not filtered:
        st.warning(t("No records match the current filters."))
        return
    st.caption(f"{len(filtered)} / {len(records)} {t('record(s) shown')}")

    cols_per_row = 3
    for row_start in range(0, len(filtered), cols_per_row):
        cols = st.columns(cols_per_row)
        for col, record in zip(cols, filtered[row_start:row_start + cols_per_row]):
            with col:
                rid = record["id"]
                readiness = readiness_map[rid]
                reminders = reminder_map[rid]
                with st.container(border=True):
                    st.markdown(f"**{record['po_number']}** — {record.get('style') or '—'}")
                    st.caption(
                        f"{record.get('company') or '—'} · "
                        f"{record.get('factory') or t('No factory set')}"
                    )

                    done, total = ProductionTrackingStore.overall_progress(record)
                    st.progress(
                        (done / total) if total else 0.0,
                        text=f"{done}/{total} {t('stages done')}",
                    )

                    group_bits = []
                    for label, stages in (
                        ("A", STAGES_GROUP_A), ("B", _group_b_stages_for(record)),
                        ("C", STAGES_GROUP_C), ("D", STAGES_GROUP_D),
                    ):
                        gd, gt = _group_progress(record, stages)
                        group_bits.append(f"{label} {gd}/{gt}")
                    st.caption(" · ".join(group_bits))

                    st.markdown(" ".join(_status_badges(record, readiness, reminders)))

                    cur = ProductionTrackingStore.current_stage(record)
                    st.caption(
                        f"➡️ {t('Next')}: {STAGE_LABELS.get(cur, cur)}" if cur
                        else f"🏁 {t('All stages complete')}"
                    )

                    if reminders:
                        names = ", ".join(r["label"] for r in reminders)
                        st.caption(f"🔔 {t('QC booking due')}: {names}")

                    if st.button(f"✏️ {t('Edit')}", key=f"pt_dash_edit_{rid}",
                                 use_container_width=True):
                        _jump_to_edit(rid)


# ─────────────────────────────────────────────────────────────────────────────
# Overview table — Stage 7
# ─────────────────────────────────────────────────────────────────────────────

def _render_overview_table(records, readiness_map, reminder_map, today) -> None:
    """One row per tracked PO/style: overall progress, per-group progress,
    current stage, and status badges — the flat "track a PO's progress by
    style" view. Consistent readiness/status logic with the Dashboard cards
    and the Edit form (Stage 7 exit criterion)."""
    from po_extractor.store.production_tracking_store import ProductionTrackingStore

    if not records:
        st.info(t("No tracked records yet."))
        return

    filtered = _render_progress_filters(records, readiness_map, key_prefix="pt_ovw")
    if not filtered:
        st.warning(t("No records match the current filters."))
        return

    rows = []
    for record in filtered:
        rid = record["id"]
        readiness = readiness_map[rid]
        reminders = reminder_map[rid]
        done, total = ProductionTrackingStore.overall_progress(record)
        cur = ProductionTrackingStore.current_stage(record)
        rows.append({
            "id":            rid,
            "PO Number":     record["po_number"],
            "Style":         record.get("style") or "—",
            "Company":       record.get("company") or "—",
            "Factory":       record.get("factory") or "—",
            "Progress":      (done / total) if total else 0.0,
            "Progress text": f"{done}/{total}",
            "Current Stage": STAGE_LABELS.get(cur, cur) if cur else t("Complete"),
            "Status":        " ".join(_status_badges(record, readiness, reminders)),
            "Updated":       (record.get("updated_at") or "")[:19].replace("T", " "),
            "Updated by":    record.get("updated_by") or "—",
        })
    df = pd.DataFrame(rows)

    st.dataframe(
        df.drop(columns=["id", "Progress text"]),
        width="stretch", hide_index=True, height=min(60 + 36 * len(df), 600),
        column_config={
            "PO Number":     st.column_config.TextColumn(t("PO Number"), width="medium"),
            "Style":         st.column_config.TextColumn(t("Style"), width="small"),
            "Company":       st.column_config.TextColumn(t("Company"), width="small"),
            "Factory":       st.column_config.TextColumn(t("Factory"), width="medium"),
            "Progress":      st.column_config.ProgressColumn(
                t("Progress"), min_value=0.0, max_value=1.0, format="%.0f%%",
            ),
            "Current Stage": st.column_config.TextColumn(t("Current Stage"), width="medium"),
            "Status":        st.column_config.TextColumn(t("Status"), width="medium"),
            "Updated":       st.column_config.TextColumn(t("Updated"), width="medium"),
            "Updated by":    st.column_config.TextColumn(t("Updated by"), width="small"),
        },
    )
    st.caption(f"{len(filtered)} / {len(records)} {t('record(s) shown')}")

    # ── Jump to Edit — same selectbox+button pattern as the Edit tab itself.
    def _fmt_ovw(rid: int) -> str:
        rec = next((r for r in filtered if r["id"] == rid), None)
        if rec is None:
            return str(rid)
        return f"{rec['po_number']} — {rec.get('style') or '—'}"

    col_sel, col_btn = st.columns([4, 1])
    with col_sel:
        chosen_id = st.selectbox(
            t("Jump to record"),
            options=[r["id"] for r in filtered],
            format_func=_fmt_ovw,
            key="pt_ovw_jump_select",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button(f"✏️ {t('Edit')}", key="pt_ovw_jump_edit", use_container_width=True):
            _jump_to_edit(chosen_id)


# ─────────────────────────────────────────────────────────────────────────────
# Edit Record tab — Stage 6
# ─────────────────────────────────────────────────────────────────────────────

def _render_edit_tab(records, readiness_map, store, username, today) -> None:
    """Full edit form for an existing tracking record."""
    if not records:
        st.info(t("No tracked records yet. Use **➕ Add New** first."))
        return

    # One-shot success message from the previous run's delete (the message
    # can't be shown in the delete handler itself — st.rerun() fires first).
    flash = st.session_state.pop(SK.PT_DELETE_FLASH, None)
    if flash:
        st.success(flash)

    # Build selectbox options — display as "PO# — Style" keyed by integer id
    id_to_record = {r["id"]: r for r in records}
    options = [r["id"] for r in records]

    def _fmt(rid: int) -> str:
        r = id_to_record[rid]
        style = r.get("style") or ""
        factory = r.get("factory") or ""
        label = f"{r['po_number']}"
        if style:
            label += f" — {style}"
        if factory:
            label += f"  ({factory})"
        return label

    # Honour pre-selection from Dashboard Edit shortcut
    preselected = st.session_state.get(SK.PT_SELECTED_EDIT)
    if preselected not in options:
        preselected = options[0]

    st.caption(f"{len(options):,} {t('record(s) tracked')}")
    selected_id = st.selectbox(
        t("Select PO / Style"),
        options=options,
        format_func=_fmt,
        index=options.index(preselected),
        key=SK.PT_SELECTED_EDIT,
    )

    # Defensive: selectbox state can briefly hold an id that no longer exists
    # (e.g. right after a delete); Streamlit reconciles it to the index
    # default on this same run, but never KeyError on the lookup.
    record = id_to_record.get(selected_id, id_to_record[options[0]])
    rid    = record["id"]
    readiness = readiness_map[rid]
    reminders = store.compute_inspection_reminders(record, today)

    st.divider()

    # ── Factory / Company (read-only display) ────────────────────────────────
    meta_c1, meta_c2, meta_c3 = st.columns([2, 2, 4])
    meta_c1.text_input("PO Number",  value=record.get("po_number") or "", disabled=True)
    meta_c2.text_input("Style",      value=record.get("style")     or "", disabled=True)
    meta_c3.text_input("Factory",    value=record.get("factory")   or "", disabled=True)

    # Overall notes
    overall_notes_val = record.get("overall_notes") or ""
    st.text_area(
        t("Overall Notes"),
        value=overall_notes_val,
        key=_wkey(rid, "overall_notes"),
    )

    st.divider()

    # ── Stage sections — ONE group rendered at a time ────────────────────────
    # Perf: rendering all 4 groups + QC mounts ~120 widgets (44 date pickers,
    # ~30 selectboxes...) and EVERY interaction re-mounts them all, making
    # each click feel seconds-slow. Rendering only the selected group cuts
    # that ~4-5x. Saving stays correct: the _read/_MISSING mechanism falls
    # back to the record's DB value for any widget not rendered this run
    # (the same contract the Optional Samples toggle already relies on).
    _PANES = [
        "🧵 A · Pre-Production",
        "🧪 B · Samples",
        "🏭 C · Production",
        "📦 D · Post-Production",
        "🔍 QC",
    ]
    pane = st.radio(
        "Stage group", _PANES, horizontal=True, key="pt_edit_pane",
        format_func=t, label_visibility="collapsed",
    )
    st.caption(t(
        "💾 Save before switching sections — unsaved edits in a section "
        "disappear when it is hidden."
    ))
    if pane == _PANES[0]:
        _render_group_a_section(record, rid, readiness)
    elif pane == _PANES[1]:
        _render_pp_sample_section(record, rid, readiness["pp_sample"])
    elif pane == _PANES[2]:
        _render_group_c_section(record, rid, readiness["cutting"])
    elif pane == _PANES[3]:
        _render_group_d_section(record, rid)
    else:
        _render_qc_section(record, rid, reminders)

    st.divider()

    # ── Save / Delete buttons ────────────────────────────────────────────────
    col_save, col_del = st.columns(2)

    with col_save:
        if st.button("💾 Save", type="primary", use_container_width=True):
            _do_save(record, store, username, rid)
            fragment_rerun()

    with col_del:
        if st.button("🗑️ Delete", use_container_width=True):
            st.session_state[SK.PT_DELETE_CONFIRM] = True

    if st.session_state.get(SK.PT_DELETE_CONFIRM):
        _style_part = (
            f"{t('Style:')} {record['style']}" if record.get("style") else t("no style")
        )
        st.warning(
            f"⚠️ {t('Delete')} **{record['po_number']}** ({_style_part})? "
            + t("This cannot be undone.")
        )
        if st.button(f"✅ {t('Confirm Delete')}", type="primary"):
            store.delete([rid])
            st.session_state[SK.PT_DELETE_CONFIRM] = False
            # Do NOT touch SK.PT_SELECTED_EDIT here — it is the selectbox's
            # widget key and was instantiated this run; assigning to it
            # raises StreamlitAPIException (the delete succeeded but the
            # success message and rerun never happened).  After the rerun
            # the stale id reconciles to the first option automatically.
            st.session_state[SK.PT_DELETE_FLASH] = t("Record deleted.")
            fragment_rerun()
        if st.button(t("Cancel")):
            st.session_state[SK.PT_DELETE_CONFIRM] = False
            fragment_rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Add New tab — Stage 5
# ─────────────────────────────────────────────────────────────────────────────

def _render_add_tab(
    store,
    po_store,
    username: str,
    *,
    user_cos: list[str],
    admin_mode: bool,
) -> None:
    """Picker + initial-fields form for adding a new tracking record.

    ``user_cos`` and ``admin_mode`` are forwarded to
    ``store.list_untracked_pos()`` so non-admin users only see candidates
    from their assigned companies (mirrors the ``list_all`` access-control
    contract).
    """
    untracked = store.list_untracked_pos(
        po_store,
        companies=user_cos if not admin_mode else None,
        allow_all=admin_mode,
    )
    if not untracked:
        st.info(t("All POs are already being tracked."))
        return

    # ── Client filter ──────────────────────────────────────────────────────
    # list_untracked_pos() now unions candidates from every client pipeline
    # (GIII + Sky East) — with several clients mixed together the picker
    # below can get long, so let the user narrow it down first.
    ALL_CLIENTS = t("All clients")
    clients = sorted({row["company"] for row in untracked if row.get("company")})
    if len(clients) > 1:
        client_options = [ALL_CLIENTS] + clients
        # Selectbox (not multiselect) — reconcile manually: a stale stored
        # value (e.g. the previously chosen client has no more untracked
        # POs) must not linger un-rendered.
        if st.session_state.get(SK.PT_ADD_CLIENT) not in client_options:
            st.session_state[SK.PT_ADD_CLIENT] = ALL_CLIENTS
        sel_client = st.selectbox(
            t("Client"),
            options=client_options,
            key=SK.PT_ADD_CLIENT,
        )
        if sel_client != ALL_CLIENTS:
            untracked = [row for row in untracked if row.get("company") == sel_client]

    # ── PO picker ────────────────────────────────────────────────────────────
    def _fmt_ut(row: dict) -> str:
        parts = [row["po_number"]]
        if row.get("style"):
            parts.append(row["style"])
        if row.get("factory"):
            parts.append(f"({row['factory']})")
        return " — ".join(parts)

    options = list(range(len(untracked)))
    selected_idx = st.selectbox(
        t("Select PO / Style to start tracking"),
        options=options,
        format_func=lambda i: _fmt_ut(untracked[i]),
        key="pt_add_picker",
    )
    chosen = untracked[selected_idx]

    st.divider()

    # ── Editable metadata ────────────────────────────────────────────────────
    mc1, mc2, mc3 = st.columns([2, 2, 4])
    mc1.text_input("PO Number", value=chosen["po_number"], disabled=True)
    mc2.text_input("Style",     value=chosen.get("style") or "", disabled=True)
    factory_val = st.text_input(
        "Factory",
        value=chosen.get("factory") or "",
        key="pt_add_factory",
    )
    company_val = chosen.get("company") or ""
    overall_notes_val = st.text_area(t("Overall Notes"), value="", key="pt_add_notes")

    st.divider()

    if st.button("➕ Start Tracking", type="primary", use_container_width=True):
        # Build the empty default payload — all stages Not Started,
        # expected_days=None, DEFAULT_DEP_ON flags set to 1.
        stage_fields: dict[str, Any] = {}
        for s in STAGES:
            if s in OPTIONAL_SAMPLE_STAGES:
                stage_fields[f"{s}_applicable"] = 0
            stage_fields[f"{s}_status"]        = "Not Started"
            stage_fields[f"{s}_planned"]       = ""
            stage_fields[f"{s}_actual"]        = ""
            stage_fields[f"{s}_notes"]         = ""
            stage_fields[f"{s}_expected_days"] = None

        dep_fields: dict[str, Any] = {}
        for source, targets in PREREQ_VALID.items():
            # loop var `tgt`, not `t` — `t` is this module's i18n translator;
            # a bare `for t in ...:` anywhere in the function makes Python
            # treat `t` as local for the WHOLE function (UnboundLocalError on
            # the t("Overall Notes") call above, which runs unconditionally).
            for tgt in targets:
                col = dep_col(source, tgt)
                dep_fields[col] = 1 if col in DEFAULT_DEP_ON else 0
        # pp_sample → cutting is always 1
        dep_fields[dep_col("pp_sample", "cutting")] = 1

        qc_fields: dict[str, Any] = {}
        for key in QC_INSPECTIONS:
            qc_fields[f"{key}_booking_deadline"] = ""
            qc_fields[f"{key}_reminder_days"]    = 7
            qc_fields[f"{key}_booked"]           = 0
            qc_fields[f"{key}_booking_date"]     = ""
            qc_fields[f"{key}_inspection_date"]  = ""
            qc_fields[f"{key}_result"]           = "Pending"
            qc_fields[f"{key}_notes"]            = ""

        new_id = store.upsert(
            po_number=chosen["po_number"],
            style=chosen.get("style") or "",
            factory=factory_val or chosen.get("factory") or "",
            company=company_val,
            updated_by=username,
            overall_notes=overall_notes_val,
            use_substitute_materials=1,
            stage_fields=stage_fields,
            dep_fields=dep_fields,
            qc_fields=qc_fields,
        )
        st.success(
            f"✅ Now tracking **{chosen['po_number']}**"
            + (f" — {chosen['style']}" if chosen.get("style") else "")
            + "."
        )
        # Navigate to Edit tab with the new record pre-selected
        st.session_state[SK.PT_SELECTED_EDIT] = new_id
        st.session_state[SK.PT_ACTIVE_TAB]    = TAB_EDIT
        # Delete the radio's own widget key so the next render falls back to
        # index=PT_ACTIVE_TAB.  Writing it directly after instantiation raises
        # StreamlitAPIException ("cannot be modified after widget instantiated").
        st.session_state.pop("pt_tab_radio", None)
        fragment_rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Plan tab — Stage 8 placeholder
# ─────────────────────────────────────────────────────────────────────────────

def _render_plan_tab(records, store) -> None:
    """Stage 8 will render the planning what-if interface."""
    if not records:
        st.info(t("No tracked records yet — nothing to plan."))
        return
    st.caption(
        f"📅 {t('Plan placeholder')} — {len(records)} "
        + t("record(s) available. Schedule calculator lands in Stage 8.")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Factory Updates tab — quantity reports from factories (units cut/sewn/packed)
# ─────────────────────────────────────────────────────────────────────────────

def _render_factory_updates_tab(records, username, admin_mode) -> None:
    """Excel round-trip + manual entry for factory quantity reports.

    Flow: generate a request form for one factory (their tracked PO/styles
    pre-filled) → factory fills the New-quantities columns → upload the
    returned file (validated preview → import) → per-PO/style totals table.
    Each report is a dated log entry (history kept); totals are derived.
    A future factory-login phase reuses the same store writes unchanged.
    """
    from ui.stores import get_factory_progress_store
    from po_extractor.store._factory_progress_schema import (
        REPORT_STAGES, REPORT_STAGE_LABELS,
        MILESTONE_STAGES, MILESTONE_LABELS,
    )
    from po_extractor.exporters.factory_progress_form import (
        build_progress_request_xlsx, parse_progress_report_xlsx,
    )

    fp_store = get_factory_progress_store()

    if not records:
        st.info(t(
            "No tracked records yet. Use **➕ Add New** to start tracking a "
            "PO/style first — factory progress reports attach to tracked records."
        ))
        return

    pairs = [(r["po_number"], r.get("style") or "") for r in records]
    totals    = fp_store.totals_for_pairs(pairs)
    order_qty = fp_store.order_qty_for_pairs(pairs)
    last_date = fp_store.last_report_dates(pairs)

    # ── 1. Progress summary — units cut/sewn/packed vs ordered ──────────────
    st.subheader(f"📈 {t('Quantity progress')}")
    rows = []
    for r in records:
        key = (r["po_number"], r.get("style") or "")
        tot = totals.get(key, {s: 0 for s in REPORT_STAGES})
        oq = order_qty.get(key, 0)
        rows.append({
            "PO Number": key[0],
            "Style":     key[1] or "—",
            "Factory":   r.get("factory") or "—",
            "Ordered":   oq,
            "Cut":       tot["cutting"],
            "Sewn":      tot["sewing"],
            "Packed":    tot["packing"],
            "Packed %":  (tot["packing"] / oq) if oq else 0.0,
            "Last report": last_date.get(key, "") or "—",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df, width="stretch", hide_index=True,
        height=min(60 + 36 * len(df), 460),
        column_config={
            "PO Number": st.column_config.TextColumn(t("PO Number"), width="medium"),
            "Style":     st.column_config.TextColumn(t("Style"), width="small"),
            "Factory":   st.column_config.TextColumn(t("Factory"), width="medium"),
            "Ordered":   st.column_config.NumberColumn(t("Ordered"), format="%d"),
            "Cut":       st.column_config.NumberColumn(t("Cut"), format="%d"),
            "Sewn":      st.column_config.NumberColumn(t("Sewn"), format="%d"),
            "Packed":    st.column_config.NumberColumn(t("Packed"), format="%d"),
            "Packed %":  st.column_config.ProgressColumn(
                t("Packed %"), min_value=0.0, max_value=1.0, format="%.0f%%"),
            "Last report": st.column_config.TextColumn(t("Last report"), width="small"),
        },
    )
    # Over-report guard: cumulative beyond ordered qty is suspicious.
    for row in rows:
        over = [c for c in ("Cut", "Sewn", "Packed")
                if row["Ordered"] and row[c] > row["Ordered"]]
        if over:
            st.warning(
                f"⚠️ {row['PO Number']} / {row['Style']}: "
                + ", ".join(f"{c} {row[c]:,} > {t('ordered')} {row['Ordered']:,}"
                            for c in over)
                + " — " + t("check for a duplicate or cumulative-instead-of-new report.")
            )

    st.divider()

    # ── 2. Generate request form for one factory ────────────────────────────
    with st.expander(f"📤 {t('Generate request form for a factory')}", expanded=False):
        factories = sorted({r.get("factory") or "" for r in records if r.get("factory")})
        if not factories:
            st.info(t("No tracked record has a factory set — fill the Factory "
                      "field in ✏️ Edit Record first."))
        else:
            sel_factory = st.selectbox(t("Factory"), options=factories,
                                       key="pt_fu_form_factory")
            fac_rows = [
                {
                    "po_number": r["po_number"],
                    "style":     r.get("style") or "",
                    "order_qty": order_qty.get((r["po_number"], r.get("style") or ""), 0),
                    **{
                        {"cutting": "cut", "sewing": "sewn", "packing": "packed"}[s]:
                            totals.get((r["po_number"], r.get("style") or ""),
                                       {}).get(s, 0)
                        for s in REPORT_STAGES
                    },
                }
                for r in records if (r.get("factory") or "") == sel_factory
            ]
            st.caption(f"{len(fac_rows)} {t('PO/style row(s) for this factory')}")
            # Milestone rows: current expected/notes/completed per stage, so
            # the factory sees the plan and updates it on sheet 2.
            _fac_recs = [r for r in records
                         if (r.get("factory") or "") == sel_factory]
            _ms_rows = [
                {
                    "po_number": r["po_number"],
                    "style":     r.get("style") or "",
                    "stage":     _stage,
                    "expected":  r.get(f"{_stage}_planned") or "",
                    "note":      r.get(f"{_stage}_notes") or "",
                    "completed": r.get(f"{_stage}_actual") or "",
                }
                for r in _fac_recs
                for _stage, _lbl in MILESTONE_STAGES
            ]
            from datetime import date as _date
            st.download_button(
                f"⬇️ {t('Download request form')}",
                data=build_progress_request_xlsx(sel_factory, fac_rows,
                                                 milestones=_ms_rows),
                file_name=f"进度回报表_{sel_factory}_{_date.today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="pt_fu_form_download",
            )

    # ── 3. Import a returned form ───────────────────────────────────────────
    with st.expander(f"📥 {t('Import a returned form')}", expanded=False):
        up_factory = st.text_input(
            t("Factory this file came from"), key="pt_fu_import_factory",
            help=t("Stamped on every imported report row for the audit trail."),
        )
        uploaded = st.file_uploader(
            t("Returned progress form (.xlsx)"), type=["xlsx", "xlsm"],
            key="pt_fu_import_file", label_visibility="collapsed",
        )
        if uploaded is not None:
            try:
                parsed = parse_progress_report_xlsx(uploaded.getvalue(),
                                                    factory=up_factory.strip())
            except ValueError as exc:
                st.error(str(exc))
            else:
                reports = parsed["reports"]
                milestones = parsed.get("milestones") or []
                for issue in parsed["issues"]:
                    st.warning(f"⚠️ {issue}")
                if milestones:
                    st.markdown(f"**{t('Milestone updates in this file')}** ({len(milestones)})")
                    ms_prev = pd.DataFrame([{
                        "PO Number": m["po_number"], "Style": m["style"],
                        "Milestone": MILESTONE_LABELS.get(m["stage"], m["stage"]),
                        "Expected": m["expected"] or "—",
                        "Note": m["note"] or "—",
                        "Completed": m["completed"] or "—",
                    } for m in milestones])
                    st.dataframe(ms_prev, width="stretch", hide_index=True,
                                 height=min(60 + 36 * len(ms_prev), 350))
                if not reports and not milestones:
                    st.info(t("No new quantities found in this file."))
                else:
                    prev = pd.DataFrame([{
                        "PO Number": rp["po_number"], "Style": rp["style"],
                        "Stage": REPORT_STAGE_LABELS.get(rp["stage"], rp["stage"]),
                        "Units": rp["units"], "Date": rp["report_date"],
                        "Notes": rp["notes"],
                    } for rp in reports])
                    st.dataframe(prev, width="stretch", hide_index=True)
                    # Warn on rows for PO/styles that aren't tracked (typo guard).
                    tracked = {(r["po_number"], r.get("style") or "") for r in records}
                    unknown = {(rp["po_number"], rp["style"]) for rp in reports} - tracked
                    for po, sty in sorted(unknown):
                        st.warning(f"⚠️ {po} / {sty or '—'} — "
                                   + t("not a tracked PO/style (import anyway if intentional)."))
                    _btn_label = (
                        f"✅ {t('Import')} {len(reports)} {t('report(s)')}"
                        + (f" + {len(milestones)} {t('milestone update(s)')}"
                           if milestones else "")
                    )
                    if st.button(_btn_label, type="primary", key="pt_fu_import_go"):
                        n = 0
                        for rp in reports:
                            try:
                                fp_store.add_report(
                                    rp["po_number"], rp["style"], rp["stage"],
                                    rp["report_date"], rp["units"],
                                    factory=rp["factory"], source="excel",
                                    notes=rp["notes"], created_by=username,
                                )
                                n += 1
                            except ValueError as exc:
                                st.error(f"{rp['po_number']} / {rp['style']}: {exc}")
                        # Milestone updates -> production_tracking stage fields.
                        # Completing a milestone (完成日期 filled) marks the
                        # stage Done with that actual date.
                        pt_store = get_production_tracking_store()
                        n_ms = 0
                        for m in milestones:
                            fields: dict = {}
                            if m["expected"]:
                                fields[f"{m['stage']}_planned"] = m["expected"]
                            if m["note"]:
                                fields[f"{m['stage']}_notes"] = m["note"]
                            if m["completed"]:
                                fields[f"{m['stage']}_actual"] = m["completed"]
                                fields[f"{m['stage']}_status"] = "Done"
                            try:
                                if pt_store.update_stage_fields(
                                    m["po_number"], m["style"], fields,
                                    updated_by=username,
                                ):
                                    n_ms += 1
                                else:
                                    st.warning(
                                        f"⚠️ {m['po_number']} / {m['style']} — "
                                        + t("not tracked; milestone update skipped."))
                            except ValueError as exc:
                                st.error(f"{m['po_number']} / {m['style']}: {exc}")
                        st.success(
                            f"✅ {n} {t('report(s) imported.')}"
                            + (f" {n_ms} {t('milestone update(s) applied.')}"
                               if milestones else "")
                        )
                        fragment_rerun()

    # ── 3.5 Milestones editor — the buy plan Index tab's tracking fields ────
    # Expected completion date + status note per milestone, and marking a
    # milestone complete/arrived (fills the actual date, status -> Done).
    # Written to production_tracking, so populated values flow straight into
    # the Sky East buy plan's Index columns on the next generation.
    with st.expander(f"📋 {t('Milestones (buy plan tracking fields)')}", expanded=False):
        def _fmt_ms_rec(idx: int) -> str:
            r = records[idx]
            return f"{r['po_number']} — {r.get('style') or '—'}"

        ms_idx = st.selectbox(
            t("PO / Style"), options=range(len(records)),
            format_func=_fmt_ms_rec, key="pt_fu_ms_rec",
        )
        ms_rec = records[ms_idx]
        _rid_key = f"{ms_rec['po_number']}|{ms_rec.get('style') or ''}"

        def _to_date(v):
            s = str(v or "").strip()
            try:
                return date.fromisoformat(s) if s else None
            except ValueError:
                return None

        ms_df = pd.DataFrame([{
            "milestone": _lbl,
            "expected":  _to_date(ms_rec.get(f"{_stage}_planned")),
            "note":      ms_rec.get(f"{_stage}_notes") or "",
            "completed": _to_date(ms_rec.get(f"{_stage}_actual")),
        } for _stage, _lbl in MILESTONE_STAGES])
        edited_ms = st.data_editor(
            ms_df, hide_index=True, width="stretch", num_rows="fixed",
            disabled=["milestone"],
            key=f"pt_fu_ms_editor_{_rid_key}",
            column_config={
                "milestone": st.column_config.TextColumn(t("Milestone"), width="medium"),
                "expected":  st.column_config.DateColumn(t("Expected date")),
                "note":      st.column_config.TextColumn(t("Status note"), width="large"),
                "completed": st.column_config.DateColumn(t("Completed (arrived)")),
            },
        )
        st.caption(t(
            "Fill **Completed** to mark a milestone done/arrived — its stage "
            "is set to Done. These fields appear in the buy plan's Index tab "
            "and in the factory request form's 里程碑 sheet."
        ))
        if st.button(f"💾 {t('Save milestones')}", type="primary",
                     key=f"pt_fu_ms_save_{_rid_key}"):
            fields: dict = {}
            for i, (_stage, _lbl) in enumerate(MILESTONE_STAGES):
                row = edited_ms.iloc[i]
                exp, comp = row["expected"], row["completed"]
                fields[f"{_stage}_planned"] = (
                    exp.isoformat() if hasattr(exp, "isoformat") and pd.notna(exp) else "")
                fields[f"{_stage}_notes"] = str(row["note"] or "")
                if pd.notna(comp) and comp is not None:
                    fields[f"{_stage}_actual"] = comp.isoformat()
                    fields[f"{_stage}_status"] = "Done"
                else:
                    fields[f"{_stage}_actual"] = ""
                    # Un-completing a previously Done milestone downgrades it,
                    # so the status can't claim Done with no completion date.
                    if (ms_rec.get(f"{_stage}_status") or "") == "Done":
                        fields[f"{_stage}_status"] = "In Progress"
            pt_store = get_production_tracking_store()
            pt_store.update_stage_fields(
                ms_rec["po_number"], ms_rec.get("style") or "", fields,
                updated_by=username,
            )
            st.success(f"✅ {t('Milestones saved.')}")
            fragment_rerun()

    # ── 4. Manual entry (phone/WeChat reports keyed in by your own staff) ───
    with st.expander(f"✍️ {t('Manual entry')}", expanded=False):
        def _fmt_rec(idx: int) -> str:
            r = records[idx]
            return f"{r['po_number']} — {r.get('style') or '—'}"

        idx = st.selectbox(
            t("PO / Style"), options=range(len(records)),
            format_func=_fmt_rec, key="pt_fu_manual_rec",
        )
        rec = records[idx]
        c1, c2, c3 = st.columns(3)
        with c1:
            stage = st.selectbox(
                t("Stage"), options=REPORT_STAGES,
                format_func=lambda s: REPORT_STAGE_LABELS.get(s, s),
                key="pt_fu_manual_stage",
            )
        with c2:
            units = st.number_input(t("Units (new since last report)"),
                                    min_value=1, step=1, value=1,
                                    key="pt_fu_manual_units")
        with c3:
            rdate = st.date_input(t("Report date"), key="pt_fu_manual_date")
        note = st.text_input(t("Notes"), key="pt_fu_manual_note")
        if st.button(f"➕ {t('Add report')}", type="primary", key="pt_fu_manual_add"):
            fp_store.add_report(
                rec["po_number"], rec.get("style") or "", stage,
                rdate.isoformat(), int(units),
                factory=rec.get("factory") or "", source="manual",
                notes=note, created_by=username,
            )
            st.success(f"✅ {t('Report added.')}")
            fragment_rerun()

    # ── 5. Recent reports + correction (delete) ─────────────────────────────
    with st.expander(f"🗂 {t('Recent reports')}", expanded=False):
        recent = fp_store.list_reports(limit=200)
        if not recent:
            st.info(t("No reports yet."))
        else:
            rec_df = pd.DataFrame([{
                "id":        rp["id"],
                "PO Number": rp["po_number"],
                "Style":     rp["style"] or "—",
                "Factory":   rp["factory"] or "—",
                "Stage":     REPORT_STAGE_LABELS.get(rp["stage"], rp["stage"]),
                "Units":     rp["units"],
                "Date":      rp["report_date"],
                "Source":    rp["source"],
                "By":        rp["created_by"] or "—",
                "Notes":     rp["notes"] or "",
            } for rp in recent])
            st.dataframe(rec_df.drop(columns=["id"]), width="stretch",
                         hide_index=True, height=min(60 + 36 * len(rec_df), 400))
            if admin_mode:
                guard_multiselect_state("pt_fu_del_sel", rec_df["id"].tolist())
                del_ids = st.multiselect(
                    t("Delete report(s) — corrections only"),
                    options=rec_df["id"].tolist(),
                    format_func=lambda i: (
                        lambda row: f"#{i} · {row['PO Number']} {row['Style']} "
                                    f"{row['Stage']} {row['Units']} ({row['Date']})"
                    )(rec_df[rec_df["id"] == i].iloc[0]),
                    key="pt_fu_del_sel",
                )
                if del_ids and st.button(
                    f"🗑 {t('Delete')} {len(del_ids)}", key="pt_fu_del_go",
                ):
                    fp_store.delete_reports(del_ids)
                    st.session_state.pop("pt_fu_del_sel", None)
                    fragment_rerun()
