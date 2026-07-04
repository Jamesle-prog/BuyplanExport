"""SQLite schema and exported constants for the production_tracking table.

Single source of truth for the 22-stage manufacturing pipeline tracker.
Imported by ``production_tracking_store.py`` and the UI view module.

Schema overview
---------------
``production_tracking`` is a wide table holding one row per ``(po_number, style)``
pair.  Every stage, every dependency, and every QC inspection is a column on
the same row — this keeps the readiness, schedule, and reminder computations
as pure-Python operations over a single dict (no extra DB queries).

Total: **173 columns**
  - 8 base columns
  - 1 global flag (``use_substitute_materials``)
  - 40 Group A stage fields (8 stages × 5 fields)
  - 30 Group B optional sample fields (5 stages × 6 fields)
  - 5 PP Sample fields
  - 30 Group C production fields (6 stages × 5 fields)
  - 10 Group D post-production fields (2 stages × 5 fields)
  - 21 dependency matrix booleans
  - 28 QC inspection fields (4 types × 7 fields)

Migration
---------
``_ensure_schema()`` in the store uses ``PRAGMA table_info`` plus
``ALTER TABLE ADD COLUMN`` so existing stub databases gain the new columns
without losing data.  Dead columns from the previous stub
(``ex_factory_date``, ``etd``, ``eta``, ``carrier``, ``vessel``,
``bl_number``, ``status``, ``notes``) remain in place — SQLite cannot
safely drop columns in a migration, so we just leave them and ignore them.
"""
from __future__ import annotations

# ── Stage groupings ─────────────────────────────────────────────────────────

STAGES_GROUP_A: list[str] = [
    "trim_layout",            # must be confirmed before Trim Purchase
    "trim_purchase",
    "fabric_color_ld",        # must be confirmed before Fabric Purchase
    "fabric_purchase",
    "base_size_pattern",
    "full_sized_pattern",
    "sample_trim_purchase",
    "sample_fabric_purchase",
]

STAGES_GROUP_B_OPTIONAL: list[str] = [
    "proto_sample",
    "fit_sample",
    "size_set_sample",
    "salesman_sample",
    "counter_sample",
]

# PP Sample is part of Group B but always applicable (not optional).
STAGES_GROUP_B: list[str] = STAGES_GROUP_B_OPTIONAL + ["pp_sample"]

STAGES_GROUP_C: list[str] = [
    "cutting",
    "sewing",
    "top_sample",
    "packing",
    "qa",
    "final_qa",
]

STAGES_GROUP_D: list[str] = ["boat_sample", "shipping"]

# Full ordered list of all 22 stages.
STAGES: list[str] = (
    STAGES_GROUP_A + STAGES_GROUP_B + STAGES_GROUP_C + STAGES_GROUP_D
)

# Convenience: which stages are "sample stages" for the substitute-material rule.
ALL_SAMPLE_STAGES: list[str] = STAGES_GROUP_B   # proto … pp_sample

OPTIONAL_SAMPLE_STAGES: list[str] = STAGES_GROUP_B_OPTIONAL


# ── Display labels (single source of truth for UI rendering) ────────────────

STAGE_LABELS: dict[str, str] = {
    # Group A
    "trim_purchase":           "Trim Purchase",
    "trim_layout":             "Trim Layout",
    "fabric_purchase":         "Fabric Purchase",
    "fabric_color_ld":         "Fabric Color (LD)",
    "base_size_pattern":       "Base Size Pattern",
    "full_sized_pattern":      "Full Sized Pattern",
    "sample_trim_purchase":    "Sample Trim Purchase",
    "sample_fabric_purchase":  "Sample Fabric Purchase",
    # Group B
    "proto_sample":            "Proto Sample",
    "fit_sample":              "Fit Sample",
    "size_set_sample":         "Size Set Sample",
    "salesman_sample":         "Salesman Sample (SMS)",
    "counter_sample":          "Counter Sample",
    "pp_sample":               "PP Sample",
    # Group C
    "cutting":                 "Cutting",
    "sewing":                  "Sewing",
    "top_sample":              "TOP Sample",
    "packing":                 "Packing",
    "qa":                      "QA",
    "final_qa":                "Final QA",
    # Group D
    "boat_sample":             "Boat Sample",
    "shipping":                "Shipping",
}


# ── Status options and badges ───────────────────────────────────────────────

STATUS_OPTIONS: list[str] = ["Not Started", "In Progress", "Done", "Delayed"]

STATUS_EMOJI: dict[str, str] = {
    "Not Started": "⬜",
    "In Progress": "🔵",
    "Done":        "✅",
    "Delayed":     "🔴",
}


# ── Dependency matrix definitions ───────────────────────────────────────────

# Which (source → target) pairs are valid in the configurable dep matrix.
# Sample-material gating by ``use_substitute_materials`` is handled separately
# in the compute helpers (see SUBSTITUTE_SAMPLE_PREREQS / BULK_MATERIAL_PREREQS).
PREREQ_VALID: dict[str, list[str]] = {
    "trim_purchase":          ["pp_sample", "cutting"],
    "trim_layout":            ["trim_purchase", "pp_sample", "cutting"],   # LD gate
    "fabric_purchase":        ["pp_sample", "cutting"],
    "fabric_color_ld":        ["fabric_purchase", "pp_sample", "cutting"], # LD gate
    "sample_trim_purchase":   ["pp_sample", "cutting"],
    "sample_fabric_purchase": ["pp_sample", "cutting"],
    "base_size_pattern":      ["pp_sample", "cutting"],
    "full_sized_pattern":     ["cutting"],
    "proto_sample":           ["pp_sample"],
    "fit_sample":             ["pp_sample"],
    "size_set_sample":        ["pp_sample"],
    "salesman_sample":        ["pp_sample"],
    "counter_sample":         ["pp_sample"],
    # System-enforced ON, never user-configurable (see FR-03).  Listed here so
    # the column gets included in schema generation, but the UI never exposes
    # a multiselect for it.
    "pp_sample":              ["cutting"],
}

# Stages that have computed readiness (displayed as badges in the Edit form).
# trim_purchase and fabric_purchase are gated by their respective LD/layout
# confirmation stages; pp_sample and cutting are gated by the broader matrix.
PREREQ_TARGETS: list[str] = ["trim_purchase", "fabric_purchase", "pp_sample", "cutting"]

# Substitute-material automatic gating (FR-03b).
# When use_substitute_materials=1, these stages must be Done before any sample
# stage (proto, fit, size_set, salesman, counter, pp_sample) can start.
SUBSTITUTE_SAMPLE_PREREQS: list[str] = [
    "sample_trim_purchase",
    "sample_fabric_purchase",
]

# When use_substitute_materials=0, these bulk-material stages gate samples instead.
BULK_MATERIAL_PREREQS: list[str] = [
    "trim_purchase",
    "trim_layout",
    "fabric_purchase",
    "fabric_color_ld",
]

# Dep matrix flags that default to 1 (ON) on every new record.
DEFAULT_DEP_ON: set[str] = {
    # New: confirm before bulk procurement
    "trim_layout_req_trim_purchase",
    "fabric_color_ld_req_fabric_purchase",
    # Pattern approvals gate samples and cutting
    "base_size_pattern_req_pp_sample",
    "base_size_pattern_req_cutting",
    "full_sized_pattern_req_cutting",
    # System-enforced: PP Sample must precede Cutting
    "pp_sample_req_cutting",
}


def dep_col(source: str, target: str) -> str:
    """Return the dep matrix column name for a (source → target) pair."""
    return f"{source}_req_{target}"


# ── Stage field layout ──────────────────────────────────────────────────────

# Common fields every stage carries.
STAGE_FIELDS: list[str] = ["status", "planned", "actual", "notes", "expected_days"]

# Optional sample stages also carry an applicability toggle.
OPTIONAL_STAGE_EXTRA_FIELDS: list[str] = ["applicable"]


# ── QC inspection definitions ───────────────────────────────────────────────

QC_INSPECTIONS: list[str] = [
    "insp_ppi",
    "insp_inline",
    "insp_final",
    "insp_refinal",
]

QC_INSPECTION_LABELS: dict[str, str] = {
    "insp_ppi":     "Pre-Production Inspection (PPI)",
    "insp_inline":  "Inline Inspection",
    "insp_final":   "Final Inspection",
    "insp_refinal": "Re-Final Inspection",
}

QC_RESULT_OPTIONS: list[str] = [
    "Pending",
    "Pass",
    "Conditional Pass",
    "Fail",
    "N/A",
]

QC_FIELDS: list[str] = [
    "booking_deadline",
    "reminder_days",
    "booked",
    "booking_date",
    "inspection_date",
    "result",
    "notes",
]


# ── Schema column generation ────────────────────────────────────────────────
# We build the column list programmatically so the schema can never drift from
# the constants above.  ``_ensure_schema()`` in the store reads this list to
# perform ``ALTER TABLE ADD COLUMN`` for any column that's missing.

def _stage_columns(stage: str, *, optional: bool = False) -> list[tuple[str, str]]:
    """Return [(col_name, col_definition), ...] for one stage."""
    cols: list[tuple[str, str]] = [
        (f"{stage}_status",        "TEXT    DEFAULT 'Not Started'"),
        (f"{stage}_planned",       "TEXT    DEFAULT ''"),
        (f"{stage}_actual",        "TEXT    DEFAULT ''"),
        (f"{stage}_notes",         "TEXT    DEFAULT ''"),
        (f"{stage}_expected_days", "INTEGER DEFAULT NULL"),
    ]
    if optional:
        cols.append((f"{stage}_applicable", "INTEGER DEFAULT 0"))
    return cols


def _qc_columns(key: str) -> list[tuple[str, str]]:
    """Return [(col_name, col_definition), ...] for one QC inspection type."""
    return [
        (f"{key}_booking_deadline", "TEXT    DEFAULT ''"),
        (f"{key}_reminder_days",    "INTEGER DEFAULT 7"),
        (f"{key}_booked",           "INTEGER DEFAULT 0"),
        (f"{key}_booking_date",     "TEXT    DEFAULT ''"),
        (f"{key}_inspection_date",  "TEXT    DEFAULT ''"),
        (f"{key}_result",           "TEXT    DEFAULT 'Pending'"),
        (f"{key}_notes",            "TEXT    DEFAULT ''"),
    ]


def _build_column_spec() -> list[tuple[str, str]]:
    """Return the complete ordered column list for production_tracking.

    Each entry is ``(column_name, column_definition_sql)``.  The 8 base
    columns are NOT included here — they live in the CREATE TABLE statement
    because they participate in PRIMARY KEY / UNIQUE / NOT NULL constraints
    that ``ALTER TABLE ADD COLUMN`` cannot express.
    """
    cols: list[tuple[str, str]] = []

    # 1. Global flag
    cols.append(("use_substitute_materials", "INTEGER DEFAULT 1"))

    # 2. Group A stage fields (8 × 5 = 40 cols)
    for stage in STAGES_GROUP_A:
        cols.extend(_stage_columns(stage))

    # 3. Group B optional sample fields (5 × 6 = 30 cols)
    for stage in STAGES_GROUP_B_OPTIONAL:
        cols.extend(_stage_columns(stage, optional=True))

    # 4. PP Sample (1 × 5 = 5 cols) — always applicable, no toggle
    cols.extend(_stage_columns("pp_sample"))

    # 5. Group C production fields (6 × 5 = 30 cols)
    for stage in STAGES_GROUP_C:
        cols.extend(_stage_columns(stage))

    # 6. Group D post-production fields (2 × 5 = 10 cols)
    for stage in STAGES_GROUP_D:
        cols.extend(_stage_columns(stage))

    # 7. Dependency matrix (23 cols) — sorted into a stable order.
    for source, targets in PREREQ_VALID.items():
        for target in targets:
            col = dep_col(source, target)
            default = 1 if col in DEFAULT_DEP_ON else 0
            cols.append((col, f"INTEGER DEFAULT {default}"))

    # 8. QC inspections (4 × 7 = 28 cols)
    for key in QC_INSPECTIONS:
        cols.extend(_qc_columns(key))

    return cols


# Frozen column spec — computed once at import time, used by the store for
# both initial creation and idempotent migration.
COLUMN_SPEC: list[tuple[str, str]] = _build_column_spec()


# Base table SQL (the 8 base columns + UNIQUE constraint + index).
# Non-base columns are added via ALTER TABLE ADD COLUMN in the store's
# _ensure_schema() so the same code path handles both fresh creation and
# migration of the old 6-column stub.
_BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS production_tracking (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number     TEXT NOT NULL,
    style         TEXT NOT NULL DEFAULT '',
    factory       TEXT DEFAULT '',
    company       TEXT DEFAULT '',
    overall_notes TEXT DEFAULT '',
    updated_at    TEXT,
    updated_by    TEXT,
    UNIQUE(po_number, style)
);
CREATE INDEX IF NOT EXISTS idx_pt_company ON production_tracking(company);
"""


def base_schema_sql() -> str:
    """Return the CREATE TABLE + CREATE INDEX SQL for the base columns."""
    return _BASE_SCHEMA


__all__ = [
    # Stage groups
    "STAGES_GROUP_A", "STAGES_GROUP_B_OPTIONAL", "STAGES_GROUP_B",
    "STAGES_GROUP_C", "STAGES_GROUP_D", "STAGES",
    "ALL_SAMPLE_STAGES", "OPTIONAL_SAMPLE_STAGES",
    # Labels
    "STAGE_LABELS",
    # Status
    "STATUS_OPTIONS", "STATUS_EMOJI",
    # Dependency matrix
    "PREREQ_VALID", "PREREQ_TARGETS",
    "SUBSTITUTE_SAMPLE_PREREQS", "BULK_MATERIAL_PREREQS",
    "DEFAULT_DEP_ON", "dep_col",
    # Field layout
    "STAGE_FIELDS", "OPTIONAL_STAGE_EXTRA_FIELDS",
    # QC
    "QC_INSPECTIONS", "QC_INSPECTION_LABELS",
    "QC_RESULT_OPTIONS", "QC_FIELDS",
    # Schema helpers
    "COLUMN_SPEC", "base_schema_sql",
]
