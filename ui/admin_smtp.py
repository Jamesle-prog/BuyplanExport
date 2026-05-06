"""Admin: SMTP configuration and test."""
from __future__ import annotations

import streamlit as st

from auth import smtp_settings
from auth.users import get_user_email
from po_extractor.utils.email_utils import EmailError, send_test_email


def show_smtp_admin() -> None:
    st.subheader("📧 Email (SMTP) Settings")
    st.caption(
        "Configure the outgoing mail server used to send generated buy plan / "
        "核料 files. Settings persist to `auth/smtp_settings.json` (excluded "
        "from git). Per-user recipient addresses live on the Users tab."
    )

    cur = smtp_settings.load()

    with st.form("smtp_form"):
        c1, c2 = st.columns([3, 1])
        with c1:
            host = st.text_input("SMTP Host", value=cur["host"],
                                 placeholder="smtp.gmail.com")
        with c2:
            port = st.number_input("Port", min_value=1, max_value=65535,
                                   value=int(cur["port"] or 587), step=1)

        c3, c4 = st.columns(2)
        with c3:
            user = st.text_input("Username", value=cur["user"],
                                 placeholder="no-reply@example.com")
        with c4:
            password = st.text_input(
                "Password", value=cur["password"], type="password",
                help="For Gmail use an App Password "
                     "(https://myaccount.google.com/apppasswords).",
            )

        sender = st.text_input(
            "Sender (From address)", value=cur["sender"],
            placeholder='PO Extractor <no-reply@example.com>',
            help="Defaults to the Username when empty.",
        )
        use_tls = st.checkbox("Use STARTTLS (recommended)", value=cur["use_tls"])

        saved = st.form_submit_button("💾 Save", type="primary")

    if saved:
        smtp_settings.save({
            "host": host, "port": int(port), "user": user,
            "password": password, "sender": sender, "use_tls": bool(use_tls),
        })
        st.success("Saved.")
        st.rerun()

    st.divider()
    st.markdown("**Test connection**")
    if not smtp_settings.is_configured():
        st.info("Fill in Host + (Sender or Username) and Save before testing.", icon="ℹ️")
        return

    default_to = get_user_email(st.session_state.username) or cur["user"]
    tcol1, tcol2 = st.columns([4, 1])
    with tcol1:
        to = st.text_input("Send test to", value=default_to,
                           key="smtp_test_to",
                           placeholder="you@example.com")
    with tcol2:
        st.write("")
        clicked = st.button("Send test", use_container_width=True,
                            disabled=not to.strip(), key="smtp_test_btn")
    if clicked:
        try:
            with st.spinner(f"Sending test to {to}…"):
                send_test_email(to)
            st.success(f"Test message sent to {to}.")
        except EmailError as exc:
            st.error(f"Test failed: {exc}")
