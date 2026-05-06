"""SMTP server configuration — persisted to auth/smtp_settings.json.

Admin-editable from the Admin → Email tab. Falls back to PO_SMTP_* env vars
when no JSON file exists, which keeps existing deployments working without
a UI round-trip.

The file is excluded from git (see .gitignore) because it contains the
SMTP password in plain text. For production, prefer a real secrets store.
"""
from __future__ import annotations

import json
import os
from typing import TypedDict

_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "smtp_settings.json")


class SmtpSettings(TypedDict):
    host:     str
    port:     int
    user:     str
    password: str
    sender:   str       # "From" address (defaults to user when empty)
    use_tls:  bool


_DEFAULTS: SmtpSettings = {
    "host":     "",
    "port":     587,
    "user":     "",
    "password": "",
    "sender":   "",
    "use_tls":  True,
}


def _coerce(d: dict) -> SmtpSettings:
    out: SmtpSettings = dict(_DEFAULTS)  # type: ignore[assignment]
    out["host"]     = str(d.get("host", "") or "").strip()
    out["user"]     = str(d.get("user", "") or "").strip()
    out["password"] = str(d.get("password", "") or "")
    out["sender"]   = str(d.get("sender", "") or "").strip()
    try:
        out["port"] = int(d.get("port", 587) or 587)
    except (TypeError, ValueError):
        out["port"] = 587
    out["use_tls"] = bool(d.get("use_tls", True))
    return out


def _from_env() -> SmtpSettings:
    return _coerce({
        "host":     os.environ.get("PO_SMTP_HOST", ""),
        "port":     os.environ.get("PO_SMTP_PORT", "587"),
        "user":     os.environ.get("PO_SMTP_USER", ""),
        "password": os.environ.get("PO_SMTP_PASSWORD", ""),
        "sender":   os.environ.get("PO_SMTP_FROM", ""),
        "use_tls":  os.environ.get("PO_SMTP_USE_TLS", "1") not in ("0", "false", "False", ""),
    })


def load() -> SmtpSettings:
    """Read settings from JSON, falling back to env vars when the file is absent."""
    if not os.path.exists(_SETTINGS_FILE):
        return _from_env()
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return _coerce(json.load(f))
    except (OSError, json.JSONDecodeError):
        return _from_env()


def save(settings: SmtpSettings) -> None:
    """Persist settings to disk (admin only — caller must enforce)."""
    payload = _coerce(dict(settings))  # type: ignore[arg-type]
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def is_configured() -> bool:
    s = load()
    return bool(s["host"] and (s["sender"] or s["user"]))


def effective_sender(s: SmtpSettings | None = None) -> str:
    s = s or load()
    return s["sender"] or s["user"]
