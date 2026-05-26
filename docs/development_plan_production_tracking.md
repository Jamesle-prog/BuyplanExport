# Production Stage Tracking — Development Plan

> **Version**: 1.0  
> **Module**: 🏭 Tracking tab  
> **App**: PO Automation GIII  
> **Requirements**: See `docs/requirements_production_tracking.md`

---

## Overview

This document describes the implementation steps to add the Production Stage Tracking module. Work is divided into three phases: Data Layer, UI Layer, and Version/Documentation.

**Files to create (new):**
- `po_extractor/store/production_tracking_store.py`
- `ui/production_tracking_view.py`
- `docs/requirements_production_tracking.md`
- `docs/development_plan_production_tracking.md`

**Files to modify:**
- `po_extractor/store/_production_tracking_schema.py` (replace stub)
- `po_extractor/store/__init__.py`
- `ui/stores.py`
- `ui/session_keys.py`
- `app.py`

---

## Phase 1 — Data Layer

### Step 1.1 — Replace Schema Stub

**File**: `po_extractor/store/_production_tracking_schema.py`

Replace the existing 6-column stub with the full 173-column schema and all exported constants.

**Table layout:**

```
production_tracking
────────────────────────────────────────────────────
id            INTEGER PRIMARY KEY AUTOINCREMENT
po_number     TEXT NOT NULL
style         TEXT NOT NULL DEFAULT ''
factory       TEXT DEFAULT ''
company       TEXT DEFAULT ''        ← indexed
overall_notes TEXT DEFAULT ''
updated_at    TEXT
updated_by    TEXT
UNIQUE(po_number, style)

── Global flag ──────────────────────────────────────
use_substitute_materials INTEGER DEFAULT 1

── Group A (8 stages × 5 fields = 40 cols) ─────────
{stage}_{status|planned|actual|notes|expected_days}
stage ∈ {trim_purchase, trim_layout, fabric_purchase, fabric_color_ld,
         base_size_pattern, full_sized_pattern,
         sample_trim_purchase, sample_fabric_purchase}

── Group B optional samples (5 stages × 6 fields = 30 cols) ──
{stage}_{status|planned|actual|notes|expected_days|applicable}
applicable DEFAULT 0 (off by default)
stage ∈ {proto_sample, fit_sample, size_set_sample, salesman_sample, counter_sample}

── PP Sample (1 stage × 5 fields = 5 cols) ─────────
pp_sample_{status|planned|actual|notes|expected_days}

── Group C Production (6 stages × 5 fields = 30 cols) ──
stage ∈ {cutting, sewing, top_sample, packing, qa, final_qa}

── Group D Post-Production (2 stages × 5 fields = 10 cols) ──
stage ∈ {boat_sample, shipping}

── Dependency matrix (21 boolean cols) ─────────────
trim_purchase_req_{pp_sample|cutting}            DEFAULT 0
trim_layout_req_{pp_sample|cutting}              DEFAULT 0
fabric_purchase_req_{pp_sample|cutting}          DEFAULT 0
fabric_color_ld_req_{pp_sample|cutting}          DEFAULT 0
sample_trim_purchase_req_{pp_sample|cutting}     DEFAULT 0
sample_fabric_purchase_req_{pp_sample|cutting}   DEFAULT 0
base_size_pattern_req_{pp_sample|cutting}        DEFAULT 1  ← ON
full_sized_pattern_req_cutting                   DEFAULT 1  ← ON
{proto|fit|size_set|salesman|counter}_sample_req_pp_sample  DEFAULT 0
pp_sample_req_cutting                            DEFAULT 1  ← ON

── QC Inspections (4 types × 7 fields = 28 cols) ────
{key}_{booking_deadline|reminder_days|booked|booking_date|inspection_date|result|notes}
reminder_days DEFAULT 7, result DEFAULT 'Pending'
key ∈ {insp_ppi, insp_inline, insp_final, insp_refinal}

Total: 8 base + 1 flag + 40(A) + 30(B-opt) + 5(PP) + 30(C) + 10(D) + 21(dep) + 28(QC) = 173 cols
```

**Exported constants** (all consumed by the store and UI):

```python
STAGES_GROUP_A        # 8 stages
STAGES_GROUP_B_OPTIONAL  # 5 optional sample stages
STAGES_GROUP_B        # STAGES_GROUP_B_OPTIONAL + ["pp_sample"]
STAGES_GROUP_C        # 6 production stages
STAGES_GROUP_D        # 2 post-production stages
STAGES                # all 22, in order

STAGE_LABELS          # {key: display_name}
STATUS_OPTIONS        # ["Not Started","In Progress","Done","Delayed"]
STATUS_EMOJI          # {status: emoji}

PREREQ_VALID          # {source: [valid_target, ...]} — 14 entries
PREREQ_TARGETS        # ["pp_sample", "cutting"]
SUBSTITUTE_SAMPLE_PREREQS  # ["sample_trim_purchase", "sample_fabric_purchase"]
BULK_MATERIAL_PREREQS      # ["trim_purchase","trim_layout","fabric_purchase","fabric_color_ld"]
ALL_SAMPLE_STAGES          # STAGES_GROUP_B (stages 9–14)
DEFAULT_DEP_ON             # set of 4 dep column names defaulting to 1

STAGE_FIELDS               # ["status","planned","actual","notes","expected_days"]
OPTIONAL_STAGE_EXTRA_FIELDS  # ["applicable"]
OPTIONAL_SAMPLE_STAGES     # STAGES_GROUP_B_OPTIONAL

QC_INSPECTIONS        # ["insp_ppi","insp_inline","insp_final","insp_refinal"]
QC_INSPECTION_LABELS  # {key: display_name}
QC_RESULT_OPTIONS     # ["Pending","Pass","Conditional Pass","Fail","N/A"]
QC_FIELDS             # ["booking_deadline","reminder_days","booked",
                      #  "booking_date","inspection_date","result","notes"]

def dep_col(source, target) -> str  # returns f"{source}_req_{target}"
```

**Migration strategy**: `_ensure_schema()` reads `PRAGMA table_info(production_tracking)` and runs `ALTER TABLE ADD COLUMN` for every column that is missing. This is safe on the existing stub and idempotent on future upgrades.

> **Dead columns from the old stub**: the previous stub defined `ex_factory_date`, `etd`, `eta`, `carrier`, `vessel`, `bl_number`, `status`, `notes`. SQLite has no `DROP COLUMN` we can safely call in a migration, and the new schema does not reference these. They will remain in the table as unused dead columns and the application code will simply ignore them. This is intentional and consistent with the migration-safe contract — no data loss from any prior writes.

---

### Step 1.2 — Create Store Class

**File**: `po_extractor/store/production_tracking_store.py` *(new)*

```python
class ProductionTrackingStore(BaseSQLiteStore):
    def __init__(self, db_path: str)
    def _ensure_schema(self) -> None   # migration via PRAGMA table_info

    # ── CRUD ─────────────────────────────────────────────────────────────────
    def upsert(self, po_number, style, factory, company, updated_by,
               overall_notes: str,
               use_substitute_materials: int,
               stage_fields: dict, dep_fields: dict, qc_fields: dict) -> None
        # overall_notes and use_substitute_materials are record-level ("global") fields
        # that don't belong in stage_fields / dep_fields / qc_fields.  They MUST be
        # explicit params here — if they were absent from the signature the UI's Save
        # button would silently drop them on every write.
        # INSERT ... ON CONFLICT DO UPDATE SET for all 173 data columns

    def list_all(self, companies: list[str] | None = None) -> list[dict]
        # SELECT * FROM production_tracking [WHERE company IN (?,...)]
        # ORDER BY updated_at DESC NULLS LAST, id DESC
        #
        # NULLS LAST keeps fresh-but-unsaved records from jumping to the top
        # before they've actually been updated.  Secondary `id DESC` gives a
        # stable order among records that share an updated_at (e.g. bulk seed).
        # Requires SQLite 3.30+ which has been ubiquitous since 2019; the
        # bundled Python sqlite3 module is fine.

    def get(self, po_number: str, style: str) -> dict | None

    def delete(self, ids: list[int]) -> int

    def list_untracked_pos(self, po_store: POStore) -> list[dict]
        # Source: po_size_rows (not po_metadata) — one row per (po_number, style) pair.
        # po_metadata has only one style column per PO; po_size_rows holds the
        # actual per-style breakdown when a single PO covers multiple styles.
        #
        # SQL (executed against the po_store DB via an ATTACH or shared db_path):
        #   SELECT DISTINCT s.po_number,
        #                   COALESCE(s.style, '') AS style,
        #                   m.factory, m.company
        #   FROM po_size_rows s
        #   JOIN po_metadata  m ON m.po_number = s.po_number
        #   WHERE (s.po_number, COALESCE(s.style,'')) NOT IN
        #         (SELECT po_number, style FROM production_tracking)
        #   ORDER BY s.po_number, s.style
        #
        # Implementation note: both tables live in the same DB file (po_history.db),
        # so the query is run with a second sqlite3 connection to po_store.db_path
        # (not self.db_path / production tracking DB).  Use po_store.db_path directly.

    # ── Compute helpers (static, pure Python) ────────────────────────────────
    @staticmethod
    def compute_readiness(record: dict) -> dict[str, str]
        # Returns {"pp_sample": "ready|waiting:...|no_prereqs",
        #          "cutting":   "ready|waiting:...|no_prereqs"}
        # Logic:
        #   auto_prereqs = SUBSTITUTE_SAMPLE_PREREQS if use_substitute_materials else BULK_MATERIAL_PREREQS
        #   For each target in PREREQ_TARGETS:
        #     matrix_tagged = [s for s in PREREQ_VALID
        #                      if target in PREREQ_VALID[s]   ← guard required
        #                      and record.get(dep_col(s, target), 0)
        #                      and record.get(s+"_applicable", 1)]
        #     auto_tagged = auto_prereqs if target in ALL_SAMPLE_STAGES else []
        #     tagged = deduplicated union
        #     pending = [s for s in tagged if record.get(s+"_status") != "Done"]

    @staticmethod
    def compute_schedule(record, start_date, override_days=None) -> dict[str, dict]
        # Forward-schedules all 22 stages in STAGES order.
        # schedule = {}
        # auto_prereqs = SUBSTITUTE_SAMPLE_PREREQS if record["use_substitute_materials"] else BULK_MATERIAL_PREREQS
        #
        # For each stage in STAGES:
        #   applicable = record.get(stage+"_applicable", 1)  # Group A/C/D always 1
        #   days = (override_days or {}).get(stage) or record.get(stage+"_expected_days") or 0
        #
        #   if not applicable:
        #     schedule[stage] = {start: current_end, end: current_end, days:0, skipped:True, critical:False}
        #     continue
        #
        #   # Configurable matrix prereqs for this stage
        #   prereqs = [s for s in PREREQ_VALID
        #              if stage in PREREQ_VALID[s]     ← guard: only valid (source→stage) pairs
        #              and record.get(dep_col(s, stage), 0)
        #              and record.get(s+"_applicable", 1)
        #              and s in schedule]
        #
        #   # FR-03b: substitute-material auto-prereqs injected per sample stage
        #   # This applies to EVERY stage in ALL_SAMPLE_STAGES (proto → pp_sample),
        #   # not just pp_sample.  A sample stage cannot start until its material
        #   # prereqs are done, regardless of the matrix configuration.
        #   if stage in ALL_SAMPLE_STAGES:
        #     prereqs = list(dict.fromkeys(prereqs + [s for s in auto_prereqs if s in schedule]))
        #
        #   # Groups A+B: parallel — start driven by prereqs only
        #   if stage in STAGES_GROUP_A or stage in STAGES_GROUP_B:
        #     earliest = max((schedule[p]["end"] for p in prereqs), default=start_date)
        #
        #   # Groups C+D: sequential — also wait for previous stage to finish
        #   else:
        #     prev = STAGES[STAGES.index(stage) - 1]
        #     earliest = max(
        #         max((schedule[p]["end"] for p in prereqs), default=start_date),
        #         schedule[prev]["end"],
        #     )
        #
        #   # Determine THIS stage's critical predecessor — the prereq (or
        #   # previous stage for sequential groups) whose end time equals
        #   # this stage's start time.  Tie-breaker: prefer the prereq with
        #   # the lowest index in STAGES so back-trace is deterministic.
        #   candidates = list(prereqs)
        #   if stage in STAGES_GROUP_C or stage in STAGES_GROUP_D:
        #     candidates.append(prev)   # the immediate predecessor by group order
        #   critical_pred = None
        #   for c in sorted(candidates, key=STAGES.index):
        #     if c in schedule and schedule[c]["end"] == earliest:
        #       critical_pred = c
        #       break
        #
        #   end = earliest + timedelta(days=days)
        #   schedule[stage] = {start:earliest, end:end, days:days,
        #                       missing_days:(days==0), skipped:False,
        #                       critical:False, critical_predecessor:critical_pred}
        #   current_end = end   # cursor used only for Group C/D sequential chaining
        #
        # ── Critical-path back-trace (deterministic) ──────────────────────
        # Starting from the LAST applicable stage (shipping unless it's been
        # made inapplicable somehow), walk the critical_predecessor chain and
        # mark every visited stage critical=True.
        #   cursor = "shipping"
        #   while cursor is not None:
        #     schedule[cursor]["critical"] = True
        #     cursor = schedule[cursor]["critical_predecessor"]
        #
        # This produces exactly one critical path per schedule (not a set of
        # paths) and exactly matches the verification scenarios.
        # Returns complete schedule dict.

    @staticmethod
    def compute_inspection_reminders(record: dict, today: date) -> list[dict]
        # For each QC_INSPECTION key:
        #   Skip insp_refinal unless insp_final_result == "Fail"
        #   Skip if booked or no deadline set
        #   Alert if today >= deadline - reminder_days
        #   Returns list of {"key", "label", "deadline", "overdue"} dicts
```

---

### Step 1.3 — Register in Store Factory

**File**: `po_extractor/store/__init__.py`

Add after existing imports and factories:

```python
from .production_tracking_store import ProductionTrackingStore

def get_production_tracking_store() -> ProductionTrackingStore:
    """Return a fresh ProductionTrackingStore wired to the canonical DB."""
    return ProductionTrackingStore(_db_path())
```

Add `"ProductionTrackingStore"` and `"get_production_tracking_store"` to `__all__`.

---

### Step 1.4 — Register in Streamlit Stores

**File**: `ui/stores.py`

Add to imports:
```python
from po_extractor.store import (
    ...,
    ProductionTrackingStore,
    get_production_tracking_store as _get_pt_store,
)
```

Add wrapper (not cached — lightweight, like `get_boat_sample_store`):
```python
def get_production_tracking_store() -> ProductionTrackingStore:
    """Return a fresh ProductionTrackingStore (not cached — lightweight wrapper)."""
    return _get_pt_store()
```

---

### Step 1.5 — Add Session Keys

**File**: `ui/session_keys.py`

Add to the `SK` class under a new `# ── Production Tracking ──` comment:

```python
PT_SELECTED_EDIT  = "pt_selected_edit"   # int — record id selected in Edit tab (None if none)
PT_SELECTED_PLAN  = "pt_selected_plan"   # int — record id selected in Plan tab (None if none)
PT_PLAN_OVERRIDE  = "pt_plan_override"   # dict[stage, int] — what-if day overrides
PT_DELETE_CONFIRM = "pt_delete_confirm"  # bool — delete confirmation shown
PT_ACTIVE_TAB     = "pt_active_tab"      # int — active sub-tab index (0=Dashboard)
```

**Record identity contract**: `PT_SELECTED_EDIT` and `PT_SELECTED_PLAN` store the integer `record["id"]` primary key — never a concatenated string. Using the id avoids parsing ambiguity when `po_number` or `style` might contain the separator character, and survives records being reordered in `list_all()`. The selectbox `format_func` converts ids to display labels at render time.

---

## Phase 2 — UI Layer

### Step 2.1 — Create View Module

**File**: `ui/production_tracking_view.py` *(new)*

**Entry point:**
```python
def show_production_tracking_tab(user_cos: list[str], username: str) -> None:
    from auth.users import is_admin
    from ui.stores import get_production_tracking_store, get_store
    store = get_production_tracking_store()
    po_store = get_store()
    today = date.today()
    # ── Access control: non-admin with empty user_cos must see zero records,
    # not all records.  Pass None only for admins (meaning "no filter").
    admin = is_admin(username)
    companies = None if admin else (user_cos or [])
    # Guard: empty list → return nothing (avoids "IN ()" SQL error)
    if companies is not None and len(companies) == 0:
        st.info("No companies assigned to your account. Contact an administrator.")
        return
    records = store.list_all(companies=companies)
    readiness_map = {r["id"]: store.compute_readiness(r) for r in records}
    reminder_map  = {r["id"]: store.compute_inspection_reminders(r, today) for r in records}
    _render_metrics(records, readiness_map, reminder_map, today)

    # ── Tab navigation via st.radio so PT_ACTIVE_TAB can control it.
    # st.tabs() has no session-state index — programmatic switching (e.g.
    # the Dashboard ✏️ Edit shortcut) is impossible with st.tabs().
    _TAB_LABELS = ["📊 Dashboard", "📋 Overview", "✏️ Edit Record", "➕ Add New", "📅 Plan"]
    active = st.radio(
        "##pt_nav", _TAB_LABELS, horizontal=True,
        index=st.session_state.get(SK.PT_ACTIVE_TAB, 0),
        key="pt_tab_radio",
        label_visibility="collapsed",
    )
    # Persist active tab so it survives reruns driven by other widgets
    st.session_state[SK.PT_ACTIVE_TAB] = _TAB_LABELS.index(active)

    if   active == _TAB_LABELS[0]: _render_dashboard_tab(records, readiness_map, reminder_map, today)
    elif active == _TAB_LABELS[1]: _render_overview_table(records, readiness_map, reminder_map, today)
    elif active == _TAB_LABELS[2]: _render_edit_tab(records, readiness_map, store, username, today)
    elif active == _TAB_LABELS[3]: _render_add_tab(store, po_store, username)
    elif active == _TAB_LABELS[4]: _render_plan_tab(records, store)
```

---

**`_render_metrics(records, readiness_map, reminder_map, today)`**

Five `st.metric` tiles across one row:

| Tile | Computation |
|------|-------------|
| Total Tracked | `len(records)` |
| Delayed Stages | sum of stages with status = Delayed across all records |
| Blocked Stages | count of records where readiness_map[id]["pp_sample"] or ["cutting"] starts with "waiting" |
| Completed Today | count of stages whose actual date field == today |
| QC Bookings Due | count of records where `reminder_map[id]` is non-empty |

---

**`_render_dashboard_tab(records, readiness_map, reminder_map, today)`**

```
Filters row: Company multiselect | Factory text | "Show only at-risk" toggle
→ apply filters to records list

2-column grid using st.columns(2):
  For each record (left col then right col, alternating):
    border_color = red (any Delayed) | orange (any Blocked) | green (all Done) | grey
    with st.container(border=True):
      col_hdr, col_factory = st.columns([3, 2])
        col_hdr:     st.markdown(f"**{po_number}** / {style}")
        col_factory: st.caption(factory)
      
      done = count of applicable stages with status Done
      total = count of applicable stages
      st.progress(done / total if total else 0,
                  text=f"{done} / {total} stages done")
      
      # Group breakdown
      st.caption(f"Pre-Prod: {a_done}/8  ·  Samples: {b_done}/{b_total}  ·  "
                 f"Production: {c_done}/6  ·  Post: {d_done}/2")
      
      # Status badge row (abbreviated)
      st.markdown(" ".join(STATUS_EMOJI[r[s+"_status"]] for s in STAGES
                            if r.get(s+"_applicable", 1)))
      
      # QC line
      reminders = reminder_map[record["id"]]
      if reminders:
          st.markdown(f":red[⚠️ {len(reminders)} QC booking(s) due]")
      else:
          st.caption("✅ QC OK")
      
      # Edit shortcut.  We must update BOTH the index tracker (PT_ACTIVE_TAB)
      # AND the radio widget's own session_state key (`pt_tab_radio`).  The
      # `index=` parameter on st.radio is ignored once the widget's key is
      # already in session_state — so without updating `pt_tab_radio` here,
      # the radio would silently ignore PT_ACTIVE_TAB and stay on Dashboard.
      if st.button("✏️ Edit", key=f"dash_edit_{record['id']}"):
          st.session_state[SK.PT_SELECTED_EDIT] = record["id"]
          st.session_state[SK.PT_ACTIVE_TAB]    = 2                  # index 2 = "✏️ Edit Record"
          st.session_state["pt_tab_radio"]      = _TAB_LABELS[2]     # ← required
          st.rerun()
```

---

**`_render_overview_table(records, readiness_map, reminder_map, today)`**

Builds a `pandas.DataFrame` with:
- Columns: PO #, Style, Factory, then one abbreviated col per stage, then QC
- Stage cell values: `STATUS_EMOJI[status]` for applicable stages; `—` for inapplicable optional stages
- PP Sample and Cutting cells: emoji + readiness suffix (`⏳`/`✅`/`⚪`)
- QC cell: `⚠️ N` if N reminders; `✅` if all booked/no deadlines; `—` if nothing set

Rendered with `st.dataframe(..., hide_index=True, use_container_width=True)`.
Abbreviated headers: "Trim Pur.", "Trim Lay.", "Fab Pur.", "Fab LD", "Base Pat.", "Full Pat.",
"Spl Trim", "Spl Fab", "Proto", "Fit", "SzSet", "SMS", "Counter", "PP Spl.",
"Cut", "Sew", "TOP", "Pack", "QA", "FQA", "Boat", "Ship", "QC".

---

**`_render_edit_tab(records, readiness_map, store, username, today)`**

```
if not records: st.info("No records yet. Use ➕ Add New."); return

# ── Record selection ──────────────────────────────────────────────────
# PT_SELECTED_EDIT stores record["id"] (int).  The selectbox option list
# is the list of ids; format_func renders each id as its display label.
_id_to_label = {r["id"]: f"{r['po_number']} — {r['style']}" for r in records}
_ids = list(_id_to_label.keys())
_saved_id = st.session_state.get(SK.PT_SELECTED_EDIT)
_default_idx = _ids.index(_saved_id) if _saved_id in _ids else 0

selected_id = st.selectbox(
    "Select PO / Style",
    options=_ids,
    format_func=lambda rid: _id_to_label[rid],
    index=_default_idx,
    key=SK.PT_SELECTED_EDIT,
)
record = next(r for r in records if r["id"] == selected_id)
reminders = store.compute_inspection_reminders(record, today)

**Critical**: every widget below uses `key=_wkey(selected_id, "...")` so that switching POs in the selectbox forces all widgets to recreate themselves with the new record's defaults. See "Widget key contract" in the Save section below.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧵 Group A — Pre-Production (Parallel)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For each stage in STAGES_GROUP_A:
  Row: st.columns([2.5, 2, 2, 2, 1.5, 2.5])
    Label
    | Status selectbox  — key=_wkey(rid, f"{stage}_status"),
                          index=STATUS_OPTIONS.index(record[f"{stage}_status"] or "Not Started")
    | Planned date_input — key=_wkey(rid, f"{stage}_planned"),
                            value=date.fromisoformat(record[...]) if record[...] else None
    | Actual date_input  — key=_wkey(rid, f"{stage}_actual"),  …same parse pattern
    | Exp.Days number_input — key=_wkey(rid, f"{stage}_expected_days"),
                              value=record[...] or 0
    | Notes text_input  — key=_wkey(rid, f"{stage}_notes"), value=record[...] or ""
  st.multiselect("Required for:",
    options=[STAGE_LABELS[t] for t in PREREQ_VALID[stage]],
    default=[STAGE_LABELS[t] for t in PREREQ_VALID[stage]
             if record.get(dep_col(stage, t))],
    key=_wkey(rid, f"dep_{stage}"))
  # On save: reverse-map display names to keys using inverted STAGE_LABELS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧪 Group B — Samples
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Substitute materials toggle (record-scoped key)
st.toggle("🔄 Use Substitute Materials for Samples",
          value=bool(record.get("use_substitute_materials", 1)),
          key=_wkey(rid, "use_substitute"))
st.info/st.warning contextual notice (see FR-03b)

with st.expander("Optional Samples",
                 expanded=any(record[s+"_applicable"] for s in STAGES_GROUP_B_OPTIONAL)):
  For each stage in STAGES_GROUP_B_OPTIONAL:
    st.toggle(f"Include {STAGE_LABELS[stage]}",
              value=bool(record.get(f"{stage}_applicable", 0)),
              key=_wkey(rid, f"appl_{stage}"))
    if applicable:
      6-column row (same layout as Group A — all widget keys use _wkey(rid, ...))
      st.multiselect("Required for PP Sample:", ["PP Sample"],
                     default=["PP Sample"] if record.get(dep_col(stage,"pp_sample")) else [],
                     key=_wkey(rid, f"dep_{stage}_pp"))

st.divider()
st.subheader("PP Sample  (Compulsory)")
# Show readiness badge: ✅ st.success / ⏳ st.warning / ⚪ st.info
6-column row for pp_sample fields

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏭 Group C — Production (Sequential)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.subheader("Cutting")
# Show readiness badge
6-column row for cutting

For sewing, top_sample, packing, qa, final_qa: 6-column rows (no readiness badge)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 Group D — Post-Production
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For boat_sample, shipping: 6-column rows

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 QC Inspections
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For each key in QC_INSPECTIONS:
  if key == "insp_refinal" and record["insp_final_result"] != "Fail":
    st.caption("🔁 Re-Final Inspection — appears when Final result is 'Fail'")
    continue
  # When the widget DOES render, every input uses _wkey(rid, f"{key}_{field}").
  # When suppressed (Re-Final hidden), the save helper falls back to record[...]
  # so existing data is preserved.

  st.subheader(QC_INSPECTION_LABELS[key])
  # Show overdue/warning banner if reminder due
  Line 1:
    Booking Deadline date_input — key=_wkey(rid, f"{key}_booking_deadline")
    Reminder Days number_input   — key=_wkey(rid, f"{key}_reminder_days"), value=record[...] or 7
    Booked checkbox              — key=_wkey(rid, f"{key}_booked"), value=bool(record[...])
    Booking Date date_input      — key=_wkey(rid, f"{key}_booking_date")
  Line 2:
    Inspection Date date_input   — key=_wkey(rid, f"{key}_inspection_date")
    Result selectbox             — key=_wkey(rid, f"{key}_result"),
                                    index=QC_RESULT_OPTIONS.index(record[...] or "Pending")
    Notes text_input             — key=_wkey(rid, f"{key}_notes")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.text_area("Overall notes", value=record.get("overall_notes",""),
             key=_wkey(rid, "overall_notes"))
col_save, col_del = st.columns(2)
  Save button (primary) → _build_payload_and_save(record, store, username) + st.rerun()
  Delete button → confirmation prompt → store.delete([record["id"]]) + st.rerun()
```

**Widget key contract** — every widget in the Edit form uses a record-scoped key built via:

```python
def _wkey(rid: int, base: str) -> str:
    """Build a widget key scoped to a specific record id.

    Scoping prevents the Edit form from showing stale values when the user
    selects a different PO/style — switching records changes `rid`, which
    changes every widget key, which causes Streamlit to recreate the widgets
    with the new record's `value=` / `index=` defaults.
    """
    return f"pt_edit_{rid}_{base}"
```

All Edit-tab widgets (status, planned, actual, expected_days, notes, applicable, dep multiselects, QC inspection fields, overall_notes text_area, use_substitute toggle) use `_wkey(selected_id, ...)` for their `key=` argument.

---

**Save payload construction** — `_build_payload_and_save(record, store, username)`:

```python
from datetime import date

def _to_iso_or_empty(val) -> str:
    """Normalize any date-ish widget value to an ISO string ('' if blank)."""
    if isinstance(val, date):
        return val.isoformat()
    return val or ""

def _build_payload_and_save(record, store, username):
    rid = record["id"]   # may be None for Add New (synthetic record)
    # Preserve-from-record helper: when a widget didn't render (hidden by
    # `applicable=0` or Re-Final being suppressed), st.session_state.get()
    # returns None and we MUST fall back to the existing DB value — otherwise
    # we'd overwrite saved data with None on every save.
    def _read(widget_key: str, record_key: str | None = None):
        if rid is not None:
            v = st.session_state.get(_wkey(rid, widget_key), None)
        else:
            v = st.session_state.get(_wkey("new", widget_key), None)
        if v is None and record_key is not None:
            return record.get(record_key)
        return v

    # ── Stage fields ──────────────────────────────────────────────────────
    DATE_FIELDS = {"planned", "actual"}
    stage_fields = {}
    for stage in STAGES:
        for field in STAGE_FIELDS:             # status/planned/actual/notes/expected_days
            db_col = f"{stage}_{field}"
            val = _read(db_col, db_col)
            if field in DATE_FIELDS:
                val = _to_iso_or_empty(val)
            stage_fields[db_col] = val
        if stage in OPTIONAL_SAMPLE_STAGES:
            # `appl_{stage}` always renders (toggle is visible even when off),
            # so no preserve-from-record fallback needed here.
            stage_fields[f"{stage}_applicable"] = int(
                bool(st.session_state.get(_wkey(rid or "new", f"appl_{stage}"), False))
            )

    # ── Dependency matrix ─────────────────────────────────────────────────
    dep_fields = {}

    # Group A → PP Sample / Cutting (handles full_sized_pattern→cutting too —
    # PREREQ_VALID["full_sized_pattern"] = ["cutting"], so no separate write needed).
    for stage in STAGES_GROUP_A:
        labels = st.session_state.get(_wkey(rid or "new", f"dep_{stage}"), None)
        if labels is None:
            # Widget didn't render — preserve existing dep values from record.
            for target in PREREQ_VALID[stage]:
                dep_fields[dep_col(stage, target)] = record.get(dep_col(stage, target), 0)
        else:
            for target in PREREQ_VALID[stage]:
                dep_fields[dep_col(stage, target)] = int(STAGE_LABELS[target] in labels)

    # Optional samples → PP Sample (only when toggle is on; otherwise preserve)
    for stage in OPTIONAL_SAMPLE_STAGES:
        applicable = stage_fields[f"{stage}_applicable"]
        if applicable:
            sel = st.session_state.get(_wkey(rid or "new", f"dep_{stage}_pp"), [])
            dep_fields[dep_col(stage, "pp_sample")] = int(bool(sel))
        else:
            dep_fields[dep_col(stage, "pp_sample")] = record.get(dep_col(stage, "pp_sample"), 0)

    # PP Sample → Cutting: SYSTEM-ENFORCED, ALWAYS ON (FR-03).  Not a UI widget.
    dep_fields[dep_col("pp_sample", "cutting")] = 1

    # ── QC fields ─────────────────────────────────────────────────────────
    QC_DATE_FIELDS = {"booking_deadline", "booking_date", "inspection_date"}
    qc_fields = {}
    for key in QC_INSPECTIONS:
        # Re-Final widgets only render when insp_final_result == "Fail".
        # When they don't render, _read() falls back to record[...] preserving data.
        for field in QC_FIELDS:
            db_col = f"{key}_{field}"
            val = _read(db_col, db_col)
            if field == "booked":
                val = int(bool(val))
            elif field in QC_DATE_FIELDS:
                val = _to_iso_or_empty(val)
            qc_fields[db_col] = val

    store.upsert(
        po_number              = record["po_number"],
        style                  = record["style"],
        factory                = record["factory"],
        company                = record["company"],
        updated_by             = username,
        overall_notes          = _read("overall_notes", "overall_notes") or "",
        use_substitute_materials = int(bool(
            st.session_state.get(_wkey(rid or "new", "use_substitute"), True)
        )),
        stage_fields           = stage_fields,
        dep_fields             = dep_fields,
        qc_fields              = qc_fields,
    )
```

> **Add New** uses the same helper with `rid = None` (widget keys use `_wkey("new", ...)`). The Add New picker builds a synthetic `record` dict before calling this — see `_render_add_tab` below for the exact construction.

---

**`_render_add_tab(store, po_store, username)`**

```python
def _render_add_tab(store, po_store, username):
    untracked = store.list_untracked_pos(po_store)
    if not untracked:
        st.info("All POs are already being tracked.")
        return

    # ── Picker: same id/format_func pattern as Edit/Plan, but the "id" here
    # is the position in the untracked list (the row has no DB id yet).
    _idx_to_label = {
        i: f"{u['po_number']} — {u['style'] or '(no style)'} — {u['factory'] or '(no factory)'}"
        for i, u in enumerate(untracked)
    }
    picked_idx = st.selectbox(
        "Select PO / Style to start tracking",
        options=list(_idx_to_label.keys()),
        format_func=lambda i: _idx_to_label[i],
    )
    picked = untracked[picked_idx]

    # ── Build the synthetic `record` dict that the form widgets and the save
    # helper expect.  It must contain every column the form reads from,
    # populated with system defaults.
    record = {
        "id":                      None,             # signals "Add New" mode
        "po_number":               picked["po_number"],
        "style":                   picked["style"] or "",
        "factory":                 picked["factory"] or "",
        "company":                 picked["company"] or "",
        "overall_notes":           "",
        "use_substitute_materials": 1,
    }
    # All stage fields → defaults
    for stage in STAGES:
        record[f"{stage}_status"]        = "Not Started"
        record[f"{stage}_planned"]       = ""
        record[f"{stage}_actual"]        = ""
        record[f"{stage}_notes"]         = ""
        record[f"{stage}_expected_days"] = None
    # Optional sample applicability → OFF by default
    for stage in OPTIONAL_SAMPLE_STAGES:
        record[f"{stage}_applicable"] = 0
    # Dependency matrix → DEFAULT_DEP_ON columns get 1, all others 0
    for source, targets in PREREQ_VALID.items():
        for target in targets:
            col = dep_col(source, target)
            record[col] = 1 if col in DEFAULT_DEP_ON else 0
    record[dep_col("pp_sample", "cutting")] = 1   # system-enforced (FR-03)
    # QC fields → schema defaults
    for key in QC_INSPECTIONS:
        record[f"{key}_booking_deadline"] = ""
        record[f"{key}_reminder_days"]    = 7
        record[f"{key}_booked"]           = 0
        record[f"{key}_booking_date"]     = ""
        record[f"{key}_inspection_date"]  = ""
        record[f"{key}_result"]           = "Pending"
        record[f"{key}_notes"]            = ""

    # Render the same Edit-tab body (helper extracted), passing this synthetic record.
    _render_record_form(record, store=None, username=username, today=date.today(), add_mode=True)

    if st.button("➕ Start Tracking", type="primary"):
        _build_payload_and_save(record, store, username)
        st.rerun()
```

> `_render_record_form()` is the shared form body extracted from `_render_edit_tab` (everything between the selectbox and the Save/Delete buttons).  In Add mode the Delete button is suppressed and the Save button label becomes "Start Tracking".

---

**`_render_plan_tab(records, store)`**

```
col_sel, col_date = st.columns([3, 2])
  # Same id-based selectbox pattern as Edit tab; PT_SELECTED_PLAN stores record id.
  _id_to_label = {r["id"]: f"{r['po_number']} — {r['style']}" for r in records}
  _ids = list(_id_to_label.keys())
  _saved_id = st.session_state.get(SK.PT_SELECTED_PLAN)
  _default_idx = _ids.index(_saved_id) if _saved_id in _ids else 0
  selected_plan_id = st.selectbox(
      "Select PO / Style",
      options=_ids, format_func=lambda rid: _id_to_label[rid],
      index=_default_idx, key=SK.PT_SELECTED_PLAN,
  )
  record = next(r for r in records if r["id"] == selected_plan_id)
  date_input("Start Date", value=date.today())

st.markdown("**Adjust expected days (what-if — not saved):**")

# Each number_input uses a Plan-scoped key.  After Calculate is clicked,
# we assemble the override dict into PT_PLAN_OVERRIDE so it survives reruns
# and can be re-read if the user changes the Start Date without re-typing.
def _plan_wkey(rid: int, stage: str) -> str:
    return f"pt_plan_{rid}_{stage}"

with st.expander("🧵 Group A — Pre-Production", expanded=True):
  for stage in STAGES_GROUP_A: number_input(key=_plan_wkey(selected_plan_id, stage), …)
with st.expander("🧪 Samples — applicable only"):
  for stage in STAGES_GROUP_B:
    if stage in OPTIONAL_SAMPLE_STAGES and not record[f"{stage}_applicable"]:
      continue
    number_input(key=_plan_wkey(selected_plan_id, stage), …)
with st.expander("🏭 Group C + D — Production & Post-Production"):
  for stage in STAGES_GROUP_C + STAGES_GROUP_D:
    number_input(key=_plan_wkey(selected_plan_id, stage), …)

if st.button("🔢 Calculate Schedule", type="primary"):
  override_days = {
      stage: st.session_state.get(_plan_wkey(selected_plan_id, stage), 0) or 0
      for stage in STAGES
  }
  st.session_state[SK.PT_PLAN_OVERRIDE] = override_days   # persist across reruns

  schedule = store.compute_schedule(record, start_date, override_days)
  shipping_end = schedule["shipping"]["end"]
  st.success(f"📦 Estimated Shipping: {shipping_end}  ({(shipping_end - start_date).days} days)")
  if any(v["missing_days"] for v in schedule.values()):
      n = sum(1 for v in schedule.values() if v["missing_days"] and not v["skipped"])
      st.warning(f"⚠️ {n} stage(s) have no expected days set — treated as 0.")

  # Build DataFrame for schedule table
  # Critical path rows: yellow background via Styler.apply()
  # Skipped rows: grey text, "—" for dates
  st.dataframe(styled_df, hide_index=True, use_container_width=True)
  st.caption("What-if only — changes here do not affect saved tracking data.")
```

---

### Step 2.2 — Wire Tab into App

**File**: `app.py`

1. **Find `APP_VERSION`** near the top of the file. Bump minor version (new feature module).

2. **Tab labels** — insert `"🏭 Tracking"` at index 6:
   ```python
   tab_labels = ["📋 GIII", "🛍 Sky East", "🧵 Fabric DB", "📐 Fabric Mapping",
                 "🎨 Colors", "📊 Summary", "🏭 Tracking", "🔖 Releases"]
   ```

3. **Handler function**:
   ```python
   def _show_production_tracking_tab() -> None:
       from ui.production_tracking_view import show_production_tracking_tab
       show_production_tracking_tab(
           user_cos=get_user_companies(st.session_state.username),
           username=st.session_state.username,
       )
   ```

4. **Tab blocks** — shift Releases and Admin by one:
   ```python
   with tabs[6]: _show_production_tracking_tab()
   with tabs[7]: _show_changelog_tab()      # was [6]
   if admin_mode:
       with tabs[8]: _show_admin_panel()    # was [7]
   ```

---

## Phase 3 — Version & Documentation

### Step 3.1 — Version Bump

Locate `APP_VERSION` in `app.py` and increment the minor version number (this is a new feature module).

### Step 3.2 — Write Documentation

- ✅ `docs/requirements_production_tracking.md` — this file's companion
- ✅ `docs/development_plan_production_tracking.md` — this file

---

## Delivery Checklist

- [ ] `po_extractor/store/_production_tracking_schema.py` — 173-col schema, all constants
- [ ] `po_extractor/store/production_tracking_store.py` — 5 CRUD + 3 compute methods
- [ ] `po_extractor/store/__init__.py` — import + factory + `__all__`
- [ ] `ui/stores.py` — import + wrapper function
- [ ] `ui/session_keys.py` — 5 new `PT_*` keys
- [ ] `ui/production_tracking_view.py` — all sub-tabs (Dashboard, Overview, Edit, Add New, Plan)
- [ ] `app.py` — tab inserted at index 6, downstream indices shifted, version bumped
- [ ] `docs/requirements_production_tracking.md` — written ✅
- [ ] `docs/development_plan_production_tracking.md` — written ✅

---

## Verification Steps

### Dashboard
1. `streamlit run app.py` — `🏭 Tracking` tab opens to `📊 Dashboard` by default.
2. Dashboard shows one card per tracked PO; progress bar reflects Done/total applicable.
3. Record with a Delayed stage: card border red. Blocked (Waiting): orange. All Done: green.
4. QC booking due today: card shows `⚠️ 1 booking(s) due`; QC Bookings Due metric = 1.
5. `✏️ Edit` button on a card → navigation radio switches to "✏️ Edit Record" panel and selectbox shows that PO pre-selected.
6. "Show only at-risk" toggle → only Delayed/Blocked cards shown.

### Stage Tracking
7. Add New: untracked POs appear; style/factory auto-fill; optional samples off by default.
8. Defaults: Base Size Pattern→PP Sample ON, Base Size Pattern→Cutting ON, Full Sized Pattern→Cutting ON, PP Sample→Cutting ON.
9. All stages Not Started (substitute=ON is the default) →
   - PP Sample: `⏳ Waiting on: Sample Trim Purchase, Sample Fabric Purchase, Base Size Pattern`
     (Sample Trim/Fabric Purchase come from the FR-03b auto-rule; Base Size Pattern from the default dep matrix.)
   - Cutting: `⏳ Waiting on: Base Size Pattern, Full Sized Pattern, PP Sample`
     (Cutting is not a sample stage, so the auto substitute-material rule does not apply to it directly.)
10. Mark Base Size Pattern Done → PP Sample: `✅ Ready`.
11. Mark PP Sample + Full Sized Pattern Done → Cutting: `✅ Ready`.
12. Enable Fit Sample → tick "Required for PP Sample" → PP Sample reverts to `⏳ Waiting on: Fit Sample`. Mark Fit Sample Done → `✅ Ready`.
13. Disable Fit Sample toggle → excluded from readiness; PP Sample ignores it.
14. Set a stage Delayed → `🔴` badge in overview; Delayed metric increments.
15. All POs tracked → Add New shows `st.info("All POs are already being tracked.")`.

### Substitute Materials Flag
16. New record (substitute=ON): PP Sample → `⏳ Waiting on: Sample Trim Purchase, Sample Fabric Purchase, Base Size Pattern`.
17. Mark those three Done → `✅ Ready`. Bulk Fabric Purchase still Not Started — does not block.
18. Toggle substitute=OFF → PP Sample → `⏳ Waiting on: Trim Purchase, Trim Layout, Fabric Purchase, Fabric Color (LD)`.
19. Mark all four bulk stages Done → `✅ Ready`.
20. Toggle back to ON → sample purchase prereqs re-apply; bulk stages no longer block samples.

### Planning Module

Common setup for all planning scenarios: default dep matrix (Base Size Pattern→PP Sample ON, Base Size Pattern→Cutting ON, Full Sized Pattern→Cutting ON, PP Sample→Cutting ON). Start date = 2025-01-01 (day 0).

**Scenario A — substitute=ON, base_size_pattern is bottleneck (sample purchases finish first)**

Set expected days: sample_trim_purchase=4, sample_fabric_purchase=4, base_size_pattern=5, full_sized_pattern=3, pp_sample=7, cutting=5, sewing=14, top_sample=2, packing=3, qa=2, final_qa=1, boat_sample=1, shipping=1.

21. Calculate. Verify:
    - Group A: all start day 0 (parallel). sample_trim_purchase ends day 4, sample_fabric_purchase ends day 4, base_size_pattern ends day 5, full_sized_pattern ends day 3.
    - PP Sample: prereqs = auto(sample_trim=4, sample_fabric=4) + matrix(base_size_pattern=5). Start = max(4,4,5) = day 5. End = day 12.
    - Cutting: prereqs = matrix(pp_sample=12, full_sized_pattern=3). Start = max(12,3) = day 12. End = day 17.
    - Sewing: 17→31. TOP: 31→33. Packing: 33→36. QA: 36→38. Final QA: 38→39. Boat: 39→40. Shipping: 40→41.
    - Critical path: **Base Size Pattern(0→5) → PP Sample(5→12) → Cutting(12→17) → Sewing → … → Shipping(40→41)**.  
      sample_trim_purchase and sample_fabric_purchase finish on day 4 — they are NOT on the critical path because base_size_pattern ends later (day 5).

**Scenario B — substitute=ON, sample purchases are the bottleneck**

Change: sample_trim_purchase=7, sample_fabric_purchase=6 (all others unchanged from Scenario A).

22. Calculate. Verify:
    - sample_trim_purchase ends day 7, sample_fabric_purchase ends day 6, base_size_pattern ends day 5.
    - PP Sample: start = max(7, 6, 5) = day 7. End = day 14.
    - Cutting: start = max(14, 3) = day 14. End = day 19.
    - Sewing: 19→33. TOP: 33→35. Packing: 35→38. QA: 38→40. Final QA: 40→41. Boat: 41→42. Shipping: 42→43.
    - Critical path: **Sample Trim Purchase(0→7) → PP Sample(7→14) → Cutting → … → Shipping(42→43)**.  
      sample_trim_purchase is now on the critical path; base_size_pattern is not.

**Scenario C — substitute=OFF, bulk materials gate all samples**

Revert sample purchases to 4 days each. Toggle substitute=OFF. Enable no extra deps. Set: trim_purchase=7, trim_layout=3, fabric_purchase=14, fabric_color_ld=10 (all start day 0).

23. Calculate. Verify:
    - PP Sample auto-prereqs = BULK_MATERIAL_PREREQS: trim_purchase ends 7, trim_layout ends 3, fabric_purchase ends 14, fabric_color_ld ends 10. Max = 14.
    - PP Sample: start = max(14, 5) = day 14. End = day 21.
    - Cutting: start = max(21, 3) = day 21. End = day 26.
    - Sewing: 26→40. TOP: 40→42. Packing: 42→45. QA: 45→47. Final QA: 47→48. Boat: 48→49. Shipping: 49→50.
    - Critical path: **Fabric Purchase(0→14) → PP Sample(14→21) → Cutting → … → Shipping(49→50)**.
    - Difference vs Scenario A: substitute=OFF delays PP Sample by 9 days (day 14 vs day 5), pushing shipping from day 41 to day 50.

24. Plan tab overrides do NOT persist to Edit tab.

### QC Inspections
25. New record: QC section shows PPI, Inline, Final; Re-Final shows caption placeholder.
26. Set PPI booking_deadline = today+3, reminder_days=7 → PPI shows `⚠️ Book by {date}` (today ≥ deadline−7). QC Bookings Due = 1.
27. Tick PPI Booked → reminder clears. QC Bookings Due = 0.
28. Set Final booking_deadline = yesterday → Final shows `⚠️ Booking OVERDUE`. Overview QC = `⚠️ 1`.
29. Set Final result = Fail → Re-Final section becomes visible with all 7 fields.
30. Set Final result = Pass → Re-Final collapses back to placeholder caption.
31. Record with no booking deadlines → overview QC column = `—`.
