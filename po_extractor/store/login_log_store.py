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
    ip        TEXT NOT NULL DEFAULT '',
    -- Session tracking. A successful sign-in opens a session: `session_id`
    -- identifies it, `last_seen` is refreshed while the user is active, and
    -- `ended_ts`/`end_kind` close it. Duration is
    -- COALESCE(ended_ts, last_seen) - ts, so a browser closed without signing
    -- out still yields a real (if slightly short) figure instead of nothing.
    session_id TEXT NOT NULL DEFAULT '',
    last_seen  TEXT NOT NULL DEFAULT '',
    ended_ts   TEXT NOT NULL DEFAULT '',
    end_kind   TEXT NOT NULL DEFAULT ''
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
                # Existing databases predate the session columns; CREATE TABLE
                # IF NOT EXISTS is a no-op for them, so add each explicitly.
                cols = {r[1] for r in conn.execute("PRAGMA table_info(login_log)")}
                for name in ("session_id", "last_seen", "ended_ts", "end_kind"):
                    if name not in cols:
                        self._add_column_if_missing(
                            conn, "login_log", name, "TEXT NOT NULL DEFAULT ''")
            LoginLogStore._checked_paths.add(db_path)

    # ── Write ────────────────────────────────────────────────────────────────

    def record(self, username: str, outcome: str = OUTCOME_SUCCESS, *,
               detail: str = "", ip: str = "", session_id: str = "") -> None:
        """Append one sign-in event. Never raises — a logging failure must not
        block the login it is trying to record.

        A successful sign-in also opens a session: last_seen starts equal to
        the sign-in time, so a session that is never touched again still has a
        duration of zero rather than a null.
        """
        try:
            if outcome not in OUTCOMES:
                outcome = OUTCOME_FAILED
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            opens_session = outcome == OUTCOME_SUCCESS and session_id
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO login_log (username, ts, outcome, detail, ip, "
                    "session_id, last_seen) VALUES (?,?,?,?,?,?,?)",
                    ((username or "").strip(), now, outcome, detail or "",
                     ip or "", session_id or "", now if opens_session else ""),
                )
        except Exception:
            pass

    def touch(self, session_id: str) -> None:
        """Refresh a session's last_seen. Never raises.

        Called on user activity, throttled by the caller -- most people never
        sign out, so this is what makes "how long were they in" answerable at
        all. Only ever moves last_seen forward on an OPEN session, so a
        late-arriving heartbeat cannot reopen one already closed.
        """
        if not session_id:
            return
        try:
            with self._conn() as conn:
                conn.execute(
                    "UPDATE login_log SET last_seen = ? "
                    "WHERE session_id = ? AND ended_ts = ''",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session_id),
                )
        except Exception:
            pass

    def end_session(self, session_id: str, kind: str = "signout") -> None:
        """Close a session. Never raises.

        *kind* distinguishes a deliberate sign-out from any other ending, so
        the log can show which sessions were closed properly.
        """
        if not session_id:
            return
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._conn() as conn:
                conn.execute(
                    "UPDATE login_log SET ended_ts = ?, end_kind = ?, "
                    "last_seen = ? WHERE session_id = ? AND ended_ts = ''",
                    (now, kind or "signout", now, session_id),
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
                f"SELECT id, username, ts, outcome, detail, ip, session_id, "
                f"last_seen, ended_ts, end_kind FROM login_log"
                f"{clause} ORDER BY id DESC LIMIT ?",
                (*params, int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def sessions(self, limit: int = 200, *,
                 username_like: str | None = None) -> list[dict]:
        """Successful sign-ins as sessions, newest first, with duration.

        duration_min = COALESCE(ended_ts, last_seen) - ts, in minutes. A
        session with neither (an old row from before session tracking, or one
        that never registered activity) reports None rather than 0, so
        "unknown" is never mistaken for "instant".

        `open` marks a session with no ended_ts -- either still in use or a
        browser closed without signing out; `end_kind` tells them apart.
        """
        where = ["outcome = ?"]
        params: list = [OUTCOME_SUCCESS]
        if username_like:
            where.append("LOWER(username) LIKE ?")
            params.append(f"%{username_like.strip().lower()}%")
        clause = " WHERE " + " AND ".join(where)
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT id, username, ts, ip, session_id, last_seen,
                           ended_ts, end_kind,
                           CAST(ROUND((julianday(
                               CASE WHEN ended_ts != '' THEN ended_ts
                                    WHEN last_seen != '' THEN last_seen
                                    ELSE NULL END
                           ) - julianday(ts)) * 1440) AS INTEGER)
                               AS duration_min
                    FROM login_log{clause}
                    ORDER BY id DESC LIMIT ?""",
                (*params, int(limit)),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["open"] = not d["ended_ts"]
            out.append(d)
        return out

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
