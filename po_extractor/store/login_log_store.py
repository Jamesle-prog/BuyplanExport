"""SQLite store for the sign-in audit log (Admin → 🔐 Login Log).

One row per sign-in attempt: who, when, and how it went (success, wrong
password, or blocked by the lockout). Successful logins answer the core
question ("who logged in at what time"); the failed/locked rows are kept in
the same table because they are the security-relevant half of the same
story — an admin filters to whichever they want.

Writing must never break the login itself: :meth:`record` swallows its own
errors so a logging hiccup can't stop a real user from signing in.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base_store import BaseSQLiteStore

OUTCOME_SUCCESS = "success"
OUTCOME_FAILED  = "failed"     # wrong username/password
OUTCOME_LOCKED  = "locked"     # blocked by the lockout backoff

OUTCOMES = (OUTCOME_SUCCESS, OUTCOME_FAILED, OUTCOME_LOCKED)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS login_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT NOT NULL DEFAULT '',
    ts        TEXT NOT NULL,
    outcome   TEXT NOT NULL DEFAULT 'success',
    detail    TEXT NOT NULL DEFAULT '',
    ip        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_login_log_ts ON login_log(ts);
CREATE INDEX IF NOT EXISTS idx_login_log_outcome ON login_log(outcome);
"""


class LoginLogStore(BaseSQLiteStore):
    """Append-only sign-in log with admin-side reads."""

    _checked_paths: set[str] = set()

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path not in LoginLogStore._checked_paths:
            with self._conn() as conn:
                conn.executescript(_SCHEMA)
            LoginLogStore._checked_paths.add(db_path)

    # ── Write ────────────────────────────────────────────────────────────────

    def record(self, username: str, outcome: str = OUTCOME_SUCCESS, *,
               detail: str = "", ip: str = "") -> None:
        """Append one sign-in event. Never raises — a logging failure must not
        block the login it is trying to record."""
        try:
            if outcome not in OUTCOMES:
                outcome = OUTCOME_FAILED
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO login_log (username, ts, outcome, detail, ip) "
                    "VALUES (?,?,?,?,?)",
                    ((username or "").strip(),
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     outcome, detail or "", ip or ""),
                )
        except Exception:
            pass

    # ── Read ─────────────────────────────────────────────────────────────────

    def list_recent(self, limit: int = 200, *, outcome: str | None = None,
                    username_like: str | None = None) -> list[dict]:
        """Recent events, newest first. Optional exact-outcome and
        case-insensitive username-substring filters."""
        where, params = [], []
        if outcome in OUTCOMES:
            where.append("outcome = ?")
            params.append(outcome)
        if username_like:
            where.append("LOWER(username) LIKE ?")
            params.append(f"%{username_like.strip().lower()}%")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT id, username, ts, outcome, detail, ip FROM login_log"
                f"{clause} ORDER BY id DESC LIMIT ?",
                (*params, int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict:
        """``{"total", "success", "failed", "locked", "users"}`` for the
        metrics row (one query, not five)."""
        with self._conn() as conn:
            by_outcome = dict(conn.execute(
                "SELECT outcome, COUNT(*) FROM login_log GROUP BY outcome"
            ).fetchall())
            users = conn.execute(
                "SELECT COUNT(DISTINCT username) FROM login_log "
                "WHERE outcome = ?", (OUTCOME_SUCCESS,)
            ).fetchone()[0]
        return {
            "total":   sum(by_outcome.values()),
            "success": by_outcome.get(OUTCOME_SUCCESS, 0),
            "failed":  by_outcome.get(OUTCOME_FAILED, 0),
            "locked":  by_outcome.get(OUTCOME_LOCKED, 0),
            "users":   users,
        }

    def last_login(self, username: str) -> str | None:
        """Timestamp of a user's most recent SUCCESSFUL sign-in, or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT ts FROM login_log WHERE username = ? AND outcome = ? "
                "ORDER BY id DESC LIMIT 1",
                ((username or "").strip(), OUTCOME_SUCCESS),
            ).fetchone()
        return row[0] if row else None

    # ── Maintenance ───────────────────────────────────────────────────────────

    def purge_older_than(self, days: int) -> int:
        """Delete events older than *days*. Returns rows removed."""
        if days <= 0:
            return 0
        cutoff = (datetime.now() - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM login_log WHERE ts < ?", (cutoff,))
        return cur.rowcount

    def clear(self) -> int:
        """Delete every event. Returns rows removed."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM login_log")
        return cur.rowcount
