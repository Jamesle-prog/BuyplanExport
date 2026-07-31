"""Schema for the settlement statistics module (结算统计表).

Three tables:

  - ``settlements``        — one row per invoice line: contracted, shipped,
    invoiced, received, and everything paid back out against it
  - ``settlement_samples`` — the 样品 sheet: sample cost per style
  - ``settlement_imports`` — one row per upload, so it is always answerable
    which file the figures on screen came from and when

The workbook is the master (it is maintained by hand, in Excel), so an import
**replaces** the sheets it contains and leaves the others alone.  That is why
``sheet`` is stored on every row rather than being flattened into client/year:
re-importing one client's year must not touch another's.

Money is stored per row in the row's own ``currency``.  Sheets differ — the SC
2026 book is in GBP — and adding a GBP line to a USD one would produce a
number that is not an amount of anything.  Nothing in this module sums across
currencies; totals are always grouped by it.
"""
from __future__ import annotations

_SETTLEMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS settlements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sheet           TEXT NOT NULL,              -- source sheet, the import key
    client          TEXT DEFAULT '',            -- inferred from the sheet name
    year            TEXT DEFAULT '',
    currency        TEXT DEFAULT 'USD',
    row_no          INTEGER DEFAULT 0,          -- row in the sheet, for tracing

    invoice_no      TEXT DEFAULT '',
    zalando_po       TEXT DEFAULT '',            -- the client's PO (PO#)
    style           TEXT DEFAULT '',            -- 款号
    contract_no     TEXT DEFAULT '',            -- 合同号
    factory         TEXT DEFAULT '',
    repeat_or_new   TEXT DEFAULT '',            -- 翻单还是新款

    contract_qty    REAL,                       -- 合同数量
    unit_cost       REAL,                       -- 采购单价 / 加工费
    fob             REAL,
    contract_amount REAL,                       -- 合同金额
    ex_factory      TEXT DEFAULT '',            -- 离厂时间 (may be a revision)
    shipped_qty     REAL,                       -- 出货数
    over_short_pct  REAL,                       -- 溢短装

    invoice_amount  REAL,                       -- 发票金额 (报关金额)
    received        REAL,                       -- 实际收汇
    received_date   TEXT DEFAULT '',

    pay_fabric      REAL,                       -- 支付 / 面料款
    pay_fabric_date TEXT DEFAULT '',
    pay_trim        REAL,                       -- 支付 / 辅料款
    pay_trim_date   TEXT DEFAULT '',
    pay_cmt         REAL,                       -- 支付 / 加工费
    pay_cmt_date    TEXT DEFAULT '',
    fee_port        REAL,                       -- 费用 / 港杂费 (含运费)
    fee_other1      REAL,                       -- 费用 / 其他一
    fee_other2      REAL,                       -- 费用 / 其他二 (税金)

    -- Recorded in the workbook only as a cell fill; see the parser.
    discount_risk   INTEGER DEFAULT 0,
    contract_status TEXT DEFAULT '',            -- '' | 'sent' | 'signed'

    imported_at     TEXT,
    imported_by     TEXT
);

CREATE INDEX IF NOT EXISTS idx_settlements_sheet    ON settlements(sheet);
CREATE INDEX IF NOT EXISTS idx_settlements_po       ON settlements(zalando_po);
CREATE INDEX IF NOT EXISTS idx_settlements_style    ON settlements(style);
CREATE INDEX IF NOT EXISTS idx_settlements_contract ON settlements(contract_no);
CREATE INDEX IF NOT EXISTS idx_settlements_invoice  ON settlements(invoice_no);

CREATE TABLE IF NOT EXISTS settlement_samples (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    style    TEXT NOT NULL,
    client   TEXT DEFAULT '',
    factory  TEXT DEFAULT '',
    fabric   REAL,
    lining   REAL,
    rib      REAL,
    trim     REAL,
    total    REAL,
    row_no   INTEGER DEFAULT 0,
    imported_at TEXT,
    imported_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_settlement_samples_style
    ON settlement_samples(style);

CREATE TABLE IF NOT EXISTS settlement_imports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file  TEXT DEFAULT '',
    source_hash  TEXT DEFAULT '',
    sheets       TEXT DEFAULT '',        -- comma-joined sheet names replaced
    n_rows       INTEGER DEFAULT 0,
    n_samples    INTEGER DEFAULT 0,
    skipped      TEXT DEFAULT '',        -- sheets deliberately not imported
    imported_at  TEXT,
    imported_by  TEXT
);
"""
