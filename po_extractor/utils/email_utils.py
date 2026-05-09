"""SMTP helper for sending generated buy plan / 核料 files to users.

Settings come from :pymod:`auth.smtp_settings`, which loads from
``auth/smtp_settings.json`` (admin-editable in the UI) and falls back to
``PO_SMTP_*`` env vars when no file is present.

Public API
----------
is_email_configured() -> bool
    Quick check used by the UI to enable/disable the "Send" button.

send_email_with_attachments(to, subject, body, attachments) -> None
    Synchronous send. Attachments are ``(filename, bytes, mime)`` tuples.
    Raises :class:`EmailError` on any failure (auth, network, no config).

send_test_email(to) -> None
    Sends a tiny diagnostic message. Used by the Admin → Email "Test" button.
"""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable

from auth import smtp_settings as _smtp


class EmailError(RuntimeError):
    """Raised when an email cannot be sent (config, auth, or network)."""


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match((addr or "").strip()))


def is_email_configured() -> bool:
    """True when at minimum SMTP host + sender are set."""
    return _smtp.is_configured()


def _send(msg: EmailMessage, settings: _smtp.SmtpSettings) -> None:
    host, port, user, pw = settings["host"], settings["port"], settings["user"], settings["password"]
    # Port 465 always means implicit SSL (SMTP_SSL); other ports use STARTTLS when use_tls=True.
    use_ssl = (port == 465)
    try:
        ctx = ssl.create_default_context()
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
                if user:
                    s.login(user, pw)
                s.send_message(msg)
        elif settings["use_tls"]:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=ctx)
                if user:
                    s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                if user:
                    s.login(user, pw)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise EmailError(f"SMTP authentication failed: {e}") from e
    except smtplib.SMTPException as e:
        raise EmailError(f"SMTP error: {e}") from e
    except (OSError, TimeoutError) as e:
        raise EmailError(f"Network error reaching {host}:{port} — {e}") from e


def _build_message(to_list: list[str], subject: str, body: str,
                   attachments: Iterable[tuple[str, bytes, str]],
                   settings: _smtp.SmtpSettings) -> EmailMessage:
    msg = EmailMessage()
    msg["From"]    = _smtp.effective_sender(settings)
    msg["To"]      = ", ".join(to_list)
    msg["Subject"] = subject
    msg.set_content(body)
    for fname, data, mime in attachments:
        if not data:
            continue
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(
            data, maintype=maintype or "application", subtype=subtype or "octet-stream",
            filename=fname,
        )
    return msg


def _validated_recipients(to: str | Iterable[str]) -> list[str]:
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [r.strip() for r in recipients if r and r.strip()]
    if not recipients:
        raise EmailError("No recipient address provided.")
    bad = [r for r in recipients if not is_valid_email(r)]
    if bad:
        raise EmailError(f"Invalid email address(es): {', '.join(bad)}")
    return recipients


def send_email_with_attachments(
    to: str | Iterable[str],
    subject: str,
    body: str,
    attachments: Iterable[tuple[str, bytes, str]] = (),
) -> None:
    """Send a multipart message. ``attachments`` items are (filename, bytes, mime)."""
    settings = _smtp.load()
    if not (settings["host"] and _smtp.effective_sender(settings)):
        raise EmailError(
            "SMTP is not configured. Open Admin → Email and fill in host, "
            "user, password, and sender."
        )
    recipients = _validated_recipients(to)
    msg = _build_message(recipients, subject, body, attachments, settings)
    _send(msg, settings)


def send_test_email(to: str) -> None:
    """Send a tiny diagnostic message — used by the Admin → Email Test button."""
    settings = _smtp.load()
    if not (settings["host"] and _smtp.effective_sender(settings)):
        raise EmailError("SMTP is not configured yet — fill in the form first.")
    recipients = _validated_recipients(to)
    msg = _build_message(
        recipients,
        "PO Extractor — SMTP test",
        "This is a test message from PO Extractor. If you can read this, "
        "your SMTP settings are working.\n",
        attachments=(),
        settings=settings,
    )
    _send(msg, settings)
