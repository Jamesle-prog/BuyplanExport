"""Schema for CMPT (加工) contracts with factories.

Three tables:
  - ``cmpt_contracts``       — one row per contract (factory, date, status)
  - ``cmpt_contract_lines``  — PO/style lines: qty × agreed unit price
  - ``cmpt_payments``        — dated payment log (amount, method, note)

Agreed value = SUM(lines qty × unit_price); paid = SUM(payments);
balance = agreed - paid. All three are always computed, never stored, so
they can't drift from the underlying lines/payments.
"""
from __future__ import annotations

CONTRACT_STATUSES: list[str] = ["draft", "signed", "completed", "cancelled"]

CONTRACT_STATUS_LABELS: dict[str, str] = {
    "draft":     "草拟 Draft",
    "signed":    "已签署 Signed",
    "completed": "已完成 Completed",
    "cancelled": "已取消 Cancelled",
}

_CMPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS cmpt_contracts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no   TEXT NOT NULL UNIQUE,
    factory       TEXT NOT NULL,
    company       TEXT DEFAULT '',            -- client company the POs belong to
    contract_date TEXT DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',
    currency      TEXT NOT NULL DEFAULT 'RMB',
    notes         TEXT DEFAULT '',
    created_at    TEXT,
    created_by    TEXT,
    updated_at    TEXT,
    updated_by    TEXT
);

CREATE TABLE IF NOT EXISTS cmpt_contract_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    po_number   TEXT DEFAULT '',
    style       TEXT DEFAULT '',
    color       TEXT DEFAULT '',
    description TEXT DEFAULT '',
    qty         INTEGER NOT NULL DEFAULT 0,
    unit_price  REAL NOT NULL DEFAULT 0       -- agreed CMPT price per unit
);
CREATE INDEX IF NOT EXISTS idx_ccl_contract ON cmpt_contract_lines(contract_id);

CREATE TABLE IF NOT EXISTS cmpt_payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    pay_date    TEXT NOT NULL,
    amount      REAL NOT NULL,
    method      TEXT DEFAULT '',              -- 电汇/承兑/现金/...
    note        TEXT DEFAULT '',
    recorded_at TEXT,
    recorded_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_cp_contract ON cmpt_payments(contract_id);
"""
