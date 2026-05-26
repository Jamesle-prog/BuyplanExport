"""SQLite store for production stage tracking (the 🏭 Tracking tab).

One row per ``(po_number, style)`` pair, tracking 22 manufacturing stages,
a configurable dependency matrix, and four QC inspection types.

Public surface
--------------
- ``ProductionTrackingStore`` — CRUD + compute helpers
- ``compute_readiness(record)``        → which prereqs gate PP Sample / Cutting
- ``compute_schedule(record, start)``  → forward-scheduled per-stage timeline
- ``compute_inspection_reminders(...)`` → which QC bookings are due/overdue

The compute methods are pure functions on a record dict — no DB access.
This keeps the UI render path free of extra queries and makes the logic
trivially unit-testable.

Schema and constants live in ``_production_tracking_schema.py``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .base_store import BaseSQLiteStore
from ._production_tracking_schema import (
    COLUMN_SPEC,
    base_schema_sql,
    STAGES,
    STAGES_GROUP_A,
    STAGES_GROUP_B,
    STAGES_GROUP_C,
    STAGES_GROUP_D,
    ALL_SAMPLE_STAGES,
    OPTIONAL_SAMPLE_STAGES,
    STAGE_LABELS,
    PREREQ_VALID,
    PREREQ_TARGETS,
    SUBSTITUTE_SAMPLE_PREREQS,
    BULK_MATERIAL_PREREQS,
    QC_INSPECTIONS,
    QC_INSPECTION_LABELS,
    dep_col,
)


class ProductionTrackingStore(BaseSQLiteStore):
    """Read/write access to the ``production_tracking`` table."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_schema()

    # ── Schema / migration ───────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Create the base table on a fresh DB, then ADD COLUMN for every
        non-base column that's missing.  Safe on:
        - a brand-new database (full table built)
        - the old 6-column stub (new columns added; old data preserved)
        - an already-migrated table (no-op)

        Dead columns from the previous stub (``ex_factory_date``, ``etd``,
        etc.) are intentionally left in place — SQLite has no safe
        ``DROP COLUMN`` in a migration; the application code simply ignores
        them.
        """
        with self._conn() as conn:
            conn.executescript(base_schema_sql())
            existing = {
                row[1]
                for row in conn.execute("PRAGMA table_info(production_tracking)")
            }
            for col_name, col_def in COLUMN_SPEC:
                if col_name not in existing:
                    conn.execute(
                        f"ALTER TABLE production_tracking ADD COLUMN {col_name} {col_def}"
                    )

    # ── Writes ──────────────────────────────────────────────────────────────

    def upsert(
        self,
        po_number: str,
        style: str,
        factory: str,
        company: str,
        updated_by: str,
        overall_notes: str,
        use_substitute_materials: int,
        stage_fields: dict[str, Any],
        dep_fields: dict[str, Any],
        qc_fields: dict[str, Any],
    ) -> int:
        """Insert or update one tracking record.  Returns the row id.

        ``overall_notes`` and ``use_substitute_materials`` are explicit named
        params — NOT buried inside any dict — because they are record-level
        ("global") fields and the previous design that buried them in a dict
        caused silent drops on every save.
        """
        po_number = (po_number or "").strip()
        style = (style or "").strip()
        now = datetime.utcnow().isoformat(timespec="seconds")

        # ── Build the combined column → value mapping.
        payload: dict[str, Any] = {
            "po_number":                po_number,
            "style":                    style,
            "factory":                  (factory or "").strip(),
            "company":                  (company or "").strip(),
            "overall_notes":            overall_notes or "",
            "use_substitute_materials": int(bool(use_substitute_materials)),
            "updated_at":               now,
            "updated_by":               updated_by or "",
        }
        payload.update(stage_fields or {})
        payload.update(dep_fields or {})
        payload.update(qc_fields or {})

        cols = list(payload.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_list = ", ".join(cols)
        # Build UPDATE SET clause for ON CONFLICT — every column except the
        # natural key gets refreshed from the excluded row.
        update_cols = [c for c in cols if c not in ("po_number", "style")]
        update_set = ", ".join(f"{c} = excluded.{c}" for c in update_cols)

        sql = (
            f"INSERT INTO production_tracking ({col_list}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(po_number, style) DO UPDATE SET {update_set}"
        )
        with self._conn() as conn:
            conn.execute(sql, [payload[c] for c in cols])
            row = conn.execute(
                "SELECT id FROM production_tracking WHERE po_number=? AND style=?",
                (po_number, style),
            ).fetchone()
        return int(row["id"]) if row else 0

    def delete(self, ids: list[int]) -> int:
        """Delete tracking record(s) by id.  Returns deleted count.
        Touches only ``production_tracking`` — does NOT delete the underlying
        PO data in ``po_metadata`` / ``po_size_rows``.
        """
        if not ids:
            return 0
        ph = ",".join("?" * len(ids))
        with self._conn() as conn:
            cur = conn.execute(
                f"DELETE FROM production_tracking WHERE id IN ({ph})", ids
            )
        return cur.rowcount

    # ── Reads ───────────────────────────────────────────────────────────────

    def list_all(
        self,
        companies: list[str] | None = None,
        allow_all: bool = False,
    ) -> list[dict]:
        """Return tracking records, filtered by company unless ``allow_all``.

        Access control contract:
          - ``allow_all=True`` → no filter (admin path)
          - ``allow_all=False`` + empty/None companies → return ``[]``
            (do NOT run ``IN ()`` — that's a SQL error in SQLite)
          - ``allow_all=False`` + non-empty companies → ``WHERE company IN (?…)``
        """
        if not allow_all and not companies:
            return []

        sql = "SELECT * FROM production_tracking"
        params: list[Any] = []
        if not allow_all:
            ph = ",".join("?" * len(companies))
            sql += f" WHERE company IN ({ph})"
            params = list(companies)
        # NULLS LAST keeps fresh-but-not-yet-saved records (NULL updated_at)
        # from jumping to the top of the dashboard.
        sql += " ORDER BY updated_at DESC NULLS LAST, id DESC"

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get(self, po_number: str, style: str) -> dict | None:
        """Return a single record by natural key, or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM production_tracking WHERE po_number=? AND style=?",
                ((po_number or "").strip(), (style or "").strip()),
            ).fetchone()
        return dict(row) if row else None

    def list_untracked_pos(self, po_store) -> list[dict]:
        """Return all (po_number, style, factory, company) combos that are
        present in ``po_size_rows`` but not yet tracked.

        Sourced from ``po_size_rows`` (not ``po_metadata``) because a single
        PO can carry multiple distinct styles in po_size_rows; po_metadata
        has only one style column per PO and would miss multi-style orders.

        Runs against ``po_store.db_path`` — which in single-DB mode is the
        same file as ``self.db_path``, so the same connection sees all three
        tables.
        """
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(po_store.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # Attach the tracking DB if it's a different file.  In the
            # canonical po_history.db setup they're the same file, so we
            # can simply read the local production_tracking table.
            if po_store.db_path == self.db_path:
                rows = conn.execute(
                    """
                    SELECT DISTINCT
                           s.po_number,
                           COALESCE(s.style, '') AS style,
                           COALESCE(m.factory, '') AS factory,
                           COALESCE(m.company, '') AS company
                    FROM po_size_rows s
                    LEFT JOIN po_metadata m ON m.po_number = s.po_number
                    WHERE (s.po_number, COALESCE(s.style, '')) NOT IN
                          (SELECT po_number, style FROM production_tracking)
                    ORDER BY s.po_number, s.style
                    """
                ).fetchall()
            else:
                # Different DB files: attach the tracking DB read-only.
                conn.execute(
                    f"ATTACH DATABASE '{self.db_path}' AS pt"
                )
                rows = conn.execute(
                    """
                    SELECT DISTINCT
                           s.po_number,
                           COALESCE(s.style, '') AS style,
                           COALESCE(m.factory, '') AS factory,
                           COALESCE(m.company, '') AS company
                    FROM po_size_rows s
                    LEFT JOIN po_metadata m ON m.po_number = s.po_number
                    WHERE (s.po_number, COALESCE(s.style, '')) NOT IN
                          (SELECT po_number, style FROM pt.production_tracking)
                    ORDER BY s.po_number, s.style
                    """
                ).fetchall()
        return [dict(r) for r in rows]

    # ── Compute helpers (pure-Python, no DB) ────────────────────────────────

    @staticmethod
    def _auto_prereqs_for_sample(record: dict) -> list[str]:
        """Return the auto-prereq list for sample stages per FR-03b."""
        if int(record.get("use_substitute_materials", 1) or 0):
            return SUBSTITUTE_SAMPLE_PREREQS
        return BULK_MATERIAL_PREREQS

    @staticmethod
    def compute_readiness(record: dict) -> dict[str, str]:
        """Return readiness strings for PP Sample and Cutting.

        Format per target:
          - ``"ready"``                — all prereqs Done
          - ``"waiting:Label1,Label2"`` — these prereqs not Done
          - ``"no_prereqs"``           — nothing tagged

        Both the user-configurable dep matrix AND the substitute-material
        auto-rule (FR-03b) contribute to the prereq list for sample targets.
        """
        result: dict[str, str] = {}
        auto = ProductionTrackingStore._auto_prereqs_for_sample(record)

        for target in PREREQ_TARGETS:
            # 1) Matrix-configured prereqs that point at this target.
            matrix_tagged: list[str] = [
                s for s in PREREQ_VALID
                if target in PREREQ_VALID[s]
                and record.get(dep_col(s, target), 0)
                and record.get(f"{s}_applicable", 1)
            ]
            # 2) Auto prereqs from the substitute flag — only for sample targets.
            auto_tagged: list[str] = auto if target in ALL_SAMPLE_STAGES else []

            # Deduplicate preserving order.
            tagged = list(dict.fromkeys(matrix_tagged + auto_tagged))

            if not tagged:
                result[target] = "no_prereqs"
                continue

            pending = [
                s for s in tagged
                if (record.get(f"{s}_status") or "Not Started") != "Done"
            ]
            if not pending:
                result[target] = "ready"
            else:
                result[target] = (
                    "waiting:" + ",".join(STAGE_LABELS.get(s, s) for s in pending)
                )
        return result

    @staticmethod
    def compute_schedule(
        record: dict,
        start_date: date,
        override_days: dict[str, int] | None = None,
    ) -> dict[str, dict]:
        """Forward-schedule all 22 stages.

        For each stage:
          - Group A + B: ``earliest = max(prereq ends, default=start_date)``
          - Group C + D: also wait for the previous stage in STAGES order

        FR-03b auto-prereqs are injected per-stage for every stage in
        ALL_SAMPLE_STAGES (not just pp_sample).

        Returns ``{stage: {start, end, days, missing_days, skipped, critical,
        critical_predecessor}}``.  Critical path is computed by back-tracing
        the ``critical_predecessor`` chain from ``shipping``.
        """
        schedule: dict[str, dict] = {}
        auto = ProductionTrackingStore._auto_prereqs_for_sample(record)
        overrides = override_days or {}

        # Cursor used only to keep skipped stages from going below the
        # current end-time of the most recent applicable stage.  Group C/D
        # sequential chaining is computed explicitly via STAGES[index-1].
        current_end = start_date

        for stage in STAGES:
            applicable = (
                int(record.get(f"{stage}_applicable", 1) or 0)
                if stage in OPTIONAL_SAMPLE_STAGES
                else 1
            )
            raw_days = overrides.get(stage)
            if raw_days is None:
                raw_days = record.get(f"{stage}_expected_days")
            days = int(raw_days) if raw_days else 0

            if not applicable:
                schedule[stage] = {
                    "start":                current_end,
                    "end":                  current_end,
                    "days":                 0,
                    "missing_days":         False,
                    "skipped":              True,
                    "critical":             False,
                    "critical_predecessor": None,
                }
                continue

            # ── Matrix prereqs (must already be scheduled to count).
            prereqs: list[str] = [
                s for s in PREREQ_VALID
                if stage in PREREQ_VALID[s]
                and record.get(dep_col(s, stage), 0)
                and (
                    record.get(f"{s}_applicable", 1)
                    if s in OPTIONAL_SAMPLE_STAGES else 1
                )
                and s in schedule
                and not schedule[s]["skipped"]
            ]
            # ── FR-03b auto prereqs for every sample stage.
            if stage in ALL_SAMPLE_STAGES:
                prereqs = list(dict.fromkeys(
                    prereqs + [s for s in auto if s in schedule and not schedule[s]["skipped"]]
                ))

            # ── Compute earliest start.
            if stage in STAGES_GROUP_A or stage in STAGES_GROUP_B:
                # Parallel groups: prereq-driven.
                earliest = max(
                    (schedule[p]["end"] for p in prereqs),
                    default=start_date,
                )
                prev_stage: str | None = None
            else:
                # Sequential groups: also wait for the previous stage.
                prev_stage = STAGES[STAGES.index(stage) - 1]
                prev_end = schedule[prev_stage]["end"]
                earliest = max(
                    max((schedule[p]["end"] for p in prereqs), default=start_date),
                    prev_end,
                )

            # ── Critical predecessor — first candidate (sorted by STAGES.index)
            #    whose end equals earliest.  Deterministic tie-break.
            candidates: list[str] = list(prereqs)
            if prev_stage is not None:
                candidates.append(prev_stage)
            critical_pred: str | None = None
            for cand in sorted(set(candidates), key=lambda s: STAGES.index(s)):
                if cand in schedule and schedule[cand]["end"] == earliest:
                    critical_pred = cand
                    break

            end = earliest + timedelta(days=days)
            schedule[stage] = {
                "start":                earliest,
                "end":                  end,
                "days":                 days,
                "missing_days":         (days == 0),
                "skipped":              False,
                "critical":             False,
                "critical_predecessor": critical_pred,
            }
            current_end = end

        # ── Back-trace critical path from shipping.
        cursor: str | None = "shipping"
        while cursor is not None and cursor in schedule:
            schedule[cursor]["critical"] = True
            cursor = schedule[cursor]["critical_predecessor"]

        return schedule

    @staticmethod
    def compute_inspection_reminders(record: dict, today: date) -> list[dict]:
        """Return QC bookings that are due or overdue today.

        Each item: ``{"key": str, "label": str, "deadline": date, "overdue": bool}``

        Re-Final is skipped unless ``insp_final_result == 'Fail'``.
        Already-booked or no-deadline-set inspections produce no reminder.
        """
        out: list[dict] = []
        for key in QC_INSPECTIONS:
            if key == "insp_refinal":
                if (record.get("insp_final_result") or "Pending") != "Fail":
                    continue
            if int(record.get(f"{key}_booked", 0) or 0):
                continue
            deadline_str = (record.get(f"{key}_booking_deadline") or "").strip()
            if not deadline_str:
                continue
            try:
                deadline = date.fromisoformat(deadline_str)
            except ValueError:
                continue
            reminder_days = int(record.get(f"{key}_reminder_days") or 7)
            if today >= deadline - timedelta(days=reminder_days):
                out.append({
                    "key":      key,
                    "label":    QC_INSPECTION_LABELS[key],
                    "deadline": deadline,
                    "overdue":  today > deadline,
                })
        return out
