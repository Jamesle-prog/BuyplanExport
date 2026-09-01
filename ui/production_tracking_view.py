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

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from ui.i18n import t
from ui.session_keys import SK
from ui.shared import lazy_sections, fragment_rerun, guard_multiselect_state, XLSX_MIME, show_flash, delete_button
from ui.stores import get_production_tracking_store, get_store

# ── Schema constants — imported once at module load, not on every render ──────
# Keeping these at module level avoids repeated sys.modules lookups inside the
# many small render functions that previously used local `from … import` calls.
from po_extractor.store._factory_progress_schema import (
    MILESTONE_STAGES, MILESTONE_LABELS,
)
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
    "📅 Tracking Grid",
    "➕ Add / Remove",
    "📨 Factory Updates",
]

# Indexes used for cross-panel jumps (e.g. Add → back to the grid).
TAB_GRID    = 0
TAB_ADD     = 1
TAB_FACTORY = 2

# Grid date modes — which per-stage column the 9 date columns bind to.
GRID_PLANNED = "planned"
GRID_ACTUAL  = "actual"


# ── Access scope ──────────────────────────────────────────────────────────────

class TrackScope:
    """What the current user may see and change in the tracking module.

    Built once per render in ``show_production_tracking_tab`` and threaded
    into every panel so access control lives in ONE place, enforced on the
    server side (not just by hiding widgets). Three shapes:

      - **admin** — unrestricted.
      - **client-scoped** — a normal user limited to their companies. Sees
        and edits only their companies' rows; imports that name an
        out-of-scope PO/style are rejected.
      - **factory-scoped** (``factory_mode``) — a factory login limited to
        specific factories. Sees only those factories' rows and may record
        **progress only**: actual/completion dates, quantity reports and
        status notes — never planned dates, and never add/remove rows.

    ``allowed_keys`` is the set of ``(po_number, style)`` the user may touch;
    every apply path checks :meth:`permits` before writing, so a crafted
    upload can't reach a row outside scope.
    """

    def __init__(self, admin: bool, factory_mode: bool, allowed_keys):
        self.admin = admin
        self.factory_mode = factory_mode
        self.allowed_keys = allowed_keys        # frozenset[(po, style)]

    def permits(self, po_number: str, style: str) -> bool:
        if self.admin:
            return True
        return ((str(po_number or "").strip(), str(style or "").strip())
                in self.allowed_keys)

    def sanitize_fields(self, fields: dict) -> dict:
        """Drop writes a factory user isn't allowed to make (planned dates).
        Client/admin scopes pass through unchanged."""
        if not self.factory_mode:
            return fields
        return {k: v for k, v in fields.items() if not k.endswith("_planned")}

    @property
    def can_edit_planned(self) -> bool:
        return not self.factory_mode

    @property
    def can_add_remove(self) -> bool:
        return not self.factory_mode


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
            t("Status"),
            STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0,
            key=_wkey(rid, f"{stage}_status"),
            label_visibility="collapsed",
        )

    with col3:
        planned_val = _parse_date(record.get(f"{stage}_planned"))
        st.date_input(
            t("Planned"),
            value=planned_val,
            key=_wkey(rid, f"{stage}_planned"),
            label_visibility="collapsed",
        )

    with col4:
        actual_val = _parse_date(record.get(f"{stage}_actual"))
        st.date_input(
            t("Actual"),
            value=actual_val,
            key=_wkey(rid, f"{stage}_actual"),
            label_visibility="collapsed",
        )

    with col5:
        exp_days = record.get(f"{stage}_expected_days")
        st.number_input(
            t("Exp.Days"),
            min_value=0,
            step=1,
            value=int(exp_days) if exp_days is not None else 0,
            key=_wkey(rid, f"{stage}_expected_days"),
            label_visibility="collapsed",
        )

    with col6:
        notes_val = record.get(f"{stage}_notes") or ""
        st.text_input(
            t("Notes"),
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
        t("Required for:"),
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
                t("Include {stage}").format(stage=STAGE_LABELS[stage]),
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
                    t("Required for:"),
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
        t("🔄 Use Substitute Materials for Samples"),
        value=bool(record.get("use_substitute_materials", 1)),
        key=_wkey(rid, "use_substitute_materials"),
        help=(
            t("ON: Sample Trim/Fabric Purchase gate samples; bulk Group A "
            "runs in parallel.\n"
            "OFF: All bulk Group A stages must be Done before any sample starts.")
        ),
    )
    if use_sub:
        st.info(
            t("🔄 Substitute mode: Sample Trim/Fabric Purchase gate samples. "
            "Bulk confirmations run in parallel.")
        )
    else:
        st.warning(
            t("⚠️ Confirmed materials mode: Trim Purchase, Trim Layout, "
            "Fabric Purchase, and Fabric Color (LD) must all be Done before "
            "any sample can start.")
        )

    _render_optional_samples_section(record, rid)

    st.markdown(t("#### PP Sample *(Compulsory)*"))
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
        st.markdown(t("#### Cutting"))
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
    st.subheader(t("🔍 QC Inspections"))
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
                    t("🔁 Re-Final Inspection — appears when Final result is 'Fail'")
                )
                continue

        st.markdown(f"#### {label}")

        if key in reminder_map:
            rem = reminder_map[key]
            if rem["overdue"]:
                st.error(t("⚠️ Booking OVERDUE — deadline was {date}").format(date=rem['deadline']))
            else:
                st.warning(t("⚠️ Book by {date} — reminder triggered").format(date=rem['deadline']))

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
    st.success(t("✅ Record saved."))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def show_production_tracking_tab(
    user_cos: list[str],
    username: str,
    admin_mode: bool,
    user_factories: list[str] | None = None,
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
    user_factories
        Factory strings this user is restricted to (a "factory login").
        Empty/None = not factory-restricted. A factory user sees only these
        factories' rows and may record progress only. Ignored for admins.
    """
    store    = get_production_tracking_store()
    po_store = get_store()
    today    = date.today()
    user_factories = user_factories or []
    factory_mode = bool(user_factories) and not admin_mode

    # ── Access control gate ────────────────────────────────────────────────
    # A user needs SOME scope: admin, a company, or a factory. Without any,
    # they see nothing (never let admin status leak through list_all's
    # no-filter path).
    if not admin_mode and not user_cos and not factory_mode:
        st.info(t(
            "No companies assigned to your account. "
            "Contact an administrator to be granted access."
        ))
        return

    # Fetch within company scope (admins and factory-only users with no
    # company restriction get everything), then narrow to the user's
    # factories. A factory user is scoped by factory, which can span clients,
    # so an empty company list does NOT mean "nothing" for them.
    if admin_mode or not user_cos:
        records = store.list_all(allow_all=True)
    else:
        records = store.list_all(companies=user_cos)

    if factory_mode:
        # Resolve through the factory dictionary so one assignment (a canonical
        # factory) covers every client-specific spelling of it. Falls back to
        # exact-string match when the name isn't in the dictionary yet.
        from po_extractor.store import get_factory_registry_store
        from po_extractor.store.factory_registry_store import norm as _fac_norm
        allowed_norm = get_factory_registry_store().scope_norms_for_names(
            user_factories)
        records = [r for r in records
                   if _fac_norm(r.get("factory") or "") in allowed_norm]

    allowed_keys = frozenset(
        ((r.get("po_number") or "").strip(), (r.get("style") or "").strip())
        for r in records
    )
    scope = TrackScope(admin=admin_mode, factory_mode=factory_mode,
                       allowed_keys=allowed_keys)

    if factory_mode:
        st.caption("🏭 " + t("Factory view — you see only your factory's "
                             "orders and record progress against them.")
                   + f"  ({', '.join(user_factories)})")

    # ── Top metrics row ────────────────────────────────────────────────────
    _render_metrics(records, today)

    # ── Sub-tab navigation (st.radio with session-state-controlled index) ──
    # Factory users don't get Add / Remove — they can't create or delete
    # tracking rows, only report progress. Build the visible tab list from
    # capability, and dispatch by (stable English) label.
    tab_defs = [(_TAB_LABELS[TAB_GRID], "grid")]
    if scope.can_add_remove:
        tab_defs.append((_TAB_LABELS[TAB_ADD], "add"))
    tab_defs.append((_TAB_LABELS[TAB_FACTORY], "factory"))
    labels = [lbl for lbl, _ in tab_defs]

    _stored = st.session_state.get(SK.PT_ACTIVE_TAB, TAB_GRID)
    if not isinstance(_stored, int) or not 0 <= _stored < len(_TAB_LABELS):
        _stored = TAB_GRID
    # Map the stored full-layout index onto the (possibly reduced) label list.
    _stored_label = _TAB_LABELS[_stored]
    index = labels.index(_stored_label) if _stored_label in labels else 0
    active_label = st.radio(
        t("Sub-section"), labels, horizontal=True, index=index,
        key=SK.PT_TAB_RADIO, format_func=t, label_visibility="collapsed",
    )
    st.session_state[SK.PT_ACTIVE_TAB] = _TAB_LABELS.index(active_label)
    which = dict(tab_defs)[active_label]

    st.divider()

    # ── Dispatch ───────────────────────────────────────────────────────────
    if which == "grid":
        _render_grid_tab(records, store, po_store, username, today,
                         admin_mode, user_cos, scope)
    elif which == "add":
        _render_add_tab(store, po_store, username, user_cos=user_cos,
                        admin_mode=admin_mode, records=records)
    elif which == "factory":
        _render_factory_updates_tab(records, username, admin_mode, scope)


# ─────────────────────────────────────────────────────────────────────────────
# Metrics row
# ─────────────────────────────────────────────────────────────────────────────

def _render_metrics(records, today) -> None:
    """Three summary metrics, all about the 9 tracked milestones.

    Deliberately NOT about the 22-stage model: the simplified surface only
    surfaces what the buy plan's Index tab shows, so counts must agree with
    what the user sees in the grid.
    """
    total = len(records)
    done = sum(
        1 for r in records for s, _ in MILESTONE_STAGES
        if (r.get(f"{s}_actual") or "").strip()
    )
    today_iso = today.isoformat()
    overdue_rows = [
        f"{r.get('po_number', '')} · {r.get('style', '')} — "
        f"{MILESTONE_LABELS.get(s, s)} "
        f"({t('planned')} {(r.get(f'{s}_planned') or '').strip()})"
        for r in records for s, _ in MILESTONE_STAGES
        if (r.get(f"{s}_planned") or "").strip()
        and not (r.get(f"{s}_actual") or "").strip()
        and (r.get(f"{s}_planned") or "").strip() < today_iso
    ]
    overdue = len(overdue_rows)

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    c1.metric(t("Tracked"),         f"{total:,}")
    c2.metric(t("Milestones done"), f"{done:,}")
    c3.metric(t("Overdue"),         f"{overdue:,}")
    # Overdue mail is sent on request, not on a timer: an automatic daily
    # digest would arrive whether or not anyone was looking at the plan.
    with c4:
        if overdue and st.button(f"📧 {t('Email the overdue list')}",
                                 key="pt_notify_overdue"):
            from po_extractor.utils.notifications import notify_milestones_overdue
            st.caption(notify_milestones_overdue(overdue_rows))


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


def _jump_to_advanced(rid: int) -> None:
    """Navigate to the grid tab with *rid* pre-selected in the Advanced
    editor — the radio's own widget key must be POPPED, not overwritten
    (Streamlit ignores `index=` once the key holds a value)."""
    st.session_state[SK.PT_SELECTED_EDIT] = rid
    st.session_state[SK.PT_ACTIVE_TAB]    = TAB_GRID
    st.session_state.pop(SK.PT_TAB_RADIO, None)
    fragment_rerun()


def _render_progress_filters(
    records: list[dict], key_prefix: str,
) -> list[dict]:
    """Company / factory / search filter row, applied to *records*.

    *key_prefix* scopes widget keys per caller so separate panels keep
    independent selections rather than fighting over one shared key.
    """
    companies = _all_companies(records)
    factories = _all_factories(records)

    c1, c2, c3 = st.columns([2, 2, 3])
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
        search = st.text_input(
            t("Search PO / style"), key=SK.PT_GRID_SEARCH,
            placeholder=t("type to filter…"),
        ).strip().lower()

    out = []
    for r in records:
        if sel_companies and (r.get("company") or "") not in sel_companies:
            continue
        if sel_factories and (r.get("factory") or "") not in sel_factories:
            continue
        # Styles keep their file spelling; matching treats "/" as "_" on
        # both sides, so either spelling typed finds either spelling stored.
        if search and search.replace("/", "_") not in (
            f"{r.get('po_number', '')} {r.get('style') or ''}"
            .lower().replace("/", "_")
        ):
            continue
        out.append(r)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Tracking Grid — the one-page view (mirrors the buy plan's Index tab)
# ─────────────────────────────────────────────────────────────────────────────
#
# Rows = tracked PO/styles, columns = the 9 MILESTONE_STAGES, i.e. exactly the
# milestone block of the Sky East buy plan Index sheet. One date column per
# milestone bound to EITHER {stage}_planned or {stage}_actual via a mode
# toggle -- 18 columns (both at once) does not fit a screen, and a single
# merged column would make "is this a plan or a fact?" ambiguous.

_GRID_META_COLS = ["PO Number", "Style", "Factory"]


def _grid_dataframe(records: list[dict], mode: str) -> pd.DataFrame:
    """Build the editable grid frame: meta columns + one date column per
    milestone (bound to *mode*) + a read-only done-count.

    Pure — no Streamlit — so the column contract is unit-testable.
    """
    rows = []
    for r in records:
        row = {
            "PO Number": r.get("po_number", ""),
            "Style":     r.get("style") or "",
            "Factory":   r.get("factory") or "",
        }
        done = 0
        for stage, label in MILESTONE_STAGES:
            row[label] = _parse_date(r.get(f"{stage}_{mode}"))
            if (r.get(f"{stage}_actual") or "").strip():
                done += 1
        row["Done"] = f"{done}/{len(MILESTONE_STAGES)}"
        rows.append(row)
    cols = _GRID_META_COLS + [lbl for _, lbl in MILESTONE_STAGES] + ["Done"]
    return pd.DataFrame(rows, columns=cols)


def _status_strip_df(records: list[dict], today: date | None = None) -> pd.DataFrame:
    """Read-only completion strip, one symbol per milestone:

    ✅ done · 🔴 overdue (planned date passed, nothing recorded) ·
    🟠 due within 7 days · 📅 scheduled later · ⬜ not scheduled.

    Shows where attention is needed while the editor below shows the dates.
    """
    today = today or date.today()
    soon = today + timedelta(days=7)
    rows = []
    for r in records:
        row = {"PO Number": r.get("po_number", ""), "Style": r.get("style") or ""}
        for stage, label in MILESTONE_STAGES:
            actual = (r.get(f"{stage}_actual") or "").strip()
            planned = (r.get(f"{stage}_planned") or "").strip()
            if actual:
                row[label] = "✅"
            elif not planned:
                row[label] = "⬜"
            else:
                due = _parse_date(planned)
                if due is None:
                    row[label] = "📅"
                elif due < today:
                    row[label] = "🔴"
                elif due <= soon:
                    row[label] = "🟠"
                else:
                    row[label] = "📅"
        rows.append(row)
    return pd.DataFrame(
        rows, columns=["PO Number", "Style"] + [lbl for _, lbl in MILESTONE_STAGES]
    )


def _grid_diff(original: pd.DataFrame, edited: pd.DataFrame, mode: str,
               records: list[dict]) -> dict:
    """Cell-level diff → ``{(po, style): {column: value}}`` for
    ``update_stage_fields``.

    Only CHANGED cells are emitted, so an untouched row never writes. In
    ACTUAL mode a filled date also marks the stage Done, and clearing a date
    on a previously-Done stage downgrades it to In Progress -- the status can
    never claim Done without a completion date (same rule the Milestones
    editor used).
    """
    by_key = {
        (r.get("po_number", ""), r.get("style") or ""): r for r in records
    }
    out: dict = {}
    for i in range(min(len(original), len(edited))):
        o_row, e_row = original.iloc[i], edited.iloc[i]
        key = (str(e_row["PO Number"]), str(e_row["Style"]))
        rec = by_key.get(key, {})
        fields: dict = {}
        for stage, label in MILESTONE_STAGES:
            o_val, e_val = o_row[label], e_row[label]
            if _date_str(o_val) == _date_str(e_val):
                continue
            val = _date_str(e_val)
            fields[f"{stage}_{mode}"] = val
            if mode == GRID_ACTUAL:
                if val:
                    fields[f"{stage}_status"] = "Done"
                elif (rec.get(f"{stage}_status") or "") == "Done":
                    fields[f"{stage}_status"] = "In Progress"
        if fields:
            out[key] = fields
    return out


def _date_str(v) -> str:
    """Normalise a grid cell (date / Timestamp / str / NaT / None) to a plain
    ``YYYY-MM-DD`` string or '' — the storage format of every *_planned /
    *_actual column, and what the buy plan Index prints.

    The ``.date()`` call is essential: ``pd.Timestamp`` (what data_editor
    hands back) IS a ``datetime.date`` subclass, so an isinstance guard would
    skip it and store ``2026-08-01T00:00:00`` instead of ``2026-08-01``.
    ``datetime.date`` itself has no ``.date`` attribute, so it falls through
    untouched.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if hasattr(v, "date"):
        try:
            v = v.date()
        except (TypeError, ValueError):
            pass
    return v.isoformat() if hasattr(v, "isoformat") else str(v).strip()


def _ex_factory_for(record: dict, anchors: dict) -> str:
    """Best ex-factory date for a record: the client PO's own 离厂时间 when
    we have it, else the 工厂交期 already planned on the record. Falls back
    to a PO-only match so a style-name mismatch between the order file and
    the tracking record doesn't lose the anchor."""
    po = record.get("po_number", "")
    sty = record.get("style") or ""
    return (
        anchors.get((po, sty))
        or anchors.get((po, ""))
        or (record.get("shipping_planned") or "")
    ).strip()


def _exfty_anchor_map() -> dict:
    """``{(po_number, style): ex_factory_date}`` unioned across BOTH client
    pipelines — Sky East items' 离厂时间 and GIII's factory_ship_date /
    xport_date — because tracking records come from both. A ``(po, "")``
    entry is also stored so a PO-only lookup still resolves.

    Best-effort: a failure in either source yields fewer anchors, never an
    error (auto-plan then falls back to the record's own 工厂交期).
    """
    out: dict = {}

    def _put(po: str, sty: str, raw) -> None:
        from po_extractor.utils.lead_times import parse_anchor_date
        d = parse_anchor_date(raw)
        if not po or d is None:
            return
        out.setdefault((po, sty), d.isoformat())
        out.setdefault((po, ""), d.isoformat())

    try:                                    # Sky East — client PO 离厂时间
        from ui.stores import get_sky_east_store
        df = get_sky_east_store().list_items()
        if df is not None and not df.empty and "ex_fty_date" in df.columns:
            for _, r in df.iterrows():
                _put(str(r.get("zalando_po") or "").strip(),
                     str(r.get("style") or "").strip(),
                     r.get("ex_fty_date"))
    except Exception:
        pass

    try:                                    # GIII — factory ship / export date
        import sqlite3 as _sq
        conn = _sq.connect(get_store().db_path)
        conn.row_factory = _sq.Row
        try:
            for r in conn.execute(
                "SELECT po_number, style, factory_ship_date, xport_date "
                "FROM po_metadata"
            ).fetchall():
                _put(str(r["po_number"] or "").strip(),
                     str(r["style"] or "").strip(),
                     r["factory_ship_date"] or r["xport_date"])
        finally:
            conn.close()
    except Exception:
        pass

    return out


def _render_autoplan_section(records, store, username, today) -> None:
    """Draft nine milestone dates from ONE date, plus the bulk shortcuts.

    Backward (倒推) counts back from each style's 离厂时间; forward (正推)
    counts on from a start date. Both use the same offsets table, so the two
    directions can never disagree — see po_extractor/utils/lead_times.py.
    """
    from po_extractor.utils.lead_times import (
        MILESTONE_STAGES as _MS,          # same order as the grid
        load_lead_days, save_lead_days, plan_backward, plan_forward,
        shift_plan, cycle_length,
    )

    with st.expander(f"🗓 {t('Auto-plan & bulk edits')}", expanded=False):
        lead_days = load_lead_days()

        by_label = {
            f"{r['po_number']} — {r.get('style') or '—'}": r for r in records
        }
        guard_multiselect_state("pt_autoplan_rows", list(by_label))
        chosen_labels = st.multiselect(
            t("Apply to which PO / styles?"), options=list(by_label),
            key="pt_autoplan_rows",
            help=t("Leave empty to apply to every row currently shown."),
        )
        targets = ([by_label[c] for c in chosen_labels] if chosen_labels
                   else list(records))
        st.caption(f"{len(targets)} {t('row(s) selected')}")

        # Only the selected panel is built (st.tabs ran all three).

        # ── Draft a plan ───────────────────────────────────────────────────
        def _plan_panel():
            direction = st.radio(
                t("Direction"),
                ["backward", "forward"],
                horizontal=True, key="pt_autoplan_dir",
                format_func=lambda d: (t("倒推 Back from 离厂时间")
                                       if d == "backward"
                                       else t("正推 Forward from a start date")),
                label_visibility="collapsed",
            )
            anchors = _exfty_anchor_map() if direction == "backward" else {}
            start_date = None
            if direction == "forward":
                start_date = st.date_input(t("Production start date"),
                                           value=today, key="pt_autoplan_start")
                st.caption(
                    f"{t('Implied 离厂时间')}: "
                    f"{(start_date + timedelta(days=cycle_length(lead_days))).isoformat()}"
                )

            overwrite = st.checkbox(
                t("Overwrite dates that are already filled"),
                key="pt_autoplan_overwrite",
                help=t("Off (default): only empty milestones are filled, so "
                       "hand-tuned dates survive."),
            )

            preview_rows, jobs = [], []
            for rec in targets:
                if direction == "backward":
                    anchor = _ex_factory_for(rec, anchors)
                    anchor_date = _parse_date(anchor)
                    if anchor_date is None:
                        preview_rows.append({
                            "PO Number": rec["po_number"],
                            "Style": rec.get("style") or "",
                            "Anchor": "—",
                            "Result": t("no 离厂时间 on file — skipped"),
                        })
                        continue
                    plan = plan_backward(anchor_date, lead_days)
                    anchor_txt = anchor_date.isoformat()
                else:
                    plan = plan_forward(start_date, lead_days)
                    anchor_txt = start_date.isoformat()

                fields = {}
                for stage, _lbl in _MS:
                    if not overwrite and (rec.get(f"{stage}_planned") or "").strip():
                        continue
                    fields[f"{stage}_planned"] = plan[stage]
                preview_rows.append({
                    "PO Number": rec["po_number"],
                    "Style": rec.get("style") or "",
                    "Anchor": anchor_txt,
                    "Result": (f"{len(fields)} {t('date(s)')}" if fields
                               else t("already planned — nothing to fill")),
                })
                if fields:
                    jobs.append((rec["po_number"], rec.get("style") or "", fields))

            if preview_rows:
                st.dataframe(pd.DataFrame(preview_rows), width="stretch",
                             hide_index=True,
                             height=min(60 + 35 * len(preview_rows), 260))
            if st.button(
                f"🗓 {t('Fill')} {sum(len(f) for _, _, f in jobs)} {t('date(s)')}",
                type="primary", disabled=not jobs, key="pt_autoplan_go",
            ):
                for po, sty, fields in jobs:
                    store.update_stage_fields(po, sty, fields, updated_by=username)
                st.success(f"✅ {len(jobs)} {t('record(s) updated.')}")
                fragment_rerun()

        # ── Bulk edits ─────────────────────────────────────────────────────
        def _bulk_panel():
            b1, b2 = st.columns(2)

            with b1:
                st.markdown(f"**{t('Set one milestone for all selected')}**")
                fill_stage = st.selectbox(
                    t("Milestone"), options=[s for s, _ in _MS],
                    format_func=lambda s: MILESTONE_LABELS.get(s, s),
                    key="pt_bulk_fill_stage",
                )
                fill_date = st.date_input(t("Date"), value=today,
                                          key="pt_bulk_fill_date")
                fill_which = st.radio(
                    t("Which field"), [GRID_PLANNED, GRID_ACTUAL], horizontal=True,
                    key="pt_bulk_fill_field",
                    format_func=lambda m: (t("计划 Planned") if m == GRID_PLANNED
                                           else t("实际 Actual")),
                    label_visibility="collapsed",
                )
                if st.button(f"⬇️ {t('Fill down')}", key="pt_bulk_fill_go",
                             disabled=not targets):
                    for rec in targets:
                        fields = {f"{fill_stage}_{fill_which}": fill_date.isoformat()}
                        if fill_which == GRID_ACTUAL:
                            fields[f"{fill_stage}_status"] = "Done"
                        store.update_stage_fields(
                            rec["po_number"], rec.get("style") or "", fields,
                            updated_by=username)
                    st.success(f"✅ {len(targets)} {t('record(s) updated.')}")
                    fragment_rerun()

                st.divider()
                st.markdown(f"**{t('Shift the whole plan')}**")
                shift_days = st.number_input(
                    t("Days (negative = earlier)"), value=7, step=1,
                    key="pt_bulk_shift_days")
                if st.button(f"↔ {t('Shift planned dates')}",
                             key="pt_bulk_shift_go", disabled=not targets):
                    n = 0
                    for rec in targets:
                        planned = {s: (rec.get(f"{s}_planned") or "")
                                   for s, _ in _MS}
                        shifted = shift_plan(planned, int(shift_days))
                        fields = {f"{s}_planned": v
                                  for s, v in shifted.items()
                                  if v and v != planned[s]}
                        if fields:
                            store.update_stage_fields(
                                rec["po_number"], rec.get("style") or "", fields,
                                updated_by=username)
                            n += 1
                    st.success(f"✅ {n} {t('record(s) updated.')}")
                    fragment_rerun()

            with b2:
                st.markdown(f"**{t('Copy a plan onto the selected rows')}**")
                src_label = st.selectbox(
                    t("Copy dates from"), options=list(by_label),
                    key="pt_bulk_copy_src",
                )
                src = by_label[src_label]
                src_plan = {s: (src.get(f"{s}_planned") or "") for s, _ in _MS}
                st.caption(
                    f"{sum(1 for v in src_plan.values() if v)}/{len(_MS)} "
                    + t("milestone(s) planned on the source")
                )
                if st.button(f"📋 {t('Copy plan')}", key="pt_bulk_copy_go",
                             disabled=not targets):
                    n = 0
                    for rec in targets:
                        if (rec["po_number"], rec.get("style") or "") == (
                                src["po_number"], src.get("style") or ""):
                            continue          # don't copy onto itself
                        fields = {f"{s}_planned": v
                                  for s, v in src_plan.items() if v}
                        if fields:
                            store.update_stage_fields(
                                rec["po_number"], rec.get("style") or "", fields,
                                updated_by=username)
                            n += 1
                    st.success(f"✅ {n} {t('record(s) updated.')}")
                    fragment_rerun()

        # ── Lead times ─────────────────────────────────────────────────────
        def _lead_panel():
            st.caption(t(
                "Days before 离厂时间 that each milestone should be complete. "
                "Used by both plan directions — tune once per client/factory "
                "and every future draft plan follows it."
            ))
            lead_df = pd.DataFrame(
                [{"Milestone": MILESTONE_LABELS.get(s, s),
                  "Days before 离厂时间": lead_days[s]} for s, _ in _MS]
            )
            edited_lead = st.data_editor(
                lead_df, hide_index=True, width="content", num_rows="fixed",
                disabled=["Milestone"], key="pt_lead_editor",
                column_config={
                    "Days before 离厂时间": st.column_config.NumberColumn(
                        t("Days before 离厂时间"), min_value=0, step=1),
                },
            )
            if st.button(f"💾 {t('Save lead times')}", key="pt_lead_save"):
                save_lead_days({
                    s: int(edited_lead.iloc[i]["Days before 离厂时间"] or 0)
                    for i, (s, _) in enumerate(_MS)
                })
                st.success(f"✅ {t('Lead times saved.')}")
                fragment_rerun()

        lazy_sections([
            (t("Draft a plan"), _plan_panel),
            (t("Bulk edits"),   _bulk_panel),
            (t("Lead times"),   _lead_panel),
        ], key="pt_autoplan_nav")


def _render_grid_excel_io(filtered, store, username, scope: "TrackScope") -> None:
    """Download the visible grid as Excel, edit it there, and upload to apply.

    A faster path than typing into the on-screen editor for a whole season:
    the export carries every milestone's Planned and Actual date, and the
    import applies them exactly the way the grid does (a filled Actual marks
    the milestone done; a blank cell never erases). Only rows that are still
    tracked are updated — anything else is reported, never silently dropped.

    Scope is enforced on apply: a row for a PO/style outside the user's access
    is rejected, and a factory user's planned-date edits are ignored (they may
    record progress only) — so a hand-edited upload can't escape the user's
    permissions.
    """
    from po_extractor.exporters.tracking_grid_xlsx import (
        build_tracking_grid_xlsx, parse_tracking_grid_xlsx,
    )

    with st.expander(f"📊 {t('Excel export / import')}", expanded=False):
        st.caption(t(
            "Download the rows shown above as an Excel table, edit the "
            "Planned / Actual dates in Excel, then upload it here to apply. A "
            "blank cell never erases a stored date."
        ))
        st.download_button(
            f"⬇️ {t('Export grid to Excel')}",
            data=build_tracking_grid_xlsx(filtered),
            file_name=f"Tracking_{date.today().isoformat()}.xlsx",
            mime=XLSX_MIME,
            key="pt_grid_xlsx_dl",
        )

        st.divider()
        uploaded = st.file_uploader(
            t("Upload edited tracking table (.xlsx)"), type=["xlsx", "xlsm"],
            key="pt_grid_xlsx_up", label_visibility="collapsed",
        )
        if uploaded is None:
            return

        try:
            parsed = parse_tracking_grid_xlsx(uploaded.getvalue())
        except ValueError as exc:
            st.error(f"{t('Could not read this file:')} {exc}")
            return

        for issue in parsed["issues"]:
            st.warning(f"⚠️ {issue}")
        rows = parsed["rows"]
        if not rows:
            st.info(t("No date changes found in this file."))
            return

        # Preview: how many milestone dates each PO/style would receive, and
        # flag rows that aren't tracked (typo guard) before anything is written.
        tracked = {(r.get("po_number", ""), r.get("style") or "") for r in filtered}
        prev, untracked = [], 0
        for row in rows:
            key = (row["po_number"], row["style"])
            n_dates = sum(1 for k in row["fields"] if k.endswith(("_planned", "_actual")))
            is_tracked = key in tracked
            untracked += 0 if is_tracked else 1
            prev.append({
                "PO Number": row["po_number"], "Style": row["style"],
                "Dates": n_dates,
                "Status": "✓" if is_tracked else ("⚠ " + t("not in the current view")),
            })
        st.dataframe(pd.DataFrame(prev), width="stretch", hide_index=True,
                     height=min(60 + 35 * len(prev), 320))
        if untracked:
            st.caption("⚠️ " + t(
                "Rows marked not-in-view are outside the current filter or no "
                "longer tracked; they are still applied if the PO/style exists."))

        if st.button(f"✅ {t('Apply')} {len(rows)} {t('row(s)')}",
                     type="primary", key="pt_grid_xlsx_apply"):
            applied = skipped = blocked = 0
            for row in rows:
                po, style = row["po_number"], row["style"]
                # Access gate — a crafted upload can't reach a row out of scope.
                if not scope.permits(po, style):
                    blocked += 1
                    continue
                fields = scope.sanitize_fields(row["fields"])
                if not fields:               # factory user: only planned edits
                    continue
                try:
                    if store.update_stage_fields(po, style, fields,
                                                 updated_by=username):
                        applied += 1
                    else:
                        skipped += 1
                        st.warning(f"⚠️ {po} / {style} — "
                                   + t("not tracked; skipped."))
                except ValueError as exc:
                    skipped += 1
                    st.error(f"{po} / {style}: {exc}")
            msg = f"✅ {applied} {t('record(s) updated.')}"
            if skipped:
                msg += f" {skipped} {t('skipped')}."
            if blocked:
                msg += f" 🔒 {blocked} " + t("outside your access — not applied.")
            st.success(msg)
            fragment_rerun()


def _render_grid_tab(records, store, po_store, username, today, admin_mode,
                     user_cos, scope: "TrackScope") -> None:
    """One-page milestone grid + (admin) the full 22-stage editor."""
    # Newly-loaded contracts that aren't tracked yet — surfaced right here
    # with a one-click "Track all". Factory users can't add rows, so they
    # never see this.
    had_untracked = False
    if scope.can_add_remove:
        had_untracked = _render_untracked_banner(
            store, po_store, username, user_cos, admin_mode)

    if not records:
        if not had_untracked:
            st.info(t(
                "Nothing tracked yet — use **➕ Add / Remove** to start tracking "
                "PO/styles, then fill their milestone dates here."
            ) if scope.can_add_remove else t(
                "No orders for your factory are being tracked yet."))
        return
    if had_untracked:
        st.divider()

    filtered = _render_progress_filters(records, "pt_grid")
    if not filtered:
        st.warning(t("No records match the current filters."))
        return

    # Factory users record progress only, so the grid is pinned to 实际 Actual
    # (planned dates are the merchandiser's to set). Everyone else toggles.
    if scope.can_edit_planned:
        mode_labels = {GRID_PLANNED: t("计划 Planned"), GRID_ACTUAL: t("实际 Actual")}
        mode = st.radio(
            t("Date mode"), [GRID_PLANNED, GRID_ACTUAL], horizontal=True,
            key=SK.PT_GRID_MODE, format_func=lambda m: mode_labels[m],
            label_visibility="collapsed",
        )
        st.caption(t(
            "**计划 Planned** dates are what the buy plan's Index tab prints and "
            "what the factory form asks for. Switch to **实际 Actual** to record "
            "what actually happened — filling an actual date marks that milestone "
            "complete."
        ))
    else:
        mode = GRID_ACTUAL
        st.caption(t(
            "Enter the **实际 Actual** date each milestone was completed — "
            "filling a date marks it done. Planned dates are set by the "
            "merchandiser."
        ))

    # Completion at a glance, colour-coded: 🔴 overdue · 🟠 due within 7 days
    # · ✅ done · 📅 scheduled · ⬜ nothing.
    st.dataframe(
        _status_strip_df(filtered, today), width="stretch", hide_index=True,
        height=min(60 + 35 * len(filtered), 280),
    )

    _render_autoplan_section(filtered, store, username, today)

    original = _grid_dataframe(filtered, mode)
    col_cfg = {
        "PO Number": st.column_config.TextColumn(t("PO Number"), width="medium"),
        "Style":     st.column_config.TextColumn(t("Style"), width="small"),
        "Factory":   st.column_config.TextColumn(t("Factory"), width="small"),
        "Done":      st.column_config.TextColumn(t("Done"), width="small"),
    }
    for _stage, label in MILESTONE_STAGES:
        col_cfg[label] = st.column_config.DateColumn(label, width="small",
                                                     format="YYYY-MM-DD")
    edited = st.data_editor(
        original, hide_index=True, width="stretch", num_rows="fixed",
        disabled=_GRID_META_COLS + ["Done"],
        column_config=col_cfg,
        key=f"pt_grid_editor_{mode}",
        height=min(60 + 35 * len(filtered), 500),
    )

    changes = _grid_diff(original, edited, mode, filtered)
    n = sum(len(v) for v in changes.values())
    if st.button(
        f"💾 {t('Save')}" + (f" ({n} {t('change(s)')})" if n else ""),
        type="primary", disabled=not changes, key="pt_grid_save",
    ):
        saved = 0
        for (po, style), fields in changes.items():
            # Defence in depth: the editor only shows in-scope rows, but never
            # write one the scope forbids, and strip fields the user can't set.
            if not scope.permits(po, style):
                continue
            fields = scope.sanitize_fields(fields)
            if not fields:
                continue
            try:
                if store.update_stage_fields(po, style, fields,
                                             updated_by=username):
                    saved += 1
            except ValueError as exc:
                st.error(f"{po} / {style}: {exc}")
        st.success(f"✅ {saved} {t('record(s) updated.')}")
        fragment_rerun()

    # ── Excel round-trip — edit the whole grid in a spreadsheet ─────────────
    _render_grid_excel_io(filtered, store, username, scope)

    # ── Advanced: the full 22-stage record (collapsed) ──────────────────────
    # Kept verbatim so no capability is lost -- dependencies, readiness gates,
    # optional samples, expected-days and QC all still live here. The daily
    # path above never renders any of it. Hidden from factory users: it edits
    # planned dates and the full stage model, beyond their progress-only remit.
    if scope.factory_mode:
        return
    st.divider()
    with st.expander(f"🛠 {t('Advanced — full 22-stage record')}", expanded=False):
        st.caption(t(
            "Detailed per-stage tracking: dependencies, readiness gates, "
            "optional samples, expected days and QC inspections. Most "
            "work only needs the grid above."
        ))
        # Readiness is computed HERE (not at tab entry) so the simple path
        # never pays for a 22-stage scan per record.
        readiness_map = {r["id"]: store.compute_readiness(r) for r in records}
        _render_edit_tab(records, readiness_map, store, username, today)


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
    show_flash(SK.PT_DELETE_FLASH)

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

    # ── Stage-group selector — ONE group rendered at a time ──────────────────
    # Perf: rendering all 4 groups + QC mounts ~120 widgets (44 date pickers,
    # ~30 selectboxes...) and EVERY interaction re-mounts them all, making
    # each click feel seconds-slow. Rendering only the selected group cuts
    # that ~4-5x. Saving stays correct: the _read/_MISSING mechanism falls
    # back to the record's DB value for any widget not rendered this run
    # (the same contract the Optional Samples toggle already relies on).
    #
    # Placed HIGH (directly under the record picker, above the read-only meta
    # and notes): the groups differ hugely in height (A has 8 stages, B has
    # ~1), so switching shrinks the page — with the selector low down the
    # browser clamped the scroll position and threw the user somewhere else
    # ("it jumps out"). Near the top there is nothing to clamp.
    _PANES = [
        "🧵 A · Pre-Production",
        "🧪 B · Samples",
        "🏭 C · Production",
        "📦 D · Post-Production",
        "🔍 QC",
    ]
    pane = st.radio(
        t("Stage group"), _PANES, horizontal=True, key="pt_edit_pane",
        format_func=t, label_visibility="collapsed",
    )
    st.caption(t(
        "💾 Save before switching sections — unsaved edits in a section "
        "disappear when it is hidden."
    ))

    st.divider()

    # ── Factory / Company (read-only display) ────────────────────────────────
    meta_c1, meta_c2, meta_c3 = st.columns([2, 2, 4])
    meta_c1.text_input(t("PO Number"),  value=record.get("po_number") or "", disabled=True)
    meta_c2.text_input(t("Style"),      value=record.get("style")     or "", disabled=True)
    meta_c3.text_input(t("Factory"),    value=record.get("factory")   or "", disabled=True)

    # Overall notes
    overall_notes_val = record.get("overall_notes") or ""
    st.text_area(
        t("Overall Notes"),
        value=overall_notes_val,
        key=_wkey(rid, "overall_notes"),
    )

    st.divider()

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
        if st.button(t("💾 Save"), type="primary", width="stretch"):
            _do_save(record, store, username, rid)
            fragment_rerun()

    with col_del:
        if delete_button(t("Delete"), key="pt_delete_record", width="stretch"):
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

def _default_tracking_payload() -> tuple[dict, dict, dict]:
    """``(stage_fields, dep_fields, qc_fields)`` for a brand-new record:
    every stage Not Started with no dates, DEFAULT_DEP_ON flags set, QC at
    its defaults. Shared by single-add and bulk-add so both create identical
    records.
    """
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
        # loop var `tgt`, not `t` — `t` is this module's i18n translator; a
        # bare `for t in ...:` would make Python treat `t` as local for the
        # whole function (UnboundLocalError on any t() call).
        for tgt in targets:
            col = dep_col(source, tgt)
            dep_fields[col] = 1 if col in DEFAULT_DEP_ON else 0
    dep_fields[dep_col("pp_sample", "cutting")] = 1   # always required

    qc_fields: dict[str, Any] = {}
    for key in QC_INSPECTIONS:
        qc_fields[f"{key}_booking_deadline"] = ""
        qc_fields[f"{key}_reminder_days"]    = 7
        qc_fields[f"{key}_booked"]           = 0
        qc_fields[f"{key}_booking_date"]     = ""
        qc_fields[f"{key}_inspection_date"]  = ""
        qc_fields[f"{key}_result"]           = "Pending"
        qc_fields[f"{key}_notes"]            = ""
    return stage_fields, dep_fields, qc_fields


def _bulk_track(store, rows: list[dict], username: str) -> int:
    """Create an empty tracking record for every (po, style) in *rows*.

    Shared by the grid's "Track all new" banner and the Add tab's bulk
    button so both create identical starter records. Returns how many were
    written.
    """
    stage_fields, dep_fields, qc_fields = _default_tracking_payload()
    n = 0
    for row in rows:
        store.upsert(
            po_number=row["po_number"],
            style=row.get("style") or "",
            factory=row.get("factory") or "",
            company=row.get("company") or "",
            updated_by=username,
            overall_notes="",
            use_substitute_materials=1,
            stage_fields=dict(stage_fields),
            dep_fields=dict(dep_fields),
            qc_fields=dict(qc_fields),
        )
        n += 1
    return n


def _render_untracked_banner(store, po_store, username, user_cos,
                             admin_mode) -> bool:
    """Show a one-click 'Track all N new' banner when loaded contracts (GIII
    or Sky East) aren't tracked yet. Returns True if any were shown.

    This keeps tracking opt-in — nothing is added until the button is
    pressed — while making newly-loaded orders visible right on the grid
    instead of hidden behind the Add / Remove tab.
    """
    untracked = store.list_untracked_pos(
        po_store,
        companies=user_cos if not admin_mode else None,
        allow_all=admin_mode,
    )
    if not untracked:
        return False

    from collections import Counter
    by_client = Counter((r.get("company") or t("Unknown")) for r in untracked)
    breakdown = " · ".join(f"{client}: {k}" for client, k in
                           sorted(by_client.items()))
    c1, c2 = st.columns([3, 1])
    with c1:
        st.info(
            f"➕ {len(untracked)} "
            + t("loaded PO/style(s) are not tracked yet")
            + f"  ({breakdown}). "
            + t("Add them to see their milestones here.")
        )
    with c2:
        if st.button(f"➕ {t('Track all')} {len(untracked)} {t('new')}",
                     key="pt_grid_track_all", type="primary",
                     width="stretch"):
            n = _bulk_track(store, untracked, username)
            st.success(f"✅ {n} {t('record(s) now tracked.')}")
            fragment_rerun()
    return True


def _render_remove_section(store, records: list[dict]) -> None:
    """Stop tracking selected PO/styles. Deletes ONLY the tracking record —
    the underlying PO/order data is untouched (see store.delete)."""
    if not records:
        return
    with st.expander(f"🗑 {t('Stop tracking (remove records)')}", expanded=False):
        by_label = {
            f"{r['po_number']} — {r.get('style') or '—'}": r["id"] for r in records
        }
        guard_multiselect_state("pt_remove_sel", list(by_label))
        chosen = st.multiselect(
            t("Records to stop tracking"), options=list(by_label),
            key=SK.PT_REMOVE_SEL,
        )
        st.caption(t(
            "Removes the tracking record and its milestone dates. The PO and "
            "order data itself are not deleted."
        ))
        if chosen and st.button(
            f"🗑 {t('Stop tracking')} ({len(chosen)})", key="pt_remove_go",
        ):
            store.delete([by_label[c] for c in chosen])
            st.session_state.pop(SK.PT_REMOVE_SEL, None)
            st.success(f"✅ {len(chosen)} {t('record(s) removed.')}")
            fragment_rerun()


def _render_add_tab(
    store,
    po_store,
    username: str,
    *,
    user_cos: list[str],
    admin_mode: bool,
    records: list[dict] | None = None,
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
        _render_remove_section(store, records or [])
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
    mc1.text_input(t("PO Number"), value=chosen["po_number"], disabled=True)
    mc2.text_input(t("Style"),     value=chosen.get("style") or "", disabled=True)
    factory_val = st.text_input(
        t("Factory"),
        value=chosen.get("factory") or "",
        key="pt_add_factory",
    )
    company_val = chosen.get("company") or ""
    overall_notes_val = st.text_area(t("Overall Notes"), value="", key="pt_add_notes")

    st.divider()

    if st.button(t("➕ Start Tracking"), type="primary", width="stretch"):
        stage_fields, dep_fields, qc_fields = _default_tracking_payload()
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
        # Back to the grid with the new record pre-selected in Advanced.
        st.session_state[SK.PT_SELECTED_EDIT] = new_id
        st.session_state[SK.PT_ACTIVE_TAB]    = TAB_GRID
        # Delete the radio's own widget key so the next render falls back to
        # index=PT_ACTIVE_TAB.  Writing it directly after instantiation raises
        # StreamlitAPIException ("cannot be modified after widget instantiated").
        st.session_state.pop(SK.PT_TAB_RADIO, None)
        fragment_rerun()

    # ── Bulk add — everything currently listed (after the client filter) ────
    st.divider()
    if st.button(
        f"➕ {t('Track all')} {len(untracked)} {t('shown')}",
        width="stretch", key="pt_add_all",
    ):
        n = _bulk_track(store, untracked, username)
        st.success(f"✅ {n} {t('record(s) now tracked.')}")
        st.session_state[SK.PT_ACTIVE_TAB] = TAB_GRID
        st.session_state.pop(SK.PT_TAB_RADIO, None)
        fragment_rerun()

    _render_remove_section(store, records or [])


# ─────────────────────────────────────────────────────────────────────────────
# Factory Updates tab — quantity reports from factories (units cut/sewn/packed)
# ─────────────────────────────────────────────────────────────────────────────

def _render_buyplan_tracking_import(bp: dict, records, username,
                                    scope: "TrackScope") -> None:
    """Preview + apply the tracking columns of a returned BUY PLAN Index tab.

    The Index identifies rows by (客人PC NO, 款号); the tracking key is
    (Zalando PO, style), so PC+style resolve to the PO via sky_east_items.
    Only EXPECTED (计划) dates and 生产工厂 travel on this form — non-empty
    cells overwrite the stored plan; blanks never erase anything.

    This carries PLANNED dates, so it's disabled for factory users (progress
    only) and gated by ``scope`` for everyone else.
    """
    from ui.stores import get_sky_east_store

    if scope.factory_mode:
        st.info(t("Returned buy plans set planned dates, which factory logins "
                  "can't change. Ask the merchandiser to import it."))
        return

    rows = bp.get("rows") or []
    st.markdown(f"**{t('Returned buy plan detected')}** — "
                f"{len(rows)} {t('row(s) with tracking data')}")
    if not rows:
        st.info(t("No filled tracking cells found in this buy plan's Index tab."))
        return

    try:
        items = get_sky_east_store().list_items()
        po_map: dict = {}
        for _, r in items.iterrows():
            k = (str(r.get("pc_no") or "").strip(),
                 str(r.get("style") or "").strip())
            po = str(r.get("zalando_po") or "").strip()
            if k[0] and k[1] and po and k not in po_map:
                po_map[k] = po
    except Exception:
        po_map = {}

    tracked = {(r["po_number"], r.get("style") or "") for r in records}
    prev_rows, apply_jobs = [], []
    for row in rows:
        po = po_map.get((row["pc_no"], row["style"]), "")
        changes = ", ".join(
            f"{MILESTONE_LABELS.get(k, k).split(' ')[0]}: {v}"
            for k, v in row["planned"].items()
        )
        if row["factory"]:
            changes = (f"{t('Factory')}: {row['factory']}"
                       + (f", {changes}" if changes else ""))
        if not po:
            status = "❓ " + t("PO not found for this PC/style")
        elif (po, row["style"]) not in tracked or not scope.permits(po, row["style"]):
            status = "⚠ " + t("not tracked; skipped")
        else:
            status = "✓"
            fields = {f"{k}_planned": v for k, v in row["planned"].items()}
            if row["factory"]:
                fields["factory"] = row["factory"]
            apply_jobs.append((po, row["style"], fields))
        prev_rows.append({
            "PC No.": row["pc_no"], "Style": row["style"],
            "Updates": changes, "Status": status,
        })

    st.dataframe(pd.DataFrame(prev_rows), width="stretch", hide_index=True,
                 height=min(60 + 36 * len(prev_rows), 350))
    if apply_jobs and st.button(
        f"✅ {t('Apply')} {len(apply_jobs)} {t('tracking update(s) from buy plan')}",
        type="primary", key="pt_fu_bp_apply",
    ):
        pt_store = get_production_tracking_store()
        n = 0
        for po, sty, fields in apply_jobs:
            try:
                if pt_store.update_stage_fields(po, sty, fields,
                                                updated_by=username):
                    n += 1
            except ValueError as exc:
                st.error(f"{po} / {sty}: {exc}")
        st.success(f"✅ {n} {t('tracking update(s) applied.')}")
        fragment_rerun()


def _render_factory_updates_tab(records, username, admin_mode,
                                scope: "TrackScope") -> None:
    """Excel round-trip + manual entry for factory quantity reports.

    Flow: generate a request form for one factory (their tracked PO/styles
    pre-filled) → factory fills the New-quantities columns → upload the
    returned file (validated preview → import) → per-PO/style totals table.
    Each report is a dated log entry (history kept); totals are derived.

    ``scope`` gates every write: an imported report or milestone update for a
    PO/style outside the user's access is refused, and a factory user's
    planned-date edits are dropped (progress only). ``records`` is already the
    user's scoped set, so the tables and pickers show only permitted rows.
    """
    from ui.stores import get_factory_progress_store
    from po_extractor.store._factory_progress_schema import (
        REPORT_STAGES, REPORT_STAGE_LABELS,
    )
    from po_extractor.exporters.factory_progress_form import (
        build_progress_request_xlsx, parse_progress_report_xlsx,
        parse_buyplan_index_tracking,
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
                mime=XLSX_MIME,
                key="pt_fu_form_download",
            )

    # ── 3. Import a returned form (progress form OR returned buy plan) ──────
    with st.expander(f"📥 {t('Import a returned form')}", expanded=False):
        st.caption(t(
            "Accepts either the 进度回报 progress form or a returned BUY PLAN "
            "whose Index tab tracking columns were filled in by the "
            "merchandiser/factory."
        ))
        up_factory = st.text_input(
            t("Factory this file came from"), key="pt_fu_import_factory",
            help=t("Stamped on every imported report row for the audit trail."),
        )
        uploaded = st.file_uploader(
            t("Returned progress form (.xlsx)"), type=["xlsx", "xlsm"],
            key="pt_fu_import_file", label_visibility="collapsed",
        )
        if uploaded is not None:
            parsed = None
            try:
                parsed = parse_progress_report_xlsx(uploaded.getvalue(),
                                                    factory=up_factory.strip())
            except ValueError:
                # Not the progress form — maybe a returned buy plan.
                try:
                    _bp = parse_buyplan_index_tracking(uploaded.getvalue())
                except ValueError as exc2:
                    st.error(
                        t("Not a recognisable progress form or buy plan:")
                        + f" {exc2}")
                else:
                    _render_buyplan_tracking_import(_bp, records, username, scope)
            if parsed is not None:
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
                        n = blocked = 0
                        for rp in reports:
                            if not scope.permits(rp["po_number"], rp["style"]):
                                blocked += 1
                                continue
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
                            if not scope.permits(m["po_number"], m["style"]):
                                blocked += 1
                                continue
                            fields: dict = {}
                            if m["expected"]:
                                fields[f"{m['stage']}_planned"] = m["expected"]
                            if m["note"]:
                                fields[f"{m['stage']}_notes"] = m["note"]
                            if m["completed"]:
                                fields[f"{m['stage']}_actual"] = m["completed"]
                                fields[f"{m['stage']}_status"] = "Done"
                            # Factory users record progress only — drop any
                            # planned/expected date from the sheet.
                            fields = scope.sanitize_fields(fields)
                            if not fields:
                                continue
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
                            + (f" 🔒 {blocked} " + t("outside your access — not applied.")
                               if blocked else "")
                        )
                        fragment_rerun()

    # NOTE: the per-record Milestones editor that used to live here was
    # replaced by the 📅 Tracking Grid (all records at once, same 9
    # MILESTONE_STAGES). The factory round-trip below still carries the
    # 里程碑 sheet, so factories keep updating milestones by Excel.

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
                    key=SK.PT_FU_DEL_SEL,
                )
                if del_ids and st.button(
                    f"🗑 {t('Delete')} {len(del_ids)}", key="pt_fu_del_go",
                ):
                    fp_store.delete_reports(del_ids)
                    st.session_state.pop(SK.PT_FU_DEL_SEL, None)
                    fragment_rerun()
