"""📧 Email — inbound review, outbound compose, and notification settings.

Three things live here:

**Inbox** — check the mailbox, see what arrived, and apply a spreadsheet
into the system. Nothing is applied automatically: every attachment waits
for a person to read the preview and press Apply. Mail from an address that
isn't on the allow-list is still listed (so you can see it came in) but its
attachments are locked until the sender is added.

**Compose** — a plain send box for ad-hoc mail with an attachment, using the
SMTP settings already configured in Admin → Email.

**Notifications** — who gets told about which of the five system events.

The mailbox is checked on a button press and once when the tab first opens
in a session; there is no background poller, so a slow or unreachable mail
server can never stall the rest of the app.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from ui.i18n import t
from ui.session_keys import SK
from ui.shared import lazy_sections, fragment_rerun, XLSX_MIME
from ui.stores import get_email_inbox_store

from po_extractor.store.email_inbox_store import (
    STATUS_APPLIED, STATUS_BLOCKED, STATUS_PENDING, STATUS_REJECTED,
)
from po_extractor.utils.inbound_router import KIND_LABELS, KIND_FABRIC_LIST
from po_extractor.utils import notifications as notif

_STATUS_BADGE = {
    STATUS_PENDING:  "🟡",
    STATUS_APPLIED:  "✅",
    STATUS_REJECTED: "🚫",
    STATUS_BLOCKED:  "🔒",
}


# ─────────────────────────────────────────────────────────────────────────────
# Mailbox check
# ─────────────────────────────────────────────────────────────────────────────

def _check_mailbox(*, unseen_only: bool = True) -> str:
    """Fetch → ingest → notify. Returns a one-line result for the UI."""
    from auth import imap_settings as _imap
    from po_extractor.utils.imap_client import ImapError, fetch_messages

    settings = _imap.load()
    if not _imap.is_configured():
        return t("IMAP is not configured — open Mailbox settings below.")
    try:
        messages = fetch_messages(settings, unseen_only=unseen_only)
    except ImapError as exc:
        return f"❌ {exc}"
    except Exception as exc:                     # never break the tab
        return f"❌ {exc!r}"

    res = get_email_inbox_store().ingest(
        messages, is_allowed=lambda a: _imap.is_sender_allowed(a, settings))
    st.session_state[SK.EMAIL_LAST_FETCH] = datetime.now().strftime("%H:%M:%S")

    if res["new_attachments"]:
        # One notification per new file, so the summary line says what arrived.
        for msg in get_email_inbox_store().list_messages(limit=20):
            for att in msg["attachments"]:
                if att["status"] == STATUS_PENDING and not att["handled_at"]:
                    notif.notify_factory_data(
                        msg["from_addr"], att["filename"],
                        KIND_LABELS.get(att["kind"], att["kind"]),
                        att["summary"] or "—")
    parts = [f"{res['new_messages']} " + t("new message(s)")]
    if res["new_attachments"]:
        parts.append(f"{res['new_attachments']} " + t("attachment(s)"))
    if res["blocked"]:
        parts.append(f"🔒 {res['blocked']} " + t("from unlisted sender(s)"))
    return "✅ " + ", ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Inbox
# ─────────────────────────────────────────────────────────────────────────────

def _render_attachment(att: dict, msg: dict, username: str) -> None:
    store = get_email_inbox_store()
    badge = _STATUS_BADGE.get(att["status"], "•")
    kind_label = KIND_LABELS.get(att["kind"], att["kind"])
    st.markdown(
        f"{badge} **{att['filename']}** — {kind_label}"
        + (f" · {att['summary']}" if att["summary"] else "")
    )

    if att["status"] == STATUS_BLOCKED:
        st.caption("🔒 " + t(
            "Sender is not on the allow-list, so this file cannot be applied. "
            "Add the address in Mailbox settings to unlock it."))
        return
    if att["status"] != STATUS_PENDING:
        who = att["handled_by"] or "—"
        st.caption(f"{att['status']} · {att['handled_at'] or ''} · {who}"
                   + (f" · {att['note']}" if att["note"] else ""))
        return

    if att["kind"] == KIND_FABRIC_LIST:
        st.info(t("Fabric lists are not applied from email — upload the file "
                  "in 🧵 Fabric DB so it goes through the approval queue."))

    c1, c2, c3 = st.columns([2, 1, 3])
    can_apply = att["kind"] != KIND_FABRIC_LIST and att["kind"] != "unknown"
    with c1:
        if st.button(f"✅ {t('Apply')}", key=f"em_apply_{att['id']}",
                     type="primary", disabled=not can_apply):
            from po_extractor.utils.inbound_apply import apply_attachment
            full = store.get_attachment(att["id"]) or {}
            res = apply_attachment(
                full.get("content") or b"", att["kind"],
                username=username, factory=msg.get("from_name") or "",
            )
            note = "; ".join(res["messages"][:5])
            if res["ok"]:
                store.set_status(att["id"], STATUS_APPLIED,
                                 handled_by=username, note=note)
                st.success(f"✅ {res['applied']} {t('change(s) applied')}"
                           + (f", {res['skipped']} {t('skipped')}"
                              if res["skipped"] else ""))
            else:
                st.error(note or t("Could not apply this file."))
            for m in res["messages"]:
                st.caption(f"• {m}")
            if res["ok"]:
                fragment_rerun()
    with c2:
        if st.button(f"🚫 {t('Reject')}", key=f"em_rej_{att['id']}"):
            store.set_status(att["id"], STATUS_REJECTED, handled_by=username)
            fragment_rerun()
    with c3:
        full = store.get_attachment(att["id"]) or {}
        st.download_button(
            f"⬇️ {t('Download')}", data=full.get("content") or b"",
            file_name=att["filename"] or "attachment.xlsx",
            mime=XLSX_MIME,
            key=f"em_dl_{att['id']}",
        )


def _render_inbox(username: str) -> None:
    store = get_email_inbox_store()

    c1, c2, c3 = st.columns([2, 2, 4])
    with c1:
        if st.button(f"📥 {t('Check mail now')}", type="primary",
                     key="em_check_btn"):
            st.session_state[SK.EMAIL_FETCH_FLASH] = _check_mailbox()
            fragment_rerun()
    with c2:
        if st.button(f"🔄 {t('Re-read all mail')}", key="em_check_all",
                     help=t("Includes messages already marked read — use this "
                            "if something was opened elsewhere first.")):
            st.session_state[SK.EMAIL_FETCH_FLASH] = _check_mailbox(
                unseen_only=False)
            fragment_rerun()
    with c3:
        last = st.session_state.get(SK.EMAIL_LAST_FETCH)
        if last:
            st.caption(f"{t('Last checked')}: {last}")

    flash = st.session_state.pop(SK.EMAIL_FETCH_FLASH, "")
    if flash:
        (st.error if flash.startswith("❌") else st.info)(flash)

    messages = store.list_messages(limit=100)
    if not messages:
        st.info(t("Nothing received yet. Press “Check mail now”, or configure "
                  "the mailbox below if this is the first run."))
        return

    n_pending = store.count_pending()
    if n_pending:
        st.warning(f"🟡 {n_pending} " + t("attachment(s) waiting for review."))

    for msg in messages:
        atts = msg["attachments"]
        lock = "" if msg["allowed"] else " 🔒"
        title = (f"{msg['sent_at'] or msg['received_at']} · "
                 f"{msg['from_name'] or msg['from_addr']}{lock} — "
                 f"{msg['subject'] or t('(no subject)')}"
                 + (f"  ({len(atts)} 📎)" if atts else ""))
        has_pending = any(a["status"] == STATUS_PENDING for a in atts)
        with st.expander(title, expanded=has_pending):
            st.caption(msg["from_addr"])
            if msg["body"]:
                st.text(msg["body"][:1500])
            if not atts:
                st.caption(t("No spreadsheet attachments."))
            for att in atts:
                _render_attachment(att, msg, username)
                st.divider()
            if st.button(f"🗑 {t('Remove from list')}",
                         key=f"em_delmsg_{msg['id']}",
                         help=t("Clears it from this list only — the message "
                                "stays in the mailbox.")):
                store.delete_messages([msg["id"]])
                fragment_rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Compose
# ─────────────────────────────────────────────────────────────────────────────

def _render_compose() -> None:
    from po_extractor.utils.email_utils import (
        EmailError, is_email_configured, send_email_with_attachments,
    )

    if not is_email_configured():
        st.warning(t("SMTP is not configured — open Admin → Email to set it up."))
        return

    with st.form("em_compose_form"):
        to = st.text_input(t("To (comma-separated)"), key="em_to")
        subject = st.text_input(t("Subject"), key="em_subject")
        body = st.text_area(t("Message"), height=180, key="em_body")
        files = st.file_uploader(t("Attachments"), accept_multiple_files=True,
                                 key="em_files")
        sent = st.form_submit_button(f"📤 {t('Send')}", type="primary")

    if sent:
        recipients = [a.strip() for a in (to or "").replace(";", ",").split(",")
                      if a.strip()]
        if not recipients:
            st.error(t("Enter at least one recipient."))
            return
        attachments = [
            (f.name, f.getvalue(), f.type or "application/octet-stream")
            for f in (files or [])
        ]
        try:
            send_email_with_attachments(recipients, subject or "(no subject)",
                                        body or "", attachments)
        except EmailError as exc:
            st.error(f"{t('Send failed:')} {exc}")
        else:
            st.success(f"✅ {t('Sent to')} {len(recipients)} "
                       + t("recipient(s)."))


# ─────────────────────────────────────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────────────────────────────────────

def _render_notifications(username: str) -> None:
    st.caption(t("Who gets an email when each of these happens. Leave a row "
                 "empty to switch that notification off."))
    subs = notif.load_subscribers()
    df = pd.DataFrame([
        {"Event": notif.EVENT_LABELS[e], "Recipients": ", ".join(subs[e])}
        for e in notif.EVENTS
    ])
    edited = st.data_editor(
        df, width="stretch", hide_index=True, key="em_notif_editor",
        disabled=["Event"],
        column_config={
            "Event": st.column_config.TextColumn(t("Event"), width="medium"),
            "Recipients": st.column_config.TextColumn(
                t("Recipients"), width="large",
                help=t("Comma-separated email addresses.")),
        },
    )
    if st.button(f"💾 {t('Save notification settings')}", type="primary",
                 key="em_notif_save"):
        new = {}
        for event, (_, row) in zip(notif.EVENTS, edited.iterrows()):
            raw = str(row["Recipients"] or "").replace(";", ",")
            new[event] = [a.strip() for a in raw.split(",") if a.strip()]
        notif.save_subscribers(new, updated_by=username)
        st.success(f"✅ {t('Saved.')}")
        fragment_rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Mailbox settings (admin)
# ─────────────────────────────────────────────────────────────────────────────

def _render_mailbox_settings() -> None:
    from auth import imap_settings as _imap
    from po_extractor.utils.imap_client import ImapError, test_connection

    s = _imap.load()
    st.caption(t("The mailbox the system reads. Gmail and Outlook need an "
                 "app password rather than the account password."))
    with st.form("em_imap_form"):
        c1, c2 = st.columns([3, 1])
        host = c1.text_input(t("IMAP host"), value=s["host"], key="em_imap_host")
        port = c2.number_input(t("Port"), value=int(s["port"]), min_value=1,
                               max_value=65535, key="em_imap_port")
        user = st.text_input(t("Username"), value=s["user"], key="em_imap_user")
        # Never pre-fill the stored secret — value= pushes the plaintext over
        # the websocket into the browser DOM on every render (type="password"
        # only masks it visually). Blank keeps the current password on save —
        # the same pattern admin_smtp uses.
        pw = st.text_input(
            t("Password"), value="", type="password", key="em_imap_pw",
            placeholder=(t("•••••• (saved — leave blank to keep)")
                         if s["password"] else ""))
        c3, c4 = st.columns(2)
        folder = c3.text_input(t("Folder"), value=s["folder"],
                               key="em_imap_folder")
        use_ssl = c4.checkbox(t("Use SSL"), value=bool(s["use_ssl"]),
                              key="em_imap_ssl")
        allowed = st.text_area(
            t("Allowed senders — one per line"),
            value="\n".join(s["allowed_senders"]), height=120,
            key="em_imap_allowed",
            help=t("An exact address (angel@factory.com) or a whole domain "
                   "written @factory.com. Empty means nothing is trusted."),
        )
        c5, c6 = st.columns(2)
        saved = c5.form_submit_button(f"💾 {t('Save')}", type="primary")
        tested = c6.form_submit_button(f"🔌 {t('Test connection')}")

    payload = {
        "host": host, "port": port, "user": user,
        # Blank password field = keep the stored secret (field is never
        # pre-filled with it).
        "password": pw or s["password"],
        "folder": folder, "use_ssl": use_ssl, "allowed_senders": allowed,
    }
    if saved:
        before = set(s["allowed_senders"])
        _imap.save(payload)
        after = set(_imap.load()["allowed_senders"])
        st.success(f"✅ {t('Mailbox settings saved.')}")
        # Newly-trusted senders: release anything of theirs already sitting
        # in the queue, so adding an address doesn't mean re-fetching mail.
        released = 0
        for addr in after - before:
            if not addr.startswith("@"):
                released += get_email_inbox_store().unblock_sender(addr)
        if released:
            st.info(f"🔓 {released} " + t("previously blocked attachment(s) "
                                          "are now waiting for review."))
    if tested:
        try:
            st.success("✅ " + test_connection(payload))
        except ImapError as exc:
            st.error(f"❌ {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def show_email_tab(username: str = "", admin_mode: bool = False) -> None:
    st.subheader(f"📧 {t('Email')}")

    # One automatic check per session, so opening the tab shows current mail
    # without a background poller. A failure here is shown, never raised.
    if not st.session_state.get(SK.EMAIL_AUTO_CHECKED):
        st.session_state[SK.EMAIL_AUTO_CHECKED] = True
        from auth import imap_settings as _imap
        if _imap.is_configured():
            with st.spinner(t("Checking mailbox…")):
                st.session_state[SK.EMAIL_FETCH_FLASH] = _check_mailbox()

    sections = [
        (f"📥 {t('Inbox')}",         lambda: _render_inbox(username)),
        (f"✉️ {t('Compose')}",       _render_compose),
        (f"🔔 {t('Notifications')}", lambda: _render_notifications(username)),
    ]
    if admin_mode:
        sections.append((f"⚙️ {t('Mailbox')}", _render_mailbox_settings))
    lazy_sections(sections, key="email_section_nav")
