"""Event notifications — "tell the right people something happened".

Five events are wired (chosen with the user):

    fabric_missing      a buy plan ran with fabric information missing
    buyplan_generated   a buy plan / 核料 pair was produced
    milestones_overdue  tracked milestones passed their planned date
    factory_data        a factory emailed in a spreadsheet
    fabric_pending      a fabric upload is waiting for peer review

Each event has its own recipient list, stored as JSON in app_settings under
``notify_subscribers``. An event with no subscribers simply does nothing —
notifications are opt-in per event, so turning one off is just emptying its
list.

Sending must never break the work that triggered it: :func:`notify` catches
everything and returns a status string instead of raising. A buy plan that
generated correctly should not fail because the mail server was down.
"""
from __future__ import annotations

import json

from .email_utils import EmailError, is_email_configured, send_email_with_attachments

EVENT_FABRIC_MISSING     = "fabric_missing"
EVENT_BUYPLAN_GENERATED  = "buyplan_generated"
EVENT_MILESTONES_OVERDUE = "milestones_overdue"
EVENT_FACTORY_DATA       = "factory_data"
EVENT_FABRIC_PENDING     = "fabric_pending"

EVENT_LABELS: dict[str, str] = {
    EVENT_FABRIC_MISSING:     "Missing fabric information",
    EVENT_BUYPLAN_GENERATED:  "Buy plan generated",
    EVENT_MILESTONES_OVERDUE: "Milestones overdue",
    EVENT_FACTORY_DATA:       "Factory data received",
    EVENT_FABRIC_PENDING:     "Fabric list pending approval",
}

EVENTS: tuple[str, ...] = tuple(EVENT_LABELS)

SETTINGS_KEY = "notify_subscribers"


# ── Subscriptions ───────────────────────────────────────────────────────────

def load_subscribers() -> dict[str, list[str]]:
    """Recipient lists per event, always with every event key present."""
    from ..store import get_app_settings_store
    out: dict[str, list[str]] = {e: [] for e in EVENTS}
    try:
        raw = get_app_settings_store().get(SETTINGS_KEY, "") or ""
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError, OSError):
        return out
    if not isinstance(data, dict):
        return out
    for event in EVENTS:
        vals = data.get(event) or []
        if isinstance(vals, str):
            vals = [p for chunk in vals.splitlines() for p in chunk.split(",")]
        out[event] = sorted({str(v).strip() for v in vals if str(v).strip()})
    return out


def save_subscribers(subs: dict[str, list[str]], *, updated_by: str = "") -> None:
    """Persist recipient lists (unknown events are dropped)."""
    from ..store import get_app_settings_store
    clean = {
        event: sorted({str(v).strip() for v in (subs.get(event) or [])
                       if str(v).strip()})
        for event in EVENTS
    }
    get_app_settings_store().set(
        SETTINGS_KEY, json.dumps(clean, ensure_ascii=False),
        updated_by=updated_by,
    )


def recipients_for(event: str) -> list[str]:
    return load_subscribers().get(event, [])


# ── Sending ─────────────────────────────────────────────────────────────────

def _format_body(lines: list[str], footer: str = "") -> str:
    from ..config import APP_NAME
    body = "\n".join(f"  • {ln}" for ln in lines if str(ln).strip())
    tail = (footer or
            f"Sent automatically by {APP_NAME}. Reply to this address to "
            "reach the team — this mailbox is not monitored by a robot.")
    return f"{body}\n\n{tail}\n" if body else f"{tail}\n"


def notify(event: str, subject: str, lines: list[str], *,
           attachments=(), footer: str = "") -> str:
    """Email *event*'s subscribers. Returns a short status for logging/UI.

    Never raises — a notification failure must not take down the operation
    that triggered it.
    """
    if event not in EVENT_LABELS:
        return f"unknown event {event!r}"
    to = recipients_for(event)
    if not to:
        return "no subscribers"
    if not is_email_configured():
        return "SMTP not configured"
    try:
        send_email_with_attachments(
            to, subject, _format_body(lines, footer), attachments)
    except EmailError as exc:
        return f"send failed: {exc}"
    except Exception as exc:                      # never propagate
        return f"send failed: {exc!r}"
    return f"sent to {len(to)} recipient(s)"


# ── Event-shaped convenience wrappers ───────────────────────────────────────

def _tag() -> str:
    from ..config import APP_NAME
    return f"[{APP_NAME}]"


def notify_buyplan_generated(client: str, pc_no: str, styles: int,
                             filenames: list[str] | None = None) -> str:
    return notify(
        EVENT_BUYPLAN_GENERATED,
        f"{_tag()} Buy plan generated — {client} {pc_no}".strip(),
        [f"Client: {client}", f"PC/PO: {pc_no}", f"Styles: {styles}"]
        + [f"File: {f}" for f in (filenames or [])],
    )


def notify_fabric_missing(client: str, pc_no: str, missing: list[str]) -> str:
    if not missing:
        return "nothing missing"
    return notify(
        EVENT_FABRIC_MISSING,
        f"{_tag()} Missing fabric information — {client} {pc_no}".strip(),
        [f"{len(missing)} item(s) could not be matched to the fabric master:"]
        + list(missing[:50]),
    )


def notify_milestones_overdue(rows: list[str]) -> str:
    if not rows:
        return "nothing overdue"
    return notify(
        EVENT_MILESTONES_OVERDUE,
        f"{_tag()} {len(rows)} milestone(s) overdue",
        rows[:100],
    )


def notify_factory_data(from_addr: str, filename: str, kind_label: str,
                        summary: str) -> str:
    return notify(
        EVENT_FACTORY_DATA,
        f"{_tag()} Factory data received — {filename}",
        [f"From: {from_addr}", f"Type: {kind_label}", f"Contents: {summary}",
         "Open the 📧 Email tab to review and apply it."],
    )


def notify_fabric_pending(uploaded_by: str, n_rows: int, note: str = "") -> str:
    return notify(
        EVENT_FABRIC_PENDING,
        f"{_tag()} Fabric list waiting for approval",
        [f"Uploaded by: {uploaded_by or 'unknown'}", f"Rows: {n_rows}"]
        + ([f"Note: {note}"] if note else [])
        + ["Open Fabric DB → Pending Review to approve or reject it."],
    )
