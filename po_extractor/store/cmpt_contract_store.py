"""SQLite store for CMPT (加工) contracts with factories.

Contracts + PO/style price lines + a dated payment log. Agreed value,
paid total, and outstanding balance are always computed from the lines
and payments (see ``_cmpt_schema.py``).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .base_store import BaseSQLiteStore
from ._cmpt_schema import _CMPT_SCHEMA, CONTRACT_STATUSES


class CmptContractStore(BaseSQLiteStore):
    """Read/write access to the cmpt_* tables."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_CMPT_SCHEMA)

    # ── Contracts ───────────────────────────────────────────────────────────

    def create_contract(self, contract_no: str, factory: str, *,
                        company: str = "", contract_date: str = "",
                        currency: str = "RMB", notes: str = "",
                        lines: list[dict] | None = None,
                        created_by: str = "") -> int:
        """Create a contract (status 'draft') with optional initial *lines*
        (dicts: po_number/style/color/description/qty/unit_price).
        Returns the contract id. Raises ValueError on missing/duplicate
        contract_no or missing factory.
        """
        contract_no = (contract_no or "").strip()
        factory = (factory or "").strip()
        if not contract_no:
            raise ValueError("contract_no is required.")
        if not factory:
            raise ValueError("factory is required.")
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._conn() as conn:
            dup = conn.execute(
                "SELECT id FROM cmpt_contracts WHERE contract_no=?",
                (contract_no,),
            ).fetchone()
            if dup:
                raise ValueError(f"Contract no. {contract_no!r} already exists.")
            cur = conn.execute(
                """INSERT INTO cmpt_contracts
                      (contract_no, factory, company, contract_date, status,
                       currency, notes, created_at, created_by,
                       updated_at, updated_by)
                   VALUES (?,?,?,?,'draft',?,?,?,?,?,?)""",
                (contract_no, factory, company or "", contract_date or "",
                 currency or "RMB", notes or "", now, created_by or "",
                 now, created_by or ""),
            )
            cid = int(cur.lastrowid)
            self._insert_lines(conn, cid, lines or [])
        return cid

    def replace_lines(self, contract_id: int, lines: list[dict],
                      updated_by: str = "") -> None:
        """Replace ALL lines of a contract (the line editor saves the whole
        table at once — simplest correct semantics for a small line set)."""
        with self._conn() as conn:
            self._require_contract(conn, contract_id)
            conn.execute("DELETE FROM cmpt_contract_lines WHERE contract_id=?",
                         (contract_id,))
            self._insert_lines(conn, contract_id, lines)
            self._touch(conn, contract_id, updated_by)

    @staticmethod
    def _insert_lines(conn, contract_id: int, lines: list[dict]) -> None:
        rows = []
        for ln in lines:
            qty = int(ln.get("qty") or 0)
            price = float(ln.get("unit_price") or 0)
            if qty <= 0 and not (ln.get("po_number") or ln.get("style")
                                 or ln.get("description")):
                continue    # fully empty editor row
            rows.append((
                contract_id,
                str(ln.get("po_number") or "").strip(),
                str(ln.get("style") or "").strip(),
                str(ln.get("color") or "").strip(),
                str(ln.get("description") or "").strip(),
                qty, price,
            ))
        if rows:
            conn.executemany(
                """INSERT INTO cmpt_contract_lines
                      (contract_id, po_number, style, color, description,
                       qty, unit_price)
                   VALUES (?,?,?,?,?,?,?)""",
                rows,
            )

    def update_contract(self, contract_id: int, *, updated_by: str = "",
                        **fields: Any) -> None:
        """Update header fields (factory, company, contract_date, status,
        currency, notes). Unknown fields raise; status is validated."""
        allowed = {"factory", "company", "contract_date", "status",
                   "currency", "notes"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"Unknown contract fields: {sorted(bad)}")
        if "status" in fields and fields["status"] not in CONTRACT_STATUSES:
            raise ValueError(f"Unknown status {fields['status']!r}.")
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self._conn() as conn:
            self._require_contract(conn, contract_id)
            conn.execute(
                f"UPDATE cmpt_contracts SET {sets} WHERE id=?",
                [*fields.values(), contract_id],
            )
            self._touch(conn, contract_id, updated_by)

    def delete_contract(self, contract_id: int) -> None:
        """Delete a contract with its lines and payments (admin path)."""
        with self._conn() as conn:
            conn.execute("DELETE FROM cmpt_payments WHERE contract_id=?", (contract_id,))
            conn.execute("DELETE FROM cmpt_contract_lines WHERE contract_id=?", (contract_id,))
            conn.execute("DELETE FROM cmpt_contracts WHERE id=?", (contract_id,))

    # ── Payments ────────────────────────────────────────────────────────────

    def add_payment(self, contract_id: int, pay_date: str, amount: float, *,
                    method: str = "", note: str = "",
                    recorded_by: str = "") -> int:
        """Add one payment. Amount must be non-zero (negative = refund)."""
        amount = float(amount)
        if amount == 0:
            raise ValueError("Payment amount must be non-zero.")
        if not (pay_date or "").strip():
            raise ValueError("pay_date is required.")
        with self._conn() as conn:
            self._require_contract(conn, contract_id)
            cur = conn.execute(
                """INSERT INTO cmpt_payments
                      (contract_id, pay_date, amount, method, note,
                       recorded_at, recorded_by)
                   VALUES (?,?,?,?,?,?,?)""",
                (contract_id, pay_date.strip(), amount, method or "",
                 note or "", datetime.utcnow().isoformat(timespec="seconds"),
                 recorded_by or ""),
            )
        return int(cur.lastrowid)

    def delete_payments(self, ids: list[int]) -> int:
        if not ids:
            return 0
        ph = ",".join("?" * len(ids))
        with self._conn() as conn:
            cur = conn.execute(f"DELETE FROM cmpt_payments WHERE id IN ({ph})", ids)
        return cur.rowcount

    # ── Reads ───────────────────────────────────────────────────────────────

    # Shared aggregate header query — list_contracts and get_contract compute
    # the same fields (total_qty / line_count / agreed_total / paid_total).
    _HEADER_SQL = """
        SELECT c.*,
               COALESCE(l.total_qty, 0)    AS total_qty,
               COALESCE(l.line_count, 0)   AS line_count,
               COALESCE(l.agreed_total, 0) AS agreed_total,
               COALESCE(p.paid_total, 0)   AS paid_total
        FROM cmpt_contracts c
        LEFT JOIN (
            SELECT contract_id, SUM(qty) AS total_qty, COUNT(*) AS line_count,
                   SUM(qty * unit_price) AS agreed_total
            FROM cmpt_contract_lines GROUP BY contract_id
        ) l ON l.contract_id = c.id
        LEFT JOIN (
            SELECT contract_id, SUM(amount) AS paid_total
            FROM cmpt_payments GROUP BY contract_id
        ) p ON p.contract_id = c.id
        {where}
        ORDER BY c.id DESC
    """

    def list_contracts(self, factory: str | None = None,
                       status: str | None = None) -> list[dict]:
        """Contract headers newest first, each with computed ``agreed_total``
        / ``paid_total`` / ``balance`` / ``total_qty`` / ``line_count``."""
        where, params = [], []
        if factory:
            where.append("c.factory=?"); params.append(factory)
        if status:
            where.append("c.status=?"); params.append(status)
        sql = self._HEADER_SQL.format(
            where="WHERE " + " AND ".join(where) if where else "")
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["balance"] = round((d["agreed_total"] or 0) - (d["paid_total"] or 0), 2)
            out.append(d)
        return out

    def get_contract(self, contract_id: int) -> dict | None:
        """Full contract: header (with computed totals) + lines + payments."""
        sql = self._HEADER_SQL.format(where="WHERE c.id=?")
        with self._conn() as conn:
            row = conn.execute(sql, (contract_id,)).fetchone()
            if row is None:
                return None
            contract = dict(row)
            contract["balance"] = round(
                (contract["agreed_total"] or 0) - (contract["paid_total"] or 0), 2)
            contract["lines"] = [dict(r) for r in conn.execute(
                "SELECT * FROM cmpt_contract_lines WHERE contract_id=? ORDER BY id",
                (contract_id,),
            ).fetchall()]
            contract["payments"] = [dict(r) for r in conn.execute(
                "SELECT * FROM cmpt_payments WHERE contract_id=? "
                "ORDER BY pay_date, id",
                (contract_id,),
            ).fetchall()]
        for ln in contract["lines"]:
            ln["amount"] = round(ln["qty"] * ln["unit_price"], 2)
        return contract

    def list_factories(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT factory FROM cmpt_contracts ORDER BY factory"
            ).fetchall()
        return [r["factory"] for r in rows if r["factory"]]

    def next_contract_no(self, prefix: str = "CMPT") -> str:
        """Suggest the next contract number: ``{prefix}-{YYYY}-{NNN}``.

        Sequence restarts each year and is derived from the highest existing
        number in that year's series (gaps are not refilled). Contract numbers
        in other formats are ignored -- the suggestion is only a convenience
        default, the field stays editable and uniqueness is still enforced by
        ``create_contract``.
        """
        year_pat = f"{prefix}-{datetime.now().strftime('%Y')}-"
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT contract_no FROM cmpt_contracts WHERE contract_no LIKE ?",
                (year_pat + "%",),
            ).fetchall()
        max_seq = 0
        for r in rows:
            tail = r["contract_no"][len(year_pat):]
            if tail.isdigit():
                max_seq = max(max_seq, int(tail))
        return f"{year_pat}{max_seq + 1:03d}"

    # ── Internals ───────────────────────────────────────────────────────────

    @staticmethod
    def _require_contract(conn, contract_id: int) -> None:
        if conn.execute("SELECT id FROM cmpt_contracts WHERE id=?",
                        (contract_id,)).fetchone() is None:
            raise ValueError(f"No contract with id={contract_id}.")

    @staticmethod
    def _touch(conn, contract_id: int, updated_by: str) -> None:
        conn.execute(
            "UPDATE cmpt_contracts SET updated_at=?, updated_by=? WHERE id=?",
            (datetime.utcnow().isoformat(timespec="seconds"),
             updated_by or "", contract_id),
        )
