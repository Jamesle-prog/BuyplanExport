"""Store for fabric presentation sheets (面料推荐单).

A presentation is a list of fabrics recommended to one customer, built from
``fabric_master`` and frozen at build time: the prices printed on the sheet
are stored with it, not re-read later (see ``_fabric_presentation_schema``).

Each sheet carries a QR token.  Scanning it hits the ``web_scan`` service,
which records the scan here — so a sheet's history answers when it went out
and which fabrics were on it.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

import pandas as pd

from .base_store import BaseSQLiteStore
from ._fabric_presentation_schema import _FABRIC_PRESENTATION_SCHEMA
from ..utils.fabric_quote import (
    DEFAULT_FX_RATE, DEFAULT_MARKUP, DEFAULT_ROUND_STEP, usd_per_yard,
)

# Token length in bytes before base64 — 9 bytes ≈ 12 URL-safe chars.  This is
# a LAN-internal identifier, not a secret, but it must not be guessable by
# incrementing a number: a customer-facing sheet should not expose how many
# other sheets exist.
_TOKEN_BYTES = 9

_LINE_COLS = (
    "line_no", "quality_no", "style", "season", "content", "description",
    "weight_gsm", "width_in", "moq_y", "mcq_y", "price_rmb_m", "price_usd_y",
)


class FabricPresentationStore(BaseSQLiteStore):
    """Read/write access to the fabric_presentation* tables."""

    _checked_paths: set[str] = set()

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path not in FabricPresentationStore._checked_paths:
            self._ensure_schema()
            FabricPresentationStore._checked_paths.add(db_path)

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_FABRIC_PRESENTATION_SCHEMA)

    # ── create ──────────────────────────────────────────────────────────────

    def create(self, *, lines: list[dict[str, Any]],
               title: str = "", customer: str = "", season: str = "",
               submission_date: str = "", fabric_type: str = "",
               markup: float = DEFAULT_MARKUP,
               fx_rate: float = DEFAULT_FX_RATE,
               round_step: float = DEFAULT_ROUND_STEP,
               created_by: str = "", notes: str = "") -> dict[str, Any]:
        """Build one presentation from *lines* and return its header record.

        Each line needs at least ``quality_no``; ``price_rmb_m`` drives the
        quote.  ``price_usd_y`` is computed here rather than taken from the
        caller so every stored sheet is consistent with the parameters
        recorded alongside it.
        """
        if not lines:
            raise ValueError("A presentation needs at least one fabric line")

        now = datetime.now().isoformat(timespec="seconds")
        token = self._new_token()

        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO fabric_presentations
                   (token, title, customer, season, submission_date, fabric_type,
                    markup, fx_rate, round_step, created_at, created_by, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (token, title, customer, season, submission_date, fabric_type,
                 markup, fx_rate, round_step, now, created_by, notes),
            )
            pres_id = cur.lastrowid

            for i, line in enumerate(lines, 1):
                rmb = line.get("price_rmb_m")
                usd = usd_per_yard(rmb, markup=markup, fx_rate=fx_rate,
                                   round_step=round_step)
                conn.execute(
                    f"""INSERT INTO fabric_presentation_lines
                        (presentation_id, {', '.join(_LINE_COLS)})
                        VALUES (?,{','.join('?' * len(_LINE_COLS))})""",
                    (pres_id,
                     line.get("line_no") or i,
                     str(line.get("quality_no") or ""),
                     str(line.get("style") or ""),
                     str(line.get("season") or season or ""),
                     str(line.get("content") or ""),
                     str(line.get("description") or ""),
                     line.get("weight_gsm"),
                     str(line.get("width_in") or ""),
                     line.get("moq_y"),
                     line.get("mcq_y"),
                     rmb,
                     usd),
                )
        return self.get(pres_id) or {}

    def _new_token(self) -> str:
        """A token not already in use.  Retries rather than trusting luck."""
        with self._conn() as conn:
            for _ in range(10):
                tok = secrets.token_urlsafe(_TOKEN_BYTES)
                hit = conn.execute(
                    "SELECT 1 FROM fabric_presentations WHERE token = ?", (tok,)
                ).fetchone()
                if not hit:
                    return tok
        raise RuntimeError("Could not allocate a unique presentation token")

    # ── read ────────────────────────────────────────────────────────────────

    def get(self, presentation_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM fabric_presentations WHERE id = ?",
                (presentation_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_token(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM fabric_presentations WHERE token = ?", (token,)
            ).fetchone()
        return dict(row) if row else None

    def lines(self, presentation_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM fabric_presentation_lines
                   WHERE presentation_id = ? ORDER BY line_no, id""",
                (presentation_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self, *, limit: int = 200) -> pd.DataFrame:
        """Recent sheets, newest first, with their line and scan counts."""
        cols = ["id", "token", "title", "customer", "season", "submission_date",
                "fabric_type", "created_at", "created_by", "n_lines",
                "n_scans", "first_scan", "last_scan"]
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT p.*,
                          (SELECT COUNT(*) FROM fabric_presentation_lines l
                            WHERE l.presentation_id = p.id) AS n_lines,
                          (SELECT COUNT(*) FROM fabric_presentation_scans s
                            WHERE s.presentation_id = p.id) AS n_scans,
                          (SELECT MIN(scanned_at) FROM fabric_presentation_scans s
                            WHERE s.presentation_id = p.id) AS first_scan,
                          (SELECT MAX(scanned_at) FROM fabric_presentation_scans s
                            WHERE s.presentation_id = p.id) AS last_scan
                     FROM fabric_presentations p
                 ORDER BY p.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        recs = [dict(r) for r in rows]
        return pd.DataFrame(recs, columns=cols) if recs else pd.DataFrame(columns=cols)

    # ── scans ───────────────────────────────────────────────────────────────

    def log_scan(self, token: str, *, client_ip: str = "",
                 user_agent: str = "") -> dict[str, Any] | None:
        """Record a QR scan.  Returns the presentation, or None if unknown.

        An unknown token is not an error worth raising — a mistyped or
        retired sheet should render a "not found" page, not a 500.
        """
        pres = self.get_by_token(token)
        if not pres:
            return None
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO fabric_presentation_scans
                   (presentation_id, scanned_at, client_ip, user_agent)
                   VALUES (?,?,?,?)""",
                (pres["id"], datetime.now().isoformat(timespec="seconds"),
                 client_ip, user_agent[:300]),
            )
        return pres

    def scans(self, presentation_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM fabric_presentation_scans
                   WHERE presentation_id = ? ORDER BY scanned_at DESC, id DESC""",
                (presentation_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── delete ──────────────────────────────────────────────────────────────

    def delete(self, presentation_id: int) -> bool:
        """Remove a sheet and everything recorded against it."""
        with self._conn() as conn:
            conn.execute("DELETE FROM fabric_presentation_scans WHERE presentation_id = ?",
                         (presentation_id,))
            conn.execute("DELETE FROM fabric_presentation_lines WHERE presentation_id = ?",
                         (presentation_id,))
            cur = conn.execute("DELETE FROM fabric_presentations WHERE id = ?",
                               (presentation_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM fabric_presentations").fetchone()[0]
