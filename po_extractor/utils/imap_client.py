"""IMAP inbox reader — fetches messages and their spreadsheet attachments.

Stdlib only (``imaplib`` + ``email``), so no new dependency. Deliberately
read-mostly: it can mark a message seen, but never deletes or moves mail —
the mailbox stays the user's own record, and a mis-parse can always be
re-run against the original message.

Security note: this module does NOT decide what is trustworthy. It reports
each message's sender and attachments; the caller (see
``EmailInboxStore.ingest``) applies the allow-list from
``auth.imap_settings`` and holds everything for human review.
"""
from __future__ import annotations

import email
import imaplib
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

# Attachment types worth keeping — the inbound importers all read workbooks.
SPREADSHEET_EXTS = (".xlsx", ".xlsm", ".xls")

# Hard ceilings so one enormous mailbox/message can't stall the UI thread.
MAX_MESSAGES_PER_FETCH = 50
MAX_ATTACHMENT_BYTES = 40 * 1024 * 1024      # 40 MB


class ImapError(RuntimeError):
    """Raised for connection/login/protocol problems, with a readable message."""


def _decode(value) -> str:
    """Decode a possibly RFC2047-encoded header to plain text."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(str(value))))
    except Exception:
        return str(value)


def _connect(settings: dict):
    host = (settings.get("host") or "").strip()
    user = (settings.get("user") or "").strip()
    if not host or not user:
        raise ImapError("IMAP is not configured (host and username are required).")
    port = int(settings.get("port") or 993)
    try:
        conn = (imaplib.IMAP4_SSL(host, port) if settings.get("use_ssl", True)
                else imaplib.IMAP4(host, port))
    except OSError as exc:
        raise ImapError(f"Could not reach {host}:{port} — {exc}") from exc
    try:
        conn.login(user, settings.get("password") or "")
    except imaplib.IMAP4.error as exc:
        try:
            conn.logout()
        except Exception:
            pass
        raise ImapError(
            f"Login failed for {user} — check the password. Gmail/Outlook "
            f"usually require an app password rather than the account one. ({exc})"
        ) from exc
    return conn


def test_connection(settings: dict) -> str:
    """Log in, count messages in the folder, log out. Returns a summary line.
    Raises :class:`ImapError` with a readable reason on failure."""
    conn = _connect(settings)
    try:
        folder = settings.get("folder") or "INBOX"
        status, data = conn.select(folder, readonly=True)
        if status != "OK":
            raise ImapError(f"Folder {folder!r} could not be opened.")
        total = int(data[0] or 0)
        status, unseen = conn.search(None, "UNSEEN")
        n_unseen = len(unseen[0].split()) if status == "OK" and unseen[0] else 0
        return f"Connected — {folder}: {total} message(s), {n_unseen} unread."
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def fetch_messages(settings: dict, *, unseen_only: bool = True,
                   limit: int = MAX_MESSAGES_PER_FETCH,
                   mark_seen: bool = False) -> list[dict]:
    """Return recent messages as dicts::

        {"uid": str, "from": str, "from_name": str, "subject": str,
         "date": str, "body": str,
         "attachments": [{"filename": str, "content": bytes, "size": int}]}

    Only spreadsheet attachments are kept (see :data:`SPREADSHEET_EXTS`);
    anything larger than :data:`MAX_ATTACHMENT_BYTES` is reported with
    ``content=b""`` so the UI can explain the skip instead of silently
    dropping it. Newest messages first.
    """
    conn = _connect(settings)
    out: list[dict] = []
    try:
        folder = settings.get("folder") or "INBOX"
        status, _ = conn.select(folder, readonly=not mark_seen)
        if status != "OK":
            raise ImapError(f"Folder {folder!r} could not be opened.")

        status, data = conn.search(None, "UNSEEN" if unseen_only else "ALL")
        if status != "OK":
            raise ImapError("Mailbox search failed.")
        ids = (data[0] or b"").split()
        ids = ids[-limit:][::-1]          # newest first, capped

        for mid in ids:
            # BODY.PEEK[] leaves \Seen alone; a plain RFC822 fetch would
            # silently mark every message read even in a "preview".
            item = "(RFC822)" if mark_seen else "(BODY.PEEK[])"
            status, raw = conn.fetch(mid, item)
            if status != "OK" or not raw or not isinstance(raw[0], tuple):
                continue
            msg = email.message_from_bytes(raw[0][1])

            name, addr = parseaddr(msg.get("From", ""))
            try:
                date_txt = parsedate_to_datetime(
                    msg.get("Date", "")).strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_txt = _decode(msg.get("Date", ""))

            body, attachments = "", []
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                filename = _decode(part.get_filename())
                disposition = (part.get("Content-Disposition") or "")
                if filename and filename.lower().endswith(SPREADSHEET_EXTS):
                    try:
                        payload = part.get_payload(decode=True) or b""
                    except Exception:
                        payload = b""
                    too_big = len(payload) > MAX_ATTACHMENT_BYTES
                    attachments.append({
                        "filename": filename,
                        "content": b"" if too_big else payload,
                        "size": len(payload),
                        "skipped_too_big": too_big,
                    })
                elif (part.get_content_type() == "text/plain"
                        and "attachment" not in disposition and not body):
                    try:
                        body = (part.get_payload(decode=True) or b"").decode(
                            part.get_content_charset() or "utf-8", "replace")
                    except Exception:
                        body = ""

            out.append({
                "uid": mid.decode() if isinstance(mid, bytes) else str(mid),
                "from": (addr or "").strip().lower(),
                "from_name": _decode(name),
                "subject": _decode(msg.get("Subject", "")),
                "date": date_txt,
                "body": body.strip(),
                "attachments": attachments,
            })
        return out
    finally:
        try:
            conn.logout()
        except Exception:
            pass
