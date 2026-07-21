"""SQLite store for the inbound mail queue (📧 Email tab).

One row per received message plus one per spreadsheet attachment. Nothing
here changes business data: an attachment is stored with a status of
``pending`` and only a deliberate human action in the UI applies it, then
flips it to ``applied`` (or ``rejected`` / ``ignored``).

Security boundary (matches the design decision on record): messages from
addresses outside the allow-list are still LOGGED — so you can see that
someone mailed in and add them if legitimate — but their attachments are
stored with status ``blocked`` and can never be applied without first
whitelisting the sender.

De-duplication is by (uid, folder-agnostic) message id, so re-checking the
mailbox never queues the same file twice.
"""
from __future__ import annotations

from datetime import datetime

from .base_store import BaseSQLiteStore

STATUS_PENDING  = "pending"
STATUS_APPLIED  = "applied"
STATUS_REJECTED = "rejected"
STATUS_BLOCKED  = "blocked"     # sender not on the allow-list

_EMAIL_SCHEMA = """
CREATE TABLE IF NOT EXISTS email_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uid          TEXT NOT NULL,
    from_addr    TEXT NOT NULL DEFAULT '',
    from_name    TEXT NOT NULL DEFAULT '',
    subject      TEXT NOT NULL DEFAULT '',
    sent_at      TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL DEFAULT '',
    allowed      INTEGER NOT NULL DEFAULT 0,   -- sender passed the allow-list
    received_at  TEXT NOT NULL,
    UNIQUE (uid, from_addr, subject)
);

CREATE TABLE IF NOT EXISTS email_attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER NOT NULL,
    filename    TEXT NOT NULL DEFAULT '',
    size        INTEGER NOT NULL DEFAULT 0,
    kind        TEXT NOT NULL DEFAULT 'unknown',
    summary     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    note        TEXT NOT NULL DEFAULT '',
    content     BLOB,
    handled_at  TEXT,
    handled_by  TEXT
);
CREATE INDEX IF NOT EXISTS idx_ea_msg    ON email_attachments(message_id);
CREATE INDEX IF NOT EXISTS idx_ea_status ON email_attachments(status);
"""


class EmailInboxStore(BaseSQLiteStore):
    """Read/write access to the inbound mail queue."""

    _checked_paths: set[str] = set()

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if self.db_path in EmailInboxStore._checked_paths:
            return
        with self._conn() as conn:
            conn.executescript(_EMAIL_SCHEMA)
        EmailInboxStore._checked_paths.add(self.db_path)

    # ── Ingest ──────────────────────────────────────────────────────────────

    def ingest(self, messages: list[dict], *, is_allowed) -> dict:
        """Store fetched *messages*, classifying each attachment.

        *is_allowed* is a callable ``(from_addr) -> bool`` — the allow-list
        check is injected rather than imported so this store stays testable
        and the policy lives in one place (auth.imap_settings).

        Returns ``{"new_messages": n, "new_attachments": n, "blocked": n}``.
        Already-seen messages are skipped, so polling is idempotent.
        """
        from ..utils.inbound_router import detect_kind, summarise

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n_msg = n_att = n_blocked = 0

        with self._conn() as conn:
            for m in messages:
                uid = str(m.get("uid") or "")
                from_addr = (m.get("from") or "").strip().lower()
                subject = m.get("subject") or ""
                dup = conn.execute(
                    "SELECT id FROM email_messages "
                    "WHERE uid=? AND from_addr=? AND subject=?",
                    (uid, from_addr, subject),
                ).fetchone()
                if dup:
                    continue

                allowed = bool(is_allowed(from_addr))
                cur = conn.execute(
                    """INSERT INTO email_messages
                          (uid, from_addr, from_name, subject, sent_at, body,
                           allowed, received_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (uid, from_addr, m.get("from_name") or "", subject,
                     m.get("date") or "", (m.get("body") or "")[:4000],
                     int(allowed), now),
                )
                msg_id = int(cur.lastrowid)
                n_msg += 1

                for att in (m.get("attachments") or []):
                    content = att.get("content") or b""
                    if att.get("skipped_too_big"):
                        kind, summary, status = "unknown", "Attachment too large — skipped", STATUS_REJECTED
                    elif not allowed:
                        kind, summary, status = detect_kind(content), "", STATUS_BLOCKED
                        n_blocked += 1
                    else:
                        kind = detect_kind(content)
                        info = summarise(content, kind)
                        summary = info.get("summary") or ""
                        status = STATUS_PENDING
                    conn.execute(
                        """INSERT INTO email_attachments
                              (message_id, filename, size, kind, summary,
                               status, content)
                           VALUES (?,?,?,?,?,?,?)""",
                        (msg_id, att.get("filename") or "", int(att.get("size") or 0),
                         kind, summary, status, content),
                    )
                    n_att += 1

        return {"new_messages": n_msg, "new_attachments": n_att,
                "blocked": n_blocked}

    # ── Reads ───────────────────────────────────────────────────────────────

    def list_messages(self, limit: int = 100) -> list[dict]:
        """Messages newest first, each with its attachments (without blobs)."""
        with self._conn() as conn:
            msgs = [dict(r) for r in conn.execute(
                "SELECT * FROM email_messages ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()]
            if not msgs:
                return []
            ph = ",".join("?" * len(msgs))
            atts = [dict(r) for r in conn.execute(
                f"SELECT id, message_id, filename, size, kind, summary, status, "
                f"note, handled_at, handled_by FROM email_attachments "
                f"WHERE message_id IN ({ph}) ORDER BY id",
                [m["id"] for m in msgs],
            ).fetchall()]
        by_msg: dict[int, list] = {}
        for a in atts:
            by_msg.setdefault(a["message_id"], []).append(a)
        for m in msgs:
            m["attachments"] = by_msg.get(m["id"], [])
        return msgs

    def get_attachment(self, attachment_id: int) -> dict | None:
        """One attachment INCLUDING its bytes — for preview/apply."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM email_attachments WHERE id=?", (attachment_id,)
            ).fetchone()
        return dict(row) if row else None

    def count_pending(self) -> int:
        with self._conn() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM email_attachments WHERE status=?",
                (STATUS_PENDING,),
            ).fetchone()[0])

    # ── Writes ──────────────────────────────────────────────────────────────

    def set_status(self, attachment_id: int, status: str, *,
                   handled_by: str = "", note: str = "") -> None:
        """Record the outcome of a review decision."""
        if status not in (STATUS_PENDING, STATUS_APPLIED,
                          STATUS_REJECTED, STATUS_BLOCKED):
            raise ValueError(f"Unknown status {status!r}.")
        with self._conn() as conn:
            conn.execute(
                "UPDATE email_attachments SET status=?, note=?, handled_at=?, "
                "handled_by=? WHERE id=?",
                (status, note or "",
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 handled_by or "", attachment_id),
            )

    def unblock_sender(self, from_addr: str) -> int:
        """Move a newly-whitelisted sender's blocked attachments to pending
        so they can be reviewed without re-fetching the mailbox. Returns the
        number of attachments released."""
        from ..utils.inbound_router import detect_kind, summarise
        addr = (from_addr or "").strip().lower()
        with self._conn() as conn:
            conn.execute(
                "UPDATE email_messages SET allowed=1 WHERE from_addr=?", (addr,))
            rows = conn.execute(
                "SELECT a.id, a.content FROM email_attachments a "
                "JOIN email_messages m ON m.id = a.message_id "
                "WHERE m.from_addr=? AND a.status=?",
                (addr, STATUS_BLOCKED),
            ).fetchall()
            for r in rows:
                content = r["content"] or b""
                kind = detect_kind(content)
                info = summarise(content, kind)
                conn.execute(
                    "UPDATE email_attachments SET status=?, kind=?, summary=? "
                    "WHERE id=?",
                    (STATUS_PENDING, kind, info.get("summary") or "", r["id"]),
                )
        return len(rows)

    def delete_messages(self, ids: list[int]) -> int:
        """Remove queue rows (and their attachments). The mailbox itself is
        never touched — this only clears the in-app list."""
        if not ids:
            return 0
        ph = ",".join("?" * len(ids))
        with self._conn() as conn:
            conn.execute(
                f"DELETE FROM email_attachments WHERE message_id IN ({ph})", ids)
            cur = conn.execute(
                f"DELETE FROM email_messages WHERE id IN ({ph})", ids)
        return cur.rowcount
