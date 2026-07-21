"""IMAP (incoming mail) configuration — persisted to auth/imap_settings.json.

Mirrors auth/smtp_settings.py exactly: admin-editable from the Admin → Email
tab, falling back to PO_IMAP_* env vars when no JSON file exists.

Beyond the connection fields this also carries the **sender allow-list** —
the security boundary for inbound data. Only mail from a listed address (or
a listed domain, written ``@example.com``) is ever parsed; everything else
is recorded and ignored. A blank list means nothing is trusted, which is the
safe default for a mailbox that can change system data.

The file is excluded from git (see .gitignore) because it contains the
mailbox password in plain text. For production, prefer a real secrets store.
"""
from __future__ import annotations

import json
import os
from typing import TypedDict

_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "imap_settings.json")


class ImapSettings(TypedDict):
    host:            str
    port:            int
    user:            str
    password:        str
    folder:          str        # mailbox to read, usually INBOX
    use_ssl:         bool
    allowed_senders: list[str]  # exact addresses and/or "@domain" entries


_DEFAULTS: ImapSettings = {
    "host":            "",
    "port":            993,
    "user":            "",
    "password":        "",
    "folder":          "INBOX",
    "use_ssl":         True,
    "allowed_senders": [],
}


def _coerce(d: dict) -> ImapSettings:
    out: ImapSettings = dict(_DEFAULTS)  # type: ignore[assignment]
    out["host"]     = str(d.get("host", "") or "").strip()
    out["user"]     = str(d.get("user", "") or "").strip()
    out["password"] = str(d.get("password", "") or "")
    out["folder"]   = str(d.get("folder", "") or "INBOX").strip() or "INBOX"
    try:
        out["port"] = int(d.get("port", 993) or 993)
    except (TypeError, ValueError):
        out["port"] = 993
    out["use_ssl"] = bool(d.get("use_ssl", True))

    raw = d.get("allowed_senders", []) or []
    if isinstance(raw, str):        # tolerate a newline/comma separated blob
        raw = [p for chunk in raw.splitlines() for p in chunk.split(",")]
    out["allowed_senders"] = sorted({
        str(x).strip().lower() for x in raw if str(x).strip()
    })
    return out


def _from_env() -> ImapSettings:
    return _coerce({
        "host":     os.environ.get("PO_IMAP_HOST", ""),
        "port":     os.environ.get("PO_IMAP_PORT", "993"),
        "user":     os.environ.get("PO_IMAP_USER", ""),
        "password": os.environ.get("PO_IMAP_PASSWORD", ""),
        "folder":   os.environ.get("PO_IMAP_FOLDER", "INBOX"),
        "use_ssl":  os.environ.get("PO_IMAP_USE_SSL", "1")
                    not in ("0", "false", "False", ""),
        "allowed_senders": os.environ.get("PO_IMAP_ALLOWED", ""),
    })


def load() -> ImapSettings:
    """Settings from the JSON file, else from PO_IMAP_* env vars."""
    try:
        with open(_SETTINGS_FILE, encoding="utf-8") as fh:
            return _coerce(json.load(fh))
    except (OSError, json.JSONDecodeError):
        return _from_env()


def save(settings: dict) -> None:
    """Persist settings (coerced first)."""
    data = _coerce(settings)
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def is_configured() -> bool:
    s = load()
    return bool(s["host"] and s["user"])


def is_sender_allowed(from_addr: str, settings: ImapSettings | None = None) -> bool:
    """True when *from_addr* matches the allow-list.

    Accepts an exact address (``angel@factory.com``) or a whole domain
    entry written with a leading ``@`` (``@factory.com``). An EMPTY list
    trusts nobody — inbound data must be opted into deliberately, never by
    forgetting to configure it.
    """
    s = settings or load()
    allowed = s.get("allowed_senders") or []
    if not allowed:
        return False
    addr = (from_addr or "").strip().lower()
    if not addr or "@" not in addr:
        return False
    domain = "@" + addr.rsplit("@", 1)[1]
    return addr in allowed or domain in allowed
