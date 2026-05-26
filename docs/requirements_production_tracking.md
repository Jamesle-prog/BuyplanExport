# Production Stage Tracking — Requirements Document

> **Version**: 1.0  
> **Module**: 🏭 Tracking tab  
> **App**: PO Automation GIII

---

## 1. Overview

Add a **Production Stage Tracking** module to PO Automation GIII. Each PO/style is tracked through 22 manufacturing stages in four groups. A dependency system computes readiness for PP Sample and Cutting based on user-configured prerequisite links. A planning module forward-schedules all stages from a chosen start date to estimate delivery. A QC Inspection tracker records booking deadlines, reminder windows, booked status, and results for three inspection types (PPI, Inline, Final) plus a conditional Re-Final.

---

## 2. Problem Statement

No current mechanism records whether trim/fabric is sourced, patterns cut, samples approved, or production stages completed — nor whether the right materials and patterns are ready for the right stage.

---

## 3. Goals

- Full pipeline visibility per PO/style, from pre-production procurement through post-production sampling and shipping.
- Flexible sampling: only PP Sample is always required; Proto, Fit, Size Set, Salesman, and Counter samples are optional per PO and can be configured as prerequisites for PP Sample when applicable.
- Computed readiness for PP Sample and Cutting driven by the dependency matrix.
- Forward-scheduling planning module estimates delivery date from any start date.
- QC inspection booking tracker with per-client deadlines, configurable reminders, booked flag, and results for PPI, Inline, Final, and (conditional) Re-Final inspections.

---

## 4. Scope

### In Scope
- New **🏭 Tracking** tab with Dashboard, Overview, Edit, Add New, and Plan sub-tabs.
- 22 stages in 4 groups (see FR-01).
- Per stage: Status, Planned Date, Actual Date, Expected Days, Notes.
- Optional sample stages also have an **Applicable** toggle per PO.
- Applicable optional samples can be flagged as prerequisites for PP Sample.
- Dependency matrix; computed readiness for PP Sample and Cutting.
- Forward-scheduling algorithm with critical path.
- QC inspection tracker: PPI, Inline, Final, Re-Final (conditional); booking deadline, reminder window, booked flag, booking date, inspection date, result, notes per type.
- Access control by `user_cos`.

### Out of Scope (v1)
- Email/push notifications.
- Export to Excel.
- Stage-level audit trail.
- Hard-blocking entry when prerequisites unmet.
- Per-client default booking deadlines master table.

---

## 5. User Stories

| ID | As a… | I want to… | So that… |
|----|-------|-----------|----------|
| US-01 | Operations user | See all tracked POs with per-stage badges | Assess pipeline health at a glance |
| US-02 | Operations user | Mark optional sample stages as applicable or N/A per PO | Non-applicable stages don't clutter tracking |
| US-03 | Operations user | Flag an applicable optional sample as required before PP Sample | Enforce my factory's specific sample approval chain |
| US-04 | Operations user | See computed readiness for PP Sample and Cutting | Know exactly what is blocking progress |
| US-05 | Operations user | Run a what-if schedule from any start date | Estimate delivery and identify the critical path |
| US-06 | Operations user | Override expected days in the planner without saving | Run scenarios without affecting tracked data |
| US-07 | Admin | See all companies' records | Full cross-operation visibility |
| US-08 | Operations user | See which QC bookings are due or overdue today | Take action before deadlines are missed |
| US-09 | Operations user | Record QC inspection results per type | Track pass/fail outcomes and trigger Re-Final when needed |

---

## 6. Functional Requirements

### FR-01 — Stage Definitions (22 stages, 4 groups)

All 22 stages belong to one of four groups. Scheduling behaviour differs by group.

#### Group A — Pre-Production (all parallel, always applicable)

| # | Key | Display Name | Notes |
|---|-----|--------------|-------|
| 1 | `trim_purchase` | Trim Purchase | Bulk trim procurement |
| 2 | `trim_layout` | Trim Layout | Trim card/placement approval |
| 3 | `fabric_purchase` | Fabric Purchase | Bulk fabric procurement |
| 4 | `fabric_color_ld` | Fabric Color (LD) | Lab Dip approval |
| 5 | `base_size_pattern` | Base Size Pattern | Pattern in base/sample size |
| 6 | `full_sized_pattern` | Full Sized Pattern | Graded to all sizes |
| 7 | `sample_trim_purchase` | Sample Trim Purchase | Trim purchased specifically for samples |
| 8 | `sample_fabric_purchase` | Sample Fabric Purchase | Fabric purchased specifically for samples |

> All 8 run **concurrently** — no enforced order among them.

> **Sample vs. bulk materials:** The **Use Substitute Materials** flag (FR-03b) controls whether sample-specific or bulk Group A stages automatically gate the sample pipeline.

#### Group B — Pre-Production Samples (parallel; PP Sample compulsory)

| # | Key | Display Name | Default Applicable | Notes |
|---|-----|--------------|-------------------|-------|
| 9 | `proto_sample` | Proto Sample | Optional (OFF) | First prototype check |
| 10 | `fit_sample` | Fit Sample | Optional (OFF) | Fit on model; may repeat |
| 11 | `size_set_sample` | Size Set Sample | Optional (OFF) | Grading verification |
| 12 | `salesman_sample` | Salesman Sample (SMS) | Optional (OFF) | Trade show / buyer presentation |
| 13 | `counter_sample` | Counter Sample | Optional (OFF) | Match buyer reference |
| 14 | `pp_sample` | PP Sample | **Compulsory (ON)** | Pre-production approval; gates Cutting |

> Stages 9–13 are **optional** — toggled on/off per PO. When off, excluded from all computations. When on, they can be flagged as prerequisites for PP Sample. PP Sample is always applicable.

#### Group C — Production (sequential)

| # | Key | Display Name | Notes |
|---|-----|--------------|-------|
| 15 | `cutting` | Cutting | |
| 16 | `sewing` | Sewing | |
| 17 | `top_sample` | TOP Sample | First pieces off the production line |
| 18 | `packing` | Packing | |
| 19 | `qa` | QA | |
| 20 | `final_qa` | Final QA | |

#### Group D — Post-Production (sequential)

| # | Key | Display Name | Notes |
|---|-----|--------------|-------|
| 21 | `boat_sample` | Boat Sample | Pulled from final shipment before dispatch |
| 22 | `shipping` | Shipping | |

---

### FR-02 — Stage Data Fields

All stages have:

| Field | Type | Notes |
|-------|------|-------|
| Status | Enum | `Not Started` / `In Progress` / `Done` / `Delayed` |
| Planned Date | Date | When this stage is expected to start/complete |
| Actual Date | Date | When it actually completed |
| Expected Days | Integer | Duration estimate used by the planning module |
| Notes | Text | Free-form |

Optional sample stages (9–13) additionally have an **Applicable** toggle. When `applicable = 0`:
- Stage is hidden from the tracking form (toggle shown to re-enable under an expander)
- Excluded from readiness and schedule computation
- Not counted in Blocked/Delayed metrics

---

### FR-03 — Dependency Matrix and Defaults

The dependency matrix controls which stages gate **PP Sample** and **Cutting**. It is configurable per PO.

**Valid (source → target) pairs:**

| Source | Valid Targets |
|--------|--------------|
| Trim Purchase | PP Sample, Cutting |
| Trim Layout | PP Sample, Cutting |
| Fabric Purchase | PP Sample, Cutting |
| Fabric Color (LD) | PP Sample, Cutting |
| Sample Trim Purchase | PP Sample, Cutting |
| Sample Fabric Purchase | PP Sample, Cutting |
| Base Size Pattern | PP Sample, Cutting |
| Full Sized Pattern | Cutting only |
| Proto Sample *(if applicable)* | PP Sample |
| Fit Sample *(if applicable)* | PP Sample |
| Size Set Sample *(if applicable)* | PP Sample |
| Salesman Sample *(if applicable)* | PP Sample |
| Counter Sample *(if applicable)* | PP Sample |
| PP Sample | Cutting | **System-enforced — always ON, not user-configurable** |

**System defaults for every new record:**

| Dependency | Default | User-configurable? |
|-----------|---------|--------------------|
| Base Size Pattern → PP Sample | **ON** | Yes |
| Base Size Pattern → Cutting | **ON** | Yes |
| Full Sized Pattern → Cutting | **ON** | Yes |
| PP Sample → Cutting | **ON** | **No — system-enforced** |
| All other links | OFF | Yes |

> **Why PP Sample → Cutting is locked**: pre-production sample approval before bulk cutting is a fundamental constraint of the garment manufacturing workflow. Allowing the user to disable it would let the planner produce schedules that violate physical reality. The dep column is preserved in the schema (always written as `1`) so the existing computational logic remains uniform across all (source, target) pairs.

---

### FR-03b — Use Substitute Materials Flag

Each tracking record has a **Use Substitute Materials** toggle (`use_substitute_materials`, default **ON**). This flag applies an **automatic conditional dependency** to all sample stages (proto through pp_sample), in addition to the configurable matrix:

| Flag | Automatic rule |
|------|----------------|
| **Substitute ON** (default) | `sample_trim_purchase` and `sample_fabric_purchase` must be Done before any sample starts. Bulk Group A (Trim Purchase, Trim Layout, Fabric Purchase, Fabric Color LD) runs in parallel — does **not** automatically gate samples. |
| **Substitute OFF** | All four bulk Group A stages must be Done before any sample starts. `sample_trim_purchase` / `sample_fabric_purchase` are tracked but do **not** automatically gate samples. |

> When the flag is toggled, a contextual notice explains the effect on the sample pipeline.

> **Effect on a fresh record (default state — substitute=ON, all stages Not Started):**  
> PP Sample readiness = `⏳ Waiting on: Sample Trim Purchase, Sample Fabric Purchase, Base Size Pattern`.  
> "Sample Trim/Fabric Purchase" come from the FR-03b auto-rule; "Base Size Pattern" comes from the default dep matrix (`base_size_pattern_req_pp_sample = ON`).  
> Cutting is not a sample stage, so the auto-rule does **not** apply to it directly.

---

### FR-04 — Computed Readiness

Computed for **PP Sample** and **Cutting** only. Display-only, non-blocking.

| Status | Condition | Display |
|--------|-----------|---------|
| Ready | All tagged + applicable prereqs Done | `✅ Ready` |
| Waiting | One or more tagged + applicable prereqs not Done | `⏳ Waiting on: [names]` |
| No prereqs | No prereqs tagged | `⚪ No prerequisites set` |

---

### FR-05 — Dashboard Tab

The **📊 Dashboard** is the landing view. It shows per-PO progress cards in a 2-column grid.

**Each card contains:**
- Header: `PO# / Style` + factory name
- Overall progress bar: `N / M stages done`
- Group breakdown: `Pre-Prod: N/8 · Samples: N/M · Production: N/6 · Post: N/2`
- Status badge row: one emoji per stage in order
- QC alert: `⚠️ N booking(s) due` or `✅ QC OK`
- Border colour: red (Delayed) / orange (Blocked) / green (all Done) / grey (in progress)
- `✏️ Edit` shortcut button → jumps to Edit Record sub-tab for that PO

Filters: Company multiselect, Factory text, "Show only at-risk" toggle.

---

### FR-05b — Overview Table

Columns: PO #, Style, Factory + one emoji badge per applicable stage; `—` for inapplicable optional stages. PP Sample and Cutting columns append a readiness suffix. QC column: `⚠️ N` / `✅` / `—`.

---

### FR-06 — Filters

Company (multiselect), Factory (text), Show only blocked/delayed (toggle).

---

### FR-07 — Summary Metrics

Five `st.metric` tiles at the top of the tab:

| Metric | Definition |
|--------|-----------|
| Total Tracked | Count of all records visible to user |
| Delayed Stages | Count of individual stages with status = Delayed |
| Blocked Stages | Count of records where PP Sample or Cutting = `⏳ Waiting` |
| Completed Today | Count of stages whose actual date = today |
| QC Bookings Due | Count of records with ≥1 due/overdue booking reminder today |

---

### FR-08 — PO Linking

The Add New picker shows only untracked `(po_number, style)` pairs sourced from `po_size_rows JOIN po_metadata`. `po_size_rows` is the correct source because a single PO can carry multiple distinct styles; `po_metadata` holds only one `style` column per PO and would miss multi-style orders. Factory and company auto-fill from the joined `po_metadata` row. If all PO/style pairs are already tracked, `st.info("All POs are already being tracked.")` is shown instead of the form.

---

### FR-09 — Delete

Delete button in the Edit form triggers a confirmation prompt. Confirmed deletion removes the record permanently.

---

### FR-10 — Access Control

Non-admin users see only records belonging to their assigned `user_cos` companies. Admin users see all companies.

---

### FR-11 — Expected Days

Every stage has an `expected_days` integer field. Used by the planning module (FR-12). Stages without a value are treated as 0 days and flagged with a `⚠️ not set` caption in the Plan tab.

---

### FR-12 — Planning Module

The **📅 Plan** sub-tab provides forward-scheduling from a chosen start date.

**Scheduling algorithm:**

- Group A and B stages: start = max(end of all applicable + tagged prereqs), defaulting to `start_date` if no prereqs.
- Group C and D stages: sequential — must also wait for the previous stage to finish.
- Inapplicable stages are skipped (start = end = previous cursor).

**Critical path**: back-traced from Shipping — the longest chain of stages whose end times equal the Shipping end date.

**Outputs:**
- Banner: `📦 Estimated Shipping: YYYY-MM-DD (N days from start date)`
- Warning if any stage has no expected days set
- Schedule table: Stage · Group · Exp.Days · Est.Start · Est.End · Critical Path ✓  
  (critical path rows highlighted yellow; skipped rows greyed with `—` for dates)

What-if day overrides in the Plan tab do **not** persist — they are not saved back to the record.

---

### FR-13 — QC Inspection Tracking

Four inspection types are tracked per PO/style:

| Key | Display Name | Conditionality |
|-----|-------------|----------------|
| `insp_ppi` | Pre-Production Inspection (PPI) | Always shown |
| `insp_inline` | Inline Inspection | Always shown |
| `insp_final` | Final Inspection | Always shown |
| `insp_refinal` | Re-Final Inspection | Shown only when `insp_final_result = 'Fail'` |

**Per-inspection fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| Booking Deadline | Date | — | Date by which the booking must be placed |
| Reminder Days | Integer | 7 | Days before deadline to trigger reminder |
| Booked | Boolean | No | Whether the inspection has been booked |
| Booking Date | Date | — | Actual date the booking was placed |
| Inspection Date | Date | — | Scheduled/actual inspection date |
| Result | Enum | Pending | Pending / Pass / Conditional Pass / Fail / N/A |
| Notes | Text | — | Free-form |

**Reminder logic** (computed at display time, not stored):
- Skip if already booked.
- Skip if no booking deadline set.
- Skip Re-Final unless `insp_final_result = 'Fail'`.
- Alert triggered when `today >= booking_deadline − reminder_days`.
- Overdue when `today > booking_deadline` (shown as `st.error`).

**Re-Final conditionality**: hidden with a placeholder caption until Final result = Fail. Fields are saved normally regardless — they are simply ignored in reminder logic until Final fails.

**Result options**: `Pending` · `Pass` · `Conditional Pass` · `Fail` · `N/A`

---

## 7. Non-Functional Requirements

- No new Python dependencies (no plotly/matplotlib; table-only output in Plan tab).
- Wide-table SQLite schema; `compute_readiness()`, `compute_schedule()`, and `compute_inspection_reminders()` are pure Python with no extra DB queries.
- Migration-safe: uses `ALTER TABLE ADD COLUMN` for all new columns so existing data is never lost.
