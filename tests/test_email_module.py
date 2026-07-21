"""Tests for the 📧 Email module: allow-list, inbox store, and routing.

The security-relevant behaviour (an unlisted sender's file must never be
appliable) is covered first and most heavily — everything else is a
convenience feature, that one is the boundary.
"""
from __future__ import annotations

import io
import os
import tempfile

import openpyxl
import pytest

from auth import imap_settings
from po_extractor.store.email_inbox_store import (
    EmailInboxStore, STATUS_APPLIED, STATUS_BLOCKED, STATUS_PENDING,
    STATUS_REJECTED,
)
from po_extractor.utils import inbound_router as router


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    return EmailInboxStore(str(tmp_path / "inbox.db"))


def _workbook(sheets: list[str], rows: dict | None = None) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name in sheets:
        ws = wb.create_sheet(title=name)
        for row in (rows or {}).get(name, []):
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _message(uid="1", frm="angel@factory.com", subject="Progress",
             attachments=None):
    return {
        "uid": uid, "from": frm, "from_name": "Angel", "subject": subject,
        "date": "2026-07-20 09:00", "body": "see attached",
        "attachments": attachments or [],
    }


def _attachment(name="report.xlsx", content=b"", **kw):
    return {"filename": name, "content": content, "size": len(content), **kw}


# ── Allow-list ──────────────────────────────────────────────────────────────

def test_empty_allowlist_trusts_nobody():
    s = dict(imap_settings._DEFAULTS, allowed_senders=[])
    assert imap_settings.is_sender_allowed("anyone@anywhere.com", s) is False


def test_exact_address_and_domain_entries():
    s = dict(imap_settings._DEFAULTS,
             allowed_senders=["angel@factory.com", "@trusted.cn"])
    assert imap_settings.is_sender_allowed("angel@factory.com", s)
    assert imap_settings.is_sender_allowed("ANGEL@Factory.com", s)
    assert imap_settings.is_sender_allowed("anyone@trusted.cn", s)
    assert not imap_settings.is_sender_allowed("angel@factory.com.evil.ru", s)
    assert not imap_settings.is_sender_allowed("other@factory.com", s)
    assert not imap_settings.is_sender_allowed("", s)
    assert not imap_settings.is_sender_allowed("not-an-address", s)


def test_coerce_accepts_a_pasted_blob():
    got = imap_settings._coerce({"allowed_senders": "a@x.com\nb@y.com, c@z.com"})
    assert got["allowed_senders"] == ["a@x.com", "b@y.com", "c@z.com"]


# ── Ingest ──────────────────────────────────────────────────────────────────

def test_unlisted_sender_attachment_is_blocked(store):
    content = _workbook(["Index"])
    res = store.ingest([_message(frm="stranger@nowhere.io",
                                attachments=[_attachment(content=content)])],
                       is_allowed=lambda a: False)
    assert res["blocked"] == 1
    msg = store.list_messages()[0]
    assert msg["allowed"] == 0
    assert msg["attachments"][0]["status"] == STATUS_BLOCKED
    # Blocked files are never counted as work waiting for a reviewer.
    assert store.count_pending() == 0


def test_allowed_sender_attachment_is_pending_with_a_summary(store):
    content = _workbook(["Index"])
    store.ingest([_message(attachments=[_attachment(content=content)])],
                 is_allowed=lambda a: True)
    att = store.list_messages()[0]["attachments"][0]
    assert att["status"] == STATUS_PENDING
    assert att["kind"] == router.KIND_BUYPLAN
    assert store.count_pending() == 1


def test_ingest_is_idempotent(store):
    msgs = [_message(attachments=[_attachment(content=_workbook(["Index"]))])]
    first = store.ingest(msgs, is_allowed=lambda a: True)
    second = store.ingest(msgs, is_allowed=lambda a: True)
    assert first["new_messages"] == 1
    assert second["new_messages"] == 0
    assert len(store.list_messages()) == 1


def test_oversized_attachment_is_recorded_not_dropped(store):
    store.ingest(
        [_message(attachments=[_attachment(content=b"", skipped_too_big=True,
                                           size=99_000_000)])],
        is_allowed=lambda a: True)
    att = store.list_messages()[0]["attachments"][0]
    assert att["status"] == STATUS_REJECTED
    assert "too large" in att["summary"].lower()


def test_whitelisting_a_sender_releases_their_blocked_files(store):
    store.ingest([_message(attachments=[_attachment(content=_workbook(["Index"]))])],
                 is_allowed=lambda a: False)
    released = store.unblock_sender("angel@factory.com")
    assert released == 1
    att = store.list_messages()[0]["attachments"][0]
    assert att["status"] == STATUS_PENDING
    assert att["kind"] == router.KIND_BUYPLAN
    assert store.count_pending() == 1


def test_set_status_records_who_and_when(store):
    store.ingest([_message(attachments=[_attachment(content=_workbook(["Index"]))])],
                 is_allowed=lambda a: True)
    att_id = store.list_messages()[0]["attachments"][0]["id"]
    store.set_status(att_id, STATUS_APPLIED, handled_by="mei", note="12 rows")
    att = store.list_messages()[0]["attachments"][0]
    assert (att["status"], att["handled_by"], att["note"]) == (
        STATUS_APPLIED, "mei", "12 rows")
    assert att["handled_at"]
    assert store.count_pending() == 0


def test_set_status_rejects_an_unknown_status(store):
    store.ingest([_message(attachments=[_attachment(content=b"x")])],
                 is_allowed=lambda a: True)
    att_id = store.list_messages()[0]["attachments"][0]["id"]
    with pytest.raises(ValueError):
        store.set_status(att_id, "whatever")


def test_delete_removes_message_and_attachments(store):
    store.ingest([_message(attachments=[_attachment(content=_workbook(["Index"]))])],
                 is_allowed=lambda a: True)
    mid = store.list_messages()[0]["id"]
    assert store.delete_messages([mid]) == 1
    assert store.list_messages() == []
    assert store.count_pending() == 0


def test_get_attachment_returns_the_bytes(store):
    content = _workbook(["Index"])
    store.ingest([_message(attachments=[_attachment(content=content)])],
                 is_allowed=lambda a: True)
    att_id = store.list_messages()[0]["attachments"][0]["id"]
    assert store.get_attachment(att_id)["content"] == content
    assert store.get_attachment(999_999) is None


# ── Routing ─────────────────────────────────────────────────────────────────

def test_detect_buyplan_by_index_sheet():
    assert router.detect_kind(_workbook(["Index", "AB123"])) == router.KIND_BUYPLAN


def test_detect_progress_form_by_sheet_name():
    assert router.detect_kind(
        _workbook(["进度回报表", "里程碑"])) == router.KIND_PROGRESS_FORM


def test_detect_fabric_list_by_all_sheet():
    assert router.detect_kind(_workbook(["ALL"])) == router.KIND_FABRIC_LIST


def test_detect_is_not_filename_based():
    """A file called anything at all still classifies by its contents."""
    assert router.detect_kind(_workbook(["Sheet1"])) == router.KIND_UNKNOWN


def test_detect_handles_garbage_without_raising():
    assert router.detect_kind(b"not a workbook") == router.KIND_UNKNOWN
    assert router.detect_kind(b"") == router.KIND_UNKNOWN


def test_summarise_never_raises_on_a_bad_file():
    out = router.summarise(b"corrupt", router.KIND_PROGRESS_FORM)
    assert out["ok"] is False
    assert isinstance(out["summary"], str)


# ── Notification subscriptions ──────────────────────────────────────────────

def test_subscribers_round_trip(monkeypatch, tmp_path):
    from po_extractor.store.app_settings_store import AppSettingsStore
    from po_extractor.utils import notifications as notif

    fake = AppSettingsStore(str(tmp_path / "settings.db"))
    monkeypatch.setattr("po_extractor.store.get_app_settings_store",
                        lambda: fake)

    assert notif.load_subscribers()[notif.EVENT_BUYPLAN_GENERATED] == []
    notif.save_subscribers({notif.EVENT_BUYPLAN_GENERATED:
                            ["a@x.com", " b@y.com ", ""]})
    subs = notif.load_subscribers()
    assert subs[notif.EVENT_BUYPLAN_GENERATED] == ["a@x.com", "b@y.com"]
    # Every event key is always present, so the UI never KeyErrors.
    assert set(subs) == set(notif.EVENTS)


def test_notify_with_no_subscribers_is_a_no_op(monkeypatch, tmp_path):
    from po_extractor.store.app_settings_store import AppSettingsStore
    from po_extractor.utils import notifications as notif

    fake = AppSettingsStore(str(tmp_path / "settings.db"))
    monkeypatch.setattr("po_extractor.store.get_app_settings_store",
                        lambda: fake)
    sent = []
    monkeypatch.setattr(notif, "send_email_with_attachments",
                        lambda *a, **k: sent.append(a))
    assert notif.notify(notif.EVENT_BUYPLAN_GENERATED, "s", ["x"]) == \
        "no subscribers"
    assert sent == []


def test_notify_swallows_send_failures(monkeypatch, tmp_path):
    """A buy plan that generated correctly must not fail because the mail
    server is down."""
    from po_extractor.store.app_settings_store import AppSettingsStore
    from po_extractor.utils import notifications as notif

    fake = AppSettingsStore(str(tmp_path / "settings.db"))
    monkeypatch.setattr("po_extractor.store.get_app_settings_store",
                        lambda: fake)
    notif.save_subscribers({notif.EVENT_BUYPLAN_GENERATED: ["a@x.com"]})
    monkeypatch.setattr(notif, "is_email_configured", lambda: True)

    def _boom(*a, **k):
        raise RuntimeError("smtp is on fire")
    monkeypatch.setattr(notif, "send_email_with_attachments", _boom)

    out = notif.notify(notif.EVENT_BUYPLAN_GENERATED, "s", ["x"])
    assert "send failed" in out


def test_notify_unknown_event_is_reported(tmp_path):
    from po_extractor.utils import notifications as notif
    assert "unknown event" in notif.notify("nope", "s", ["x"])


# ── Apply gate ──────────────────────────────────────────────────────────────

def test_fabric_list_is_never_applied_from_email():
    """Fabric data has its own two-person approval queue; arriving by email
    must not become a way around it."""
    from po_extractor.utils.inbound_apply import apply_attachment
    out = apply_attachment(_workbook(["ALL"]), router.KIND_FABRIC_LIST)
    assert out["ok"] is False
    assert out["applied"] == 0
    assert "Fabric DB" in " ".join(out["messages"])


def test_apply_unknown_kind_is_refused():
    from po_extractor.utils.inbound_apply import apply_attachment
    out = apply_attachment(b"x", router.KIND_UNKNOWN)
    assert out["ok"] is False and out["applied"] == 0


def test_apply_never_raises_on_a_corrupt_file():
    from po_extractor.utils.inbound_apply import apply_attachment
    out = apply_attachment(b"corrupt", router.KIND_PROGRESS_FORM)
    assert out["ok"] is False
    assert out["messages"]
