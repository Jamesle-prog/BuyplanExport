"""Schema for the actual fabric condition module (面料情况).

One table, ``fabric_condition``: one row per delivery/test logged on the shop
floor — measured width and weight against nominal, shrinkage test results,
cutting requirements, net consumption, and remaining stock.

Every column except ``seq`` and ``row_no`` is TEXT, storing the sheet's own
value verbatim. The source is a hand-typed log full of ranges ("176-178"),
approximations ("100层左右"), and words instead of numbers ("无", "同上") — a
numeric column would silently discard whichever of those didn't fit. See the
parser (``po_extractor/parsers/fabric_condition.py``) for the full rationale.

This is a single-sheet source, unlike the settlement workbook's several
client-years — so an import simply replaces the whole table rather than
replacing per partition.
"""
from __future__ import annotations

_FABRIC_CONDITION_SCHEMA = """
CREATE TABLE IF NOT EXISTS fabric_condition (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    row_no        INTEGER DEFAULT 0,      -- row in the source sheet, for tracing
    seq           INTEGER,                -- 序号 — the sheet's own batch number;
                                           -- not always filled in, and not unique
    test_date     TEXT DEFAULT '',        -- 日期
    fabric_no     TEXT DEFAULT '',        -- 面料编号
    style         TEXT DEFAULT '',        -- 款号
    body_part     TEXT DEFAULT '',        -- 部位
    color         TEXT DEFAULT '',        -- 颜色
    width_net     TEXT DEFAULT '',        -- 有效门幅 (cm)
    width_gross   TEXT DEFAULT '',        -- 毛门幅 (cm)
    weight_gsm    TEXT DEFAULT '',        -- 克重 (g)
    shrink_fabric_warp  TEXT DEFAULT '',  -- 面料缩率 / 径向
    shrink_fabric_weft  TEXT DEFAULT '',  -- 面料缩率 / 纬向
    shrink_pattern_warp TEXT DEFAULT '',  -- 纸板缩率 / 径向
    shrink_pattern_weft TEXT DEFAULT '',  -- 纸板缩率 / 纬向
    over_cut_pct        TEXT DEFAULT '',  -- 超裁%
    max_plies           TEXT DEFAULT '',  -- 裁剪最高层数
    max_cut_length      TEXT DEFAULT '',  -- 裁剪最大长度
    cut_direction        TEXT DEFAULT '', -- 裁剪方向及要求
    consumption_purchase_body    TEXT DEFAULT '',  -- 采购净单耗(cm)-大身
    consumption_purchase_binding TEXT DEFAULT '',  -- 采购净单耗(cm)-滚条
    consumption_layout_body      TEXT DEFAULT '',  -- 排版净单耗(cm)-大身
    consumption_layout_binding   TEXT DEFAULT '',  -- 排版净单耗(cm)-滚条
    remaining_rolls TEXT DEFAULT '',      -- 剩余面料 (匹)
    remaining_kg    TEXT DEFAULT '',      -- 剩余面料 (kg)
    remaining_m     TEXT DEFAULT '',      -- 剩余面料 (m)

    imported_at   TEXT,
    imported_by   TEXT
);

CREATE INDEX IF NOT EXISTS idx_fabric_condition_style ON fabric_condition(style);
CREATE INDEX IF NOT EXISTS idx_fabric_condition_color ON fabric_condition(color);
CREATE INDEX IF NOT EXISTS idx_fabric_condition_fabric_no
    ON fabric_condition(fabric_no);

CREATE TABLE IF NOT EXISTS fabric_condition_imports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file  TEXT DEFAULT '',
    source_hash  TEXT DEFAULT '',
    n_records    INTEGER DEFAULT 0,
    imported_at  TEXT,
    imported_by  TEXT
);
"""
