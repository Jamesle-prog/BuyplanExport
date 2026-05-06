"""SMTP helper for sending generated buy plan / 核料 files to users.

Configuration is read from :pymod:`po_extractor.config` which sources values
from environment variables (PO_SMTP_HOST, PO_SMTP_PORT, PO_SMTP_USER,
PO_SMTP_PASSWORD, PO_SMTP_FROM, PO_SMTP_USE_TLS). Streamlit's
``.streamlit/secrets.toml`` can also be used by exporting from ``st.secrets``
into ``os.environ`` at startup.

Public API
----------
is_email_configured() -> bool
    Quick check used by the UI to enable/disable the "Send" button.

send_email_with_attachments(to, subject, body, attachments) -> None
    Synchronous send. Attachments are ``(filename, bytes, mime)`` tuples.
    Raises :class:`EmailError` on any failure (auth, network, no config).
"""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable

from .. import config as _cfg


class EmailError(RuntimeError):
    """Raised when an email cannot be sent (config, auth, or network)."""


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match((addr or "").strip()))


def is_email_configured() -> bool:
    """True when at minimum SMTP host + sender are set."""
    return bool(_cfg.SMTP_HOST and (_cfg.SMTP_FROM or _cfg.SMTP_USER))


def send_email_with_attachments(
    to: str | Iterable[str],
    subject: str,
    body: str,
    attachments: Iterable[tuple[str, bytes, str]] = (),
) -> None:
    """Send a multipart message. ``attachments`` items are (filename, bytes, mime)."""
    if not is_email_configured():
        raise EmailError(
            "SMTP is not configured. Set PO_SMTP_HOST, PO_SMTP_USER, "
            "PO_SMTP_PASSWORD (and optionally PO_SMTP_FROM, PO_SMTP_PORT) "
            "in the environment."
        )
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [r.strip() for r in recipients if r and r.strip()]
    if not recipients:
        raise EmailError("No recipient address provided.")
    bad = [r for r in recipients if not is_valid_email(r)]
    if bad:
        raise EmailError(f"Invalid email address(es): {', '.join(bad)}")

    msg = EmailMessage()
    msg["From"]    = _cfg.SMTP_FROM or _cfg.SMTP_USER
    msg["To"]      = ", ".join(recipients)
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

    try:
        if _cfg.SMTP_USE_TLS:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(_cfg.SMTP_HOST, _cfg.SMTP_PORT, timeout=30) as s:
                s.starttls(context=ctx)
                if _cfg.SMTP_USER:
                    s.login(_cfg.SMTP_USER, _cfg.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(_cfg.SMTP_HOST, _cfg.SMTP_PORT, timeout=30) as s:
                if _cfg.SMTP_USER:
                    s.login(_cfg.SMTP_USER, _cfg.SMTP_PASSWORD)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise EmailError(f"SMTP authentication failed: {e}") from e
    except smtplib.SMTPException as e:
        raise EmailError(f"SMTP error: {e}") from e
    except (OSError, TimeoutError) as e:
        raise EmailError(f"Network error reaching {_cfg.SMTP_HOST}:{_cfg.SMTP_PORT} — {e}") from e
