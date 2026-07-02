"""Streamlit view for the 🏭 Production Tracking tab.

This module is built incrementally:
  - **Stage 4**: navigation shell, access-control gate, metrics row,
    placeholder panels.
  - **Stage 5 (current)**: Add New workflow.
  - **Stage 6 (current)**: Edit Record workflow.
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

import streamlit as st

from ui.i18n import t
from ui.session_keys import SK
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
]

# Indexes used by the dashboard Edit shortcut and similar cross-panel jumps.
TAB_DASHBOARD = 0
TAB_OVERVIEW  = 1
TAB_EDIT      = 2
TAB_ADD       = 3
TAB_PLAN      = 4


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
    h1.caption("**Stage**")
    h2.caption("**Status**")
    h3.caption("**Planned**")
    h4.caption("**Actual**")
    h5.caption("**Exp.Days**")
    h6.caption("**Notes**")


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
    default_labels = [
        STAGE_LABELS[t]
        for t in targets
        if record.get(dep_col(stage, t), 0)
    ]

    selected = st.multiselect(
        "Required for:",
        options=list(label_to_key.keys()),
        default=default_labels,
        key=_wkey(rid, f"dep_{stage}"),
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
        st.success(f"✅ **{label}** — Ready")
    elif readiness.startswith("waiting"):
        waiting_on = readiness[len("waiting:"):]
        st.warning(f"⏳ **{label}** — Waiting on: {waiting_on}")
    else:  # no_prereqs
        st.info(f"⚪ **{label}** — No prerequisites set")


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
        f"🧵 Group A — Pre-Production (Parallel) · {_done}/{_total} ✅",
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

    with st.expander("Optional Samples", expanded=any_applicable):
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
                selected = st.multiselect(
                    "Required for:",
                    options=[pp_label],
                    default=[pp_label] if is_dep else [],
                    key=_wkey(rid, f"dep_{stage}_pp"),
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
    st.subheader(f"🧪 Group B — Samples · {_done}/{_total} ✅")

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
        f"🏭 Group C — Production (Sequential) · {_done}/{_total} ✅",
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
        f"📦 Group D — Post-Production · {_done}/{_total} ✅",
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
            for t in targets:
                col = dep_col(source, t)
                fields[col] = record.get(col, 0)
        else:
            for t in targets:
                fields[dep_col(source, t)] = 1 if t in selected_targets else 0

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
        _render_add_tab(store, po_store, username, user_cos=user_cos, admin_mode=admin_mode)
    elif active_label == _TAB_LABELS[TAB_PLAN]:
        _render_plan_tab(records, store)


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
# Dashboard tab — Stage 7 placeholder
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


# ─────────────────────────────────────────────────────────────────────────────
# Overview table — Stage 7 placeholder
# ─────────────────────────────────────────────────────────────────────────────

def _render_overview_table(records, readiness_map, reminder_map, today) -> None:
    """Stage 7 will render the wide emoji-badge table."""
    if not records:
        st.info("No tracked records yet.")
        return
    st.caption(
        f"📋 Overview placeholder — {len(records)} record(s) loaded. "
        "Full table lands in Stage 7."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Edit Record tab — Stage 6
# ─────────────────────────────────────────────────────────────────────────────

def _render_edit_tab(records, readiness_map, store, username, today) -> None:
    """Full edit form for an existing tracking record."""
    if not records:
        st.info("No tracked records yet. Use **➕ Add New** first.")
        return

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

    record = id_to_record[selected_id]
    rid    = selected_id
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
        "Overall Notes",
        value=overall_notes_val,
        key=_wkey(rid, "overall_notes"),
    )

    st.divider()

    # ── Stage sections ───────────────────────────────────────────────────────
    st.caption(t(
        "Stage groups: 🧵 **A** pre-production prep (parallel) · 🧪 **B** samples · "
        "🏭 **C** production (sequential) · 📦 **D** post-production/shipping. "
        "Fully-completed groups are collapsed — open them to review."
    ))
    _render_group_a_section(record, rid, readiness)
    _render_pp_sample_section(record, rid, readiness["pp_sample"])
    _render_group_c_section(record, rid, readiness["cutting"])
    _render_group_d_section(record, rid)

    # ── QC section ───────────────────────────────────────────────────────────
    _render_qc_section(record, rid, reminders)

    st.divider()

    # ── Save / Delete buttons ────────────────────────────────────────────────
    col_save, col_del = st.columns(2)

    with col_save:
        if st.button("💾 Save", type="primary", use_container_width=True):
            _do_save(record, store, username, rid)
            st.rerun()

    with col_del:
        if st.button("🗑️ Delete", use_container_width=True):
            st.session_state[SK.PT_DELETE_CONFIRM] = True

    if st.session_state.get(SK.PT_DELETE_CONFIRM):
        st.warning(
            f"⚠️ Delete **{record['po_number']}** "
            f"({'Style: ' + record['style'] if record.get('style') else 'no style'})? "
            "This cannot be undone."
        )
        if st.button("✅ Confirm Delete", type="primary"):
            store.delete([rid])
            st.session_state[SK.PT_DELETE_CONFIRM] = False
            st.session_state[SK.PT_SELECTED_EDIT]  = None
            st.success("Record deleted.")
            st.rerun()
        if st.button("Cancel"):
            st.session_state[SK.PT_DELETE_CONFIRM] = False
            st.rerun()


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
        st.info("All POs are already being tracked.")
        return

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
        "Select PO / Style to start tracking",
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
    overall_notes_val = st.text_area("Overall Notes", value="", key="pt_add_notes")

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
            for t in targets:
                col = dep_col(source, t)
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
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Plan tab — Stage 8 placeholder
# ─────────────────────────────────────────────────────────────────────────────

def _render_plan_tab(records, store) -> None:
    """Stage 8 will render the planning what-if interface."""
    if not records:
        st.info("No tracked records yet — nothing to plan.")
        return
    st.caption(
        f"📅 Plan placeholder — {len(records)} record(s) available. "
        "Schedule calculator lands in Stage 8."
    )
