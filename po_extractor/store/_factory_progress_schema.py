"""Schema and constants for factory progress reports (工厂进度回报).

A dated report log: each row is one factory report of units completed for a
stage of one (po_number, style) — e.g. "2026-07-15: cut 300 units". Totals
are always derived by summing rows, never stored, so the full history of
when the factory reported what is preserved (dispute evidence + pace
analysis). Complements ``production_tracking`` (status/planned/actual per
stage, no quantities) — this table holds the QUANTITIES.
"""
from __future__ import annotations

# Stages a factory reports quantities for. Deliberately a small fixed set —
# these are the countable production outputs the merchandiser chases, not
# the full 22-stage tracking pipeline.
REPORT_STAGES: list[str] = ["cutting", "sewing", "packing"]

REPORT_STAGE_LABELS: dict[str, str] = {
    "cutting": "裁剪 Cutting",
    "sewing":  "车缝 Sewing",
    "packing": "包装 Packing",
}

# The buy plan Index tab's tracking columns, in display order — each maps to
# a production_tracking stage whose *_planned (expected completion),
# *_notes (status note) and *_actual (marked complete) columns drive both
# the in-house Milestones editor and the factory Excel round-trip. Mirrors
# _INDEX_MILESTONE_MAP in sky_east_buyplan_export.py (the buy plan reads
# the same stages), so populated values flow into the Index sheet.
MILESTONE_STAGES: list[tuple[str, str]] = [
    ("fabric_purchase",    "面料到厂 Fabric arrival"),
    ("trim_purchase",      "辅料到厂 Trims arrival"),
    ("pp_sample",          "样衣确认 Sample confirmation"),
    ("base_size_pattern",  "大货版 Bulk pattern"),
    ("full_sized_pattern", "全码版 Full-size pattern"),
    ("cutting",            "裁剪完成 Cutting complete"),
    ("sewing",             "车位完成 Sewing complete"),
    ("packing",            "后道完成 Finishing complete"),
    ("shipping",           "工厂交期 Factory delivery"),
]
MILESTONE_LABELS: dict[str, str] = dict(MILESTONE_STAGES)

_FACTORY_PROGRESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS factory_progress_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number   TEXT NOT NULL,
    style       TEXT NOT NULL DEFAULT '',
    factory     TEXT NOT NULL DEFAULT '',
    stage       TEXT NOT NULL,              -- 'cutting' | 'sewing' | 'packing'
    report_date TEXT NOT NULL,              -- date the factory reports FOR (ISO)
    units       INTEGER NOT NULL,           -- units completed in this report (incremental)
    source      TEXT NOT NULL DEFAULT 'manual',  -- 'manual' | 'excel'
    notes       TEXT DEFAULT '',
    created_at  TEXT,
    created_by  TEXT
);
CREATE INDEX IF NOT EXISTS idx_fpr_po_style ON factory_progress_reports(po_number, style);
CREATE INDEX IF NOT EXISTS idx_fpr_factory  ON factory_progress_reports(factory);
"""
