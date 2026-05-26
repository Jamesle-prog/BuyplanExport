# Production Tracking Build Plan by Stages

> Version: 1.0
> Module: Production Stage Tracking
> App: PO Automation GIII
> Related docs:
> - `docs/requirements_production_tracking.md`
> - `docs/development_plan_production_tracking.md`

---

## Purpose

Build the Production Stage Tracking module in controlled stages so each layer is usable and testable before the next layer depends on it.

This plan also resolves the workflow issues found during review:

- Track records by real `PO + Style` rows from `po_size_rows`, not only header rows from `po_metadata`.
- Keep access control explicit so non-admin users with no company assignment do not see all companies.
- Persist global workflow fields such as `use_substitute_materials` and `overall_notes`.
- Use a session-state-friendly navigation pattern instead of relying on `st.tabs()` to switch programmatically.
- Apply substitute-material gating consistently in readiness and schedule calculations.

---

## Stage 0 - Confirm Workflow Rules Before Coding

Goal: lock the business logic that affects schema, calculations, and UI.

Decisions to confirm:

1. Record identity is one row per `po_number + style`. The session-state identity (what `PT_SELECTED_EDIT` / `PT_SELECTED_PLAN` store) is the integer primary-key `id` — **never** a concatenated string. See dev plan §1.5 "Record identity contract".
2. Add New source is grouped from `po_size_rows`, joined to `po_metadata` for factory/company/header data.
3. `use_substitute_materials = 1` means sample-specific material stages gate sample stages.
4. `use_substitute_materials = 0` means bulk material stages gate sample stages.
5. Global fields must be saved with the same record:
   `use_substitute_materials`, `overall_notes`, `updated_by`, `updated_at`.
6. Non-admin users with no assigned companies see zero tracking records.
7. The dashboard edit shortcut must open the edit workflow and preselect the record.
8. `pp_sample → cutting` dependency is system-enforced ON, never user-configurable. Pre-production sample approval before bulk cutting is a fundamental manufacturing constraint. The dep column exists in the schema and is always written `1`.
9. Re-Final inspection (`insp_refinal`) is conditional: its widgets are only rendered when `insp_final_result == 'Fail'`. Its DB columns always exist; reminder logic ignores Re-Final unless Final has failed.

Exit criteria:

- Requirements and development docs are updated to remove contradictions.
- Schedule examples are recalculated and internally consistent.
- Access-control behavior is agreed for admin and non-admin users.

---

## Stage 1 - Data Schema and Constants

Goal: create the database foundation without UI.

Files:

- `po_extractor/store/_production_tracking_schema.py`

Build:

1. Replace the existing stub with the full production tracking schema. Total expected: **173 columns**.
   Breakdown:
   - 8 base columns: `id`, `po_number`, `style`, `factory`, `company`, `overall_notes`, `updated_at`, `updated_by`
   - 1 global flag: `use_substitute_materials`
   - 40 Group A: 8 stages × 5 fields
   - 30 Group B optional samples: 5 stages × 6 fields (5 normal + `applicable`)
   - 5 PP Sample: 5 fields
   - 30 Group C: 6 stages × 5 fields
   - 10 Group D: 2 stages × 5 fields
   - 21 dependency matrix booleans (see dev plan §1.1 for the full list)
   - 28 QC inspections: 4 types × 7 fields
2. Add all stage constants, labels, status options, dependency constants, QC constants, and helper `dep_col(source, target)`.
3. Include all global fields in the schema:
   `po_number`, `style`, `factory`, `company`, `overall_notes`, `use_substitute_materials`, `updated_at`, `updated_by`.
4. Use `UNIQUE(po_number, style)` for the tracking record.
5. Add an index on `company`.
6. Keep migration safe with `ALTER TABLE ADD COLUMN` for missing columns.
7. **Dead columns from the old stub** (`ex_factory_date`, `etd`, `eta`, `carrier`, `vessel`, `bl_number`, `status`, `notes`) are left in place. SQLite has no safe `DROP COLUMN` in a migration; the application simply ignores them. Do **not** write a destructive migration.

Exit criteria:

- Fresh database creates the full table.
- `PRAGMA table_info(production_tracking)` reports 173 columns (plus any dead columns from prior stubs).
- Existing database with stub table migrates without data loss.
- Re-running migration is idempotent.

Verification:

- Run a small schema test against a temporary SQLite database.
- Confirm all 173 expected columns exist.
- Confirm default dependency flags match `DEFAULT_DEP_ON` (4 flags: `base_size_pattern_req_pp_sample`, `base_size_pattern_req_cutting`, `full_sized_pattern_req_cutting`, `pp_sample_req_cutting`).
- Confirm migration over an existing stub DB preserves all old-stub column values.

---

## Stage 2 - Store CRUD and Access Control

Goal: make data operations reliable before adding screens.

Files:

- `po_extractor/store/production_tracking_store.py`
- `po_extractor/store/__init__.py`
- `ui/stores.py`

Build:

1. Implement `ProductionTrackingStore`.
2. Implement `upsert()` with the **exact** signature below. `overall_notes` and `use_substitute_materials` MUST be explicit named params — not buried inside `stage_fields` or any other dict — otherwise the Save handler silently drops them on every write:
   ```python
   def upsert(
       self,
       po_number: str, style: str, factory: str, company: str,
       updated_by: str,
       overall_notes: str,
       use_substitute_materials: int,
       stage_fields: dict,
       dep_fields: dict,
       qc_fields: dict,
   ) -> None
   ```
   Body uses `INSERT ... ON CONFLICT(po_number, style) DO UPDATE SET ...` covering all 165 data columns plus `updated_at = datetime('now')`.
3. Implement `list_all(companies: list[str] | None = None, allow_all: bool = False)`.
   - `allow_all=True` → no WHERE filter (admin path).
   - `allow_all=False` and `companies` non-empty → `WHERE company IN (?,...)`.
   - `allow_all=False` and `companies` is `None` or `[]` → return `[]` (do not run an `IN ()` query — that's a SQL error in SQLite).
   - `ORDER BY updated_at DESC NULLS LAST, id DESC`.
4. The view layer must pass `allow_all=admin_mode` — never let admin status leak through `companies=None`.
5. Implement `get(po_number, style)`.
6. Implement `delete(ids: list[int])` — deletes only the tracking record(s); does not touch `po_metadata` or `po_size_rows`.
7. Implement `list_untracked_pos(po_store)` from `po_size_rows`, grouped by `(po_number, COALESCE(style,''))`, joined to `po_metadata` for company/factory. See dev plan §1.2 for the exact SQL.
8. Register the store factory in `po_extractor/store/__init__.py`.
9. Register a Streamlit wrapper in `ui/stores.py` (not cached — lightweight, mirrors `get_boat_sample_store`).

Exit criteria:

- Non-admin company filters cannot accidentally return all records.
- Multi-style POs produce multiple Add New candidates.
- `overall_notes` and `use_substitute_materials` survive save/reload.
- Re-saving a record preserves untouched columns (no silent NULL-overwrites).

Verification:

- Temporary DB tests for create, update, list, get, delete.
- `companies=[]` with `allow_all=False` returns `[]` and does NOT execute an `IN ()` SQL.
- `companies=None` with `allow_all=False` returns `[]` (same guard).
- `allow_all=True` returns all records regardless of `companies`.
- Multi-style PO (same `po_number`, distinct `style` values in `po_size_rows`) produces one untracked candidate per style.
- Round-trip test: save record with `overall_notes="X"` and `use_substitute_materials=0`, reload, confirm both round-trip correctly.
- Partial-update test: save record with all fields, then call `upsert()` again touching only one field; confirm all other columns retain their prior values.

---

## Stage 3 - Readiness and Schedule Engine

Goal: implement pure business logic independently from Streamlit.

Files:

- `po_extractor/store/production_tracking_store.py`

Build:

1. Implement `compute_readiness(record)`. Logic per dev plan §1.2 — guard with `target in PREREQ_VALID[s]`; apply substitute-material auto-prereqs when `target in ALL_SAMPLE_STAGES`.
2. Implement `compute_schedule(record, start_date, override_days=None)`. Forward-schedule all 22 stages in `STAGES` order; Group A+B parallel (prereq-driven start); Group C+D sequential (also wait for previous stage).
3. Implement `compute_inspection_reminders(record, today)`.
4. Apply substitute-material gating to **every** stage in `ALL_SAMPLE_STAGES` (proto, fit, size_set, salesman, counter, **pp_sample**) — not only PP Sample. A sample stage cannot start until its material prereqs are Done.
5. Exclude inapplicable optional sample stages from readiness, schedule, delayed counts, and blocked counts.
6. Define one date convention for scheduling:
   start date plus expected days equals end date.
7. Recalculate the planning examples using that convention. Match the worked-out Scenarios A/B/C in dev plan verification §21–23.
8. Mark missing expected days as `missing_days=True` while treating duration as `0`.
9. **Critical-path algorithm** — use the deterministic predecessor-tracking approach from dev plan §1.2, NOT a vague "end == target_end" rule:
   - During the forward pass, each stage records its `critical_predecessor` — the prereq (or the immediate previous stage for Group C+D) whose `end` equals this stage's `start`.
   - Tie-break: among candidates with matching end times, pick the one with the lowest index in `STAGES`. Makes the result deterministic.
   - After forward pass: starting from `shipping`, walk the `critical_predecessor` chain and mark every visited stage `critical=True`. Stop when predecessor is `None`.
   - This produces exactly one critical path per schedule.

Exit criteria:

- PP Sample readiness matches default dependency and substitute-material rules.
- Cutting readiness respects PP Sample, Base Size Pattern, and Full Sized Pattern defaults.
- Schedule output is deterministic and consistent with verification examples.
- Critical path matches dev plan Scenarios A (base_size_pattern → pp_sample), B (sample_trim_purchase → pp_sample), and C (fabric_purchase → pp_sample).
- Re-Final reminders only appear when Final result is `Fail`.

Verification:

- Unit-style tests for substitute ON and substitute OFF.
- Test optional sample applicable ON/OFF (off must produce identical readiness to "stage doesn't exist").
- Test all three planning scenarios from the dev plan — shipping ends day 41 (A), 43 (B), 50 (C).
- Test critical-path tie-break: two prereqs ending on the same day → lower-index stage chosen.
- Test QC due, overdue, booked, no-deadline, and Re-Final cases (Re-Final reminder suppressed unless Final result is Fail).

---

## Stage 4 - UI Shell and Navigation

Goal: create a stable Tracking tab before building every form detail.

Files:

- `ui/session_keys.py`
- `ui/production_tracking_view.py`
- `app.py`

Build:

1. Add production tracking session keys (see dev plan §1.5):
   `PT_SELECTED_EDIT`, `PT_SELECTED_PLAN`, `PT_PLAN_OVERRIDE`, `PT_DELETE_CONFIRM`, `PT_ACTIVE_TAB`. All "selected" keys store the integer record `id`, **never** a concatenated string.
2. **Navigation must be `st.radio(horizontal=True)`, not `st.tabs()`.**
   - `st.tabs()` has no session-state index — programmatic switching from the dashboard Edit shortcut is impossible.
   - `st.segmented_control` has the same fundamental problem (widget key wins over external `index=` once set).
   - The dashboard Edit button MUST update **both** `PT_ACTIVE_TAB` AND the radio widget's own session-state key (`pt_tab_radio`) before calling `st.rerun()`. Setting only `PT_ACTIVE_TAB` will silently fail because `index=` is ignored once the widget key is in session_state.
   ```python
   # Correct dashboard Edit click handler:
   st.session_state[SK.PT_SELECTED_EDIT] = record["id"]
   st.session_state[SK.PT_ACTIVE_TAB]    = 2                  # index of "✏️ Edit Record"
   st.session_state["pt_tab_radio"]      = _TAB_LABELS[2]     # ← required dual-write
   st.rerun()
   ```
3. Add the Tracking tab in `app.py`.
4. View signature: `show_production_tracking_tab(user_cos: list[str], username: str, admin_mode: bool)`. Pass `admin_mode` explicitly — do not call `is_admin()` inside the view. Keeps privilege checks at one call site.
5. Use `allow_all=admin_mode` when listing records. When `admin_mode=False` and `user_cos` is empty, show `st.info("No companies assigned …")` and return — do not call `list_all` with an empty list.
6. Keep the first screen useful even when no records exist (empty-state messaging in Dashboard and Overview).

Exit criteria:

- Tracking tab appears for logged-in users.
- Admin sees all records.
- Non-admin sees only assigned-company records.
- Dashboard Edit action opens the edit view and preselects the record.

Verification:

- Manual Streamlit run.
- Test admin and non-admin user paths.
- Test empty-state UI.

---

## Stage 5 - Add New Workflow

Goal: allow users to start tracking existing PO/style rows.

Files:

- `ui/production_tracking_view.py`

Build:

1. Show untracked `PO + Style + Factory + Company` rows from store.
2. Pre-fill factory and company from PO metadata.
3. Apply defaults:
   optional samples off, substitute materials on, default dependency flags on.
4. Show a compact form for initial save.
5. Save all global, stage, dependency, and QC defaults through `upsert()`.

Exit criteria:

- A user can create a tracking record for each style in a PO.
- Creating one style does not hide other untracked styles from the same PO.
- Defaults match requirements.

Verification:

- Add a record from a single-style PO.
- Add records from a multi-style PO.
- Confirm saved record appears in dashboard and overview.

---

## Stage 6 - Edit Workflow

Goal: support full production tracking updates.

Files:

- `ui/production_tracking_view.py`

Build:

1. **Select record by integer `id` only.** The selectbox uses `format_func` to render labels (`f"{po_number} — {style}"`) but stores the integer id in `PT_SELECTED_EDIT`. Never use `po_number||style` strings — they break if either field contains the separator, and they don't survive `list_all()` reordering. See dev plan §1.5 "Record identity contract".
2. **Record-scoped widget keys (REQUIRED).** Every Edit-form widget uses `key=_wkey(record["id"], base)` where:
   ```python
   def _wkey(rid, base: str) -> str:
       return f"pt_edit_{rid}_{base}"
   ```
   Scoping by `rid` prevents the form from showing stale values when the user picks a different PO/style — switching records changes every widget key, so Streamlit recreates widgets with the new record's `value=` / `index=` defaults. Without this, the form silently shows the previously-selected record's data.
3. Render Group A, optional samples, PP Sample, Group C, Group D, and QC sections.
4. **Persist via `_build_payload_and_save(record, store, username)` — see dev plan §2.1 for the full helper.**
   Mandatory behaviours:
   - **Preserve on save for hidden widgets.** When an optional sample's `applicable=0` (its form fields aren't rendered) or Re-Final is suppressed (`insp_final_result ≠ 'Fail'`), `st.session_state.get()` returns `None`. The save handler MUST fall back to `record[...]` for missing widgets — otherwise hidden widgets silently overwrite saved data with `None` on every Save click. Implement via a `_read(widget_key, record_key)` helper.
   - **Centralized date normalization.** Every date widget value is converted to an ISO string (or `""`) before upsert via:
     ```python
     def _to_iso_or_empty(val) -> str:
         if isinstance(val, date): return val.isoformat()
         return val or ""
     ```
     Apply to all `_planned`, `_actual`, `_booking_deadline`, `_booking_date`, `_inspection_date` fields. Don't apply piecemeal — the existing P2 bug came from only converting `booking_deadline`.
   - **`pp_sample → cutting` dep is always written `1`.** It is system-enforced (see Stage 0 decision #8); no UI widget exposes it.
   - Persist: statuses, planned dates, actual dates, expected days, notes, applicability, dependency flags, QC fields, overall_notes, use_substitute_materials.
5. Show readiness badges for PP Sample and Cutting (`✅ Ready` / `⏳ Waiting on: …` / `⚪ No prerequisites set`).
6. Add delete confirmation with a clear second action. Pattern: first click sets `PT_DELETE_CONFIRM=True`; second click within the same render calls `store.delete([record["id"]])` and reruns.

Exit criteria:

- Editing any field survives save/reload.
- **Switching PO selectbox after typing in one record does not carry typed-but-unsaved values to the next record.** (Record-scoped keys prove themselves here.)
- **Toggling an optional sample off and saving does not lose its previously-entered data.** Re-enabling shows the prior values intact.
- **Setting Final result = Fail, filling Re-Final fields, setting Final result back = Pass, saving, then setting Final = Fail again shows the Re-Final fields still populated.** (Preserve-on-save proves itself here.)
- Optional samples hide from calculations when off.
- Substitute-material toggle immediately changes readiness after save.
- Delete removes only the tracking record, not PO history.

Verification:

- Edit every field type once.
- Switch selectbox between two records mid-edit; confirm the form refreshes cleanly with no leaked state.
- Toggle optional sample on → enter notes → toggle off → save → toggle back on → notes still present.
- Set Final = Fail → enter Re-Final booking deadline → set Final = Pass → save → set Final = Fail → Re-Final deadline still present.
- Toggle substitute materials on/off.
- Delete a tracking record and verify source PO/style returns to the Add New picker.

---

## Stage 7 - Dashboard and Overview

Goal: give operations a quick daily view.

Files:

- `ui/production_tracking_view.py`

Build:

1. Add summary metrics:
   total tracked, delayed stages, blocked records, completed today, QC bookings due.
2. Add dashboard cards with progress, group breakdown, status badges, QC alert, and edit shortcut.
3. Add filters:
   company, factory, only at-risk.
4. Add overview table with one row per tracked PO/style.
5. Use consistent readiness labels across dashboard, overview, and edit.

Exit criteria:

- Delayed records are clearly visible.
- Blocked records are clearly visible.
- QC due records are visible without opening each record.
- Filters work without losing selected record state.

Verification:

- Create records in Done, Delayed, Waiting, and QC due states.
- Confirm metric counts.
- Confirm filters.
- Confirm dashboard edit shortcut.

---

## Stage 8 - Planning View

Goal: let users run what-if production schedules without changing saved tracking data.

Files:

- `ui/production_tracking_view.py`

Build:

1. Select record by integer `id` stored in `PT_SELECTED_PLAN` (same pattern as Edit tab); start date defaults to today.
2. Show expected-day overrides for applicable stages only. Each number_input uses a record-scoped key: `_plan_wkey(selected_id, stage) = f"pt_plan_{selected_id}_{stage}"`.
3. Calculate schedule using `store.compute_schedule(record, start_date, override_days)`.
4. On Calculate click, assemble overrides and persist them under `PT_PLAN_OVERRIDE` so they survive reruns triggered by other widgets:
   ```python
   override_days = {s: st.session_state.get(_plan_wkey(rid, s), 0) or 0 for s in STAGES}
   st.session_state[SK.PT_PLAN_OVERRIDE] = override_days
   ```
5. Show estimated shipping date as `st.success("📦 Estimated Shipping: YYYY-MM-DD (N days)")`.
6. Show missing-day warnings — count stages with `missing_days=True` and non-skipped, display `st.warning(f"⚠️ {n} stage(s) have no expected days — treated as 0")`.
7. Highlight critical path. Style critical-path rows in the schedule table with a yellow background via `pandas.Styler.apply()`. Skipped rows are greyed; dates show as `—`.
8. Clearly keep overrides unsaved — never call `upsert()` from the Plan tab.

**Override persistence semantics (explicit, to avoid ambiguity):**

| User action | Override behaviour |
|------|---------|
| Switch nav radio to another tab and back | Overrides persist (record-scoped widget keys remain in session_state) |
| Change `Start Date` on the same record | Overrides persist; user re-clicks Calculate to see new shipping date |
| Pick a different PO/style in the Plan selectbox | Overrides for the **new** record start blank (different `_plan_wkey` namespace); the old record's overrides remain in session_state but are not displayed |
| Close and reopen the app | All overrides reset (session_state cleared) |

Exit criteria:

- Plan tab does not mutate the saved record (verified by reloading the Edit tab and confirming `expected_days` columns are unchanged after any number of Plan-tab Calculates).
- Schedule results match tests from Stage 3.
- Inapplicable optional stages are skipped (no widget rendered; appears as `—` in the result table).
- `PT_PLAN_OVERRIDE` is set after Calculate and survives reruns.

Verification:

- Run all three planning scenarios from the dev plan — shipping ends day 41 (A), 43 (B), 50 (C). Critical paths match.
- Edit override → switch to Edit tab → switch back to Plan tab → override still in number_input.
- Edit override on PO-A → switch selectbox to PO-B → PO-B shows fresh overrides (PO-A's didn't bleed in).
- Run a Plan calculation, then open the Edit tab and confirm `{stage}_expected_days` columns in the DB are unchanged.

---

## Stage 9 - QC Workflow

Goal: make inspection booking follow-up visible and reliable.

Files:

- `ui/production_tracking_view.py`

Build:

1. Show PPI, Inline, and Final inspections by default. Each section has 7 inputs (booking_deadline, reminder_days, booked, booking_date, inspection_date, result, notes) — all using record-scoped keys `_wkey(rid, f"{key}_{field}")`.
2. Show Re-Final fields only when Final result is `Fail`. Otherwise show a small caption: `🔁 Re-Final Inspection — appears when Final result is 'Fail'`.
3. **Save Re-Final fields even when hidden** via the preserve-on-save mechanism (Stage 6 build step 4). When Re-Final widgets aren't rendered, `st.session_state.get()` returns `None`; the `_read(widget_key, record_key)` helper falls back to `record[...]` so the previously-saved Re-Final values are written back unchanged. The user can fill Re-Final once when Final = Fail, toggle Final to Pass, and the Re-Final values persist in the DB — visible again if Final reverts to Fail.
4. Reminder logic ignores Re-Final unless `insp_final_result == 'Fail'` regardless of what's stored.
5. Show due and overdue banners inside Edit (`st.warning` for due-within-window; `st.error` for overdue).
6. Date fields (`booking_deadline`, `booking_date`, `inspection_date`) are normalized via `_to_iso_or_empty()` before upsert — same helper as the rest of the form.
7. Feed reminder counts into Dashboard (per-card `⚠️ N booking(s) due`) and Overview (QC column showing `⚠️ N` / `✅` / `—`).

Exit criteria:

- Booked inspections clear reminders immediately on save.
- Overdue inspections are visually distinct (`st.error` red banner).
- Re-Final behaves conditionally: hidden when Final result ≠ Fail; visible and editable when Final = Fail; its DB values survive Final-result transitions.
- Reminder counts in Dashboard/Overview match what's shown inside Edit.

Verification:

- Set booking_deadline = today+3, reminder_days = 7 → reminder fires (due).
- Set booking_deadline = yesterday → reminder fires with overdue styling.
- Tick Booked → reminder clears.
- Set booking_deadline = "" (blank) → no reminder.
- Set Final = Fail → enter Re-Final booking_deadline → save → set Final = Pass → save → set Final = Fail again → Re-Final booking_deadline is still present (proves preserve-on-save works for QC).
- Confirm Dashboard QC alert badge and Overview QC column update after each save.

---

## Stage 10 - Final Wiring, Version, and Regression Check

Goal: finish the feature with clear documentation and confidence.

Files:

- `app.py`
- `docs/requirements_production_tracking.md`
- `docs/development_plan_production_tracking.md`
- `docs/build_plan_production_tracking_by_stages.md`

Build:

1. Bump `APP_VERSION`.
2. Update requirements and development docs to match the implemented behavior.
3. Add final verification notes.
4. Run compile checks.
5. Run focused store/business-logic tests.
6. Launch Streamlit and manually verify the main workflows.

Exit criteria:

- No known contradictions remain between requirements, development plan, and implementation.
- Main workflows pass manual verification.
- The build can be handed to users for trial.

Verification:

- `python -m compileall -q po_extractor ui auth app.py`
- Store CRUD tests (Stage 2 verification list).
- Readiness/schedule/QC tests (Stage 3 verification list).
- **Full UI verification — run all 31 numbered steps from dev plan §"Verification Steps":**
  - Dashboard (steps 1–6)
  - Stage Tracking (steps 7–15)
  - Substitute Materials Flag (steps 16–20)
  - Planning Module — Scenarios A/B/C (steps 21–24)
  - QC Inspections (steps 25–31)
- Regression check on the seven other tabs (GIII, Sky East, Fabric DB, Fabric Mapping, Colors, Summary, Releases) — confirm none broke from the index shift in `app.py`.

---

## Recommended Build Order

1. Stage 0: confirm logic
2. Stage 1: schema
3. Stage 2: store CRUD and access control
4. Stage 3: pure logic helpers
5. Stage 4: UI shell and navigation
6. Stage 5: Add New
7. Stage 6: Edit
8. Stage 7: Dashboard and Overview
9. Stage 8: Plan
10. Stage 9: QC
11. Stage 10: final wiring and regression check

This order keeps the hardest risks early: identity, access control, persistence, and calculation logic.
