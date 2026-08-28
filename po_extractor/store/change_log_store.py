"""One app-wide record of who changed what, and when.

Existing history tables answer *what* changed -- ``sky_east_item_history``
keeps the whole superseded row, ``po_version_history`` keeps prior PO
versions -- but neither records *who* did it, and each answers only for its
own corner. This table is the single place to ask "what did angel change last
Tuesday", across every module.

It does not replace those tables. They keep full prior rows for recovery; this
keeps a narrow, uniform, queryable trail:

    when · who · entity · which record · what field · old -> new

Design rules, each learned from something in this codebase:

* **Writing must never break the write it describes.** :meth:`record` and
  :meth:`record_many` swallow their own errors, the same rule
  ``LoginLogStore.record`` follows -- an audit hiccup must not stop a user
  saving a contract.
* **The user comes from :mod:`po_extractor.store.audit_context`**, not from a
  parameter, so a new store method cannot silently forget to pass it. An
  unknown user records as "" rather than blocking the write.
* **Values are stored as short text.** Anything long is truncated
  (``_MAX_VALUE``) -- this is an index for humans, not a blob store, and a
  runaway value (a whole workbook, a base64 image) must not bloat the DB.
* **Append-only.** No update path. :meth:`purge_older_than` is the only
  removal, for retention.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from .audit_context import current_user
from .base_store import BaseSQLiteStore

# Actions. Free-form is tempting but a fixed set keeps the UI filter honest.
ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"
ACTIONS = (ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE)

# Entities in use. A new caller adds a constant here rather than a new table,
# so the admin filter stays a closed list.
ENTITY_BOAT_SAMPLE = "boat_sample_req"      # 船样要求
ENTITY_SKY_EAST_ITEM = "sky_east_item"      # contract line amendments
ENTITY_USER = "user"                        # accounts, roles, scopes

_MAX_VALUE = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS change_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    username   TEXT NOT NULL DEFAULT '',
    entity     TEXT NOT NULL,
    record_key TEXT NOT NULL DEFAULT '',
    action     TEXT NOT NULL DEFAULT 'update',
    field      TEXT NOT NULL DEFAULT '',
    old_value  TEXT NOT NULL DEFAULT '',
    new_value  TEXT NOT NULL DEFAULT '',
    detail     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_change_log_ts       ON change_log(ts);
CREATE INDEX IF NOT EXISTS idx_change_log_user     ON change_log(username);
CREATE INDEX IF NOT EXISTS idx_change_log_entity   ON change_log(entity, record_key);
"""


def _clip(value) -> str:
    """A short, printable form of any value. Never raises."""
    try:
        s = "" if value is None else str(value)
    except Exception:
        return "<unprintable>"
    s = s.replace("\n", " ").strip()
    return s if len(s) <= _MAX_VALUE else s[:_MAX_VALUE - 1] + "…"


class ChangeLogStore(BaseSQLiteStore):
    """Append-only who-changed-what trail."""

    _checked_paths: set[str] = set()

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        if self.db_path in ChangeLogStore._checked_paths:
            return
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
        ChangeLogStore._checked_paths.add(self.db_path)

    # ── Write ───────────────────────────────────────────────────────────────

    def record(self, entity: str, record_key: str, action: str = ACTION_UPDATE,
               *, field: str = "", old=None, new=None, detail: str = "",
               username: str | None = None) -> None:
        """Append one change. Never raises.

        *username* defaults to the signed-in user for this thread; pass it
        explicitly only where the acting user is not the ambient one.
        """
        self.record_many([{
            "entity": entity, "record_key": record_key, "action": action,
            "field": field, "old": old, "new": new, "detail": detail,
        }], username=username)

    def record_many(self, changes: list[dict], *,
                    username: str | None = None) -> None:
        """Append several changes in one transaction. Never raises.

        Each dict: entity, record_key, and optionally action/field/old/new/
        detail. One save that touches five fields becomes five rows sharing a
        timestamp, which is what makes "show me that edit" readable.
        """
        if not changes:
            return
        try:
            who = current_user() if username is None else (username or "")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for c in changes:
                action = c.get("action", ACTION_UPDATE)
                rows.append((
                    now, who, str(c.get("entity", "")),
                    _clip(c.get("record_key", "")),
                    action if action in ACTIONS else ACTION_UPDATE,
                    _clip(c.get("field", "")),
                    _clip(c.get("old")), _clip(c.get("new")),
                    _clip(c.get("detail", "")),
                ))
            with self._conn() as conn:
                conn.executemany(
                    "INSERT INTO change_log (ts, username, entity, record_key, "
                    "action, field, old_value, new_value, detail) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", rows)
        except Exception:
            pass          # auditing must never break the write it describes

    # ── Read ────────────────────────────────────────────────────────────────

    def list_recent(self, limit: int = 500, *, username: str | None = None,
                    entity: str | None = None,
                    record_key: str | None = None,
                    since: str | None = None) -> pd.DataFrame:
        """Recent changes, newest first, with optional filters."""
        cols = ["id", "ts", "username", "entity", "record_key", "action",
                "field", "old_value", "new_value", "detail"]
        where, params = [], []
        if username:
            where.append("LOWER(username) LIKE ?")
            params.append(f"%{username.strip().lower()}%")
        if entity:
            where.append("entity = ?")
            params.append(entity)
        if record_key:
            where.append("LOWER(record_key) LIKE ?")
            params.append(f"%{record_key.strip().lower()}%")
        if since:
            where.append("ts >= ?")
            params.append(since)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {', '.join(cols)} FROM change_log{clause} "
                f"ORDER BY id DESC LIMIT ?", (*params, int(limit)),
            ).fetchall()
        return (pd.DataFrame([dict(r) for r in rows], columns=cols)
                if rows else pd.DataFrame(columns=cols))

    def entities(self) -> list[str]:
        """Entities actually present, for the admin filter."""
        with self._conn() as conn:
            return [r[0] for r in conn.execute(
                "SELECT DISTINCT entity FROM change_log ORDER BY entity")]

    def users(self) -> list[str]:
        """Users who have made a recorded change."""
        with self._conn() as conn:
            return [r[0] for r in conn.execute(
                "SELECT DISTINCT username FROM change_log "
                "WHERE username != '' ORDER BY username")]

    def counts(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
            users = conn.execute(
                "SELECT COUNT(DISTINCT username) FROM change_log "
                "WHERE username != ''").fetchone()[0]
            today = conn.execute(
                "SELECT COUNT(*) FROM change_log WHERE ts >= ?",
                (datetime.now().strftime("%Y-%m-%d 00:00:00"),)).fetchone()[0]
        return {"total": total, "users": users, "today": today}

    # ── Maintenance ─────────────────────────────────────────────────────────

    def purge_older_than(self, days: int) -> int:
        """Delete entries older than *days*. Returns rows removed."""
        if days <= 0:
            return 0
        cutoff = (datetime.now() - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM change_log WHERE ts < ?", (cutoff,))
        return cur.rowcount
