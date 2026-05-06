"""Admin: SMTP configuration and test."""
from __future__ import annotations

import streamlit as st

from auth import smtp_settings
from auth.users import get_user_email
from po_extractor.utils.email_utils import EmailError, send_test_email

# Provider presets — host/port/tls auto-filled when a preset button is clicked.
_PROVIDERS: list[dict] = [
    {
        "label": "Outlook / Hotmail",
        "icon": "🔵",
        "host": "smtp-mail.outlook.com",
        "port": 587,
        "use_tls": True,
        "help": "Works for @outlook.com, @hotmail.com, @live.com accounts.\n"
                "Use your full email address as Username and your normal password.\n"
                "If 2FA is on, create an App Password at "
                "https://account.microsoft.com/security → Advanced Security → App Passwords.",
    },
    {
        "label": "Office 365 (work)",
        "icon": "🏢",
        "host": "smtp.office365.com",
        "port": 587,
        "use_tls": True,
        "help": "For corporate Microsoft 365 accounts (@yourdomain.com).\n"
                "SMTP AUTH must be enabled for the mailbox by your IT admin.\n"
                "Username = full email address.",
    },
    {
        "label": "Gmail",
        "icon": "🔴",
        "host": "smtp.gmail.com",
        "port": 587,
        "use_tls": True,
        "help": "Gmail requires an App Password — your normal password will not work.\n"
                "Go to https://myaccount.google.com/apppasswords, generate a password,\n"
                "paste it in the Password field below.",
    },
    {
        "label": "Custom",
        "icon": "⚙️",
        "host": None,   # don't overwrite
        "port": None,
        "use_tls": None,
        "help": "Enter your server details manually.",
    },
]

_SK_PRESET = "smtp_admin_preset"


def show_smtp_admin() -> None:
    st.subheader("📧 Email (SMTP) Settings")
    st.caption(
        "Configure the outgoing mail server. Settings are saved to "
        "`auth/smtp_settings.json` (excluded from git)."
    )

    # ── Provider quick-setup ──────────────────────────────────────────────────
    st.markdown("**Quick setup — choose your mail provider:**")
    pcols = st.columns(len(_PROVIDERS))
    for i, p in enumerate(_PROVIDERS):
        with pcols[i]:
            if st.button(
                f"{p['icon']} {p['label']}",
                key=f"smtp_preset_{i}",
                use_container_width=True,
                help=p["help"],
            ):
                st.session_state[_SK_PRESET] = i
                st.rerun()

    # Which preset is active?
    active_idx = st.session_state.get(_SK_PRESET)
    active = _PROVIDERS[active_idx] if active_idx is not None else None
    if active and active["label"] != "Custom":
        st.info(
            f"{active['icon']} **{active['label']}** selected — "
            f"`{active['host']}:{active['port']}` (STARTTLS). "
            f"{active['help']}",
            icon="ℹ️",
        )

    cur = smtp_settings.load()

    # Compute field defaults: preset overrides saved config for host/port/tls;
    # user/password/sender always come from saved config so editing isn't lost.
    def _host_default() -> str:
        if active and active["host"]:
            return active["host"]
        return cur["host"]

    def _port_default() -> int:
        if active and active["port"]:
            return int(active["port"])
        return int(cur["port"] or 587)

    def _tls_default() -> bool:
        if active and active["use_tls"] is not None:
            return bool(active["use_tls"])
        return cur["use_tls"]

    # ── Settings form ─────────────────────────────────────────────────────────
    st.markdown("**Server details:**")
    with st.form("smtp_form"):
        c1, c2 = st.columns([3, 1])
        with c1:
            host = st.text_input("SMTP Host", value=_host_default(),
                                 placeholder="smtp-mail.outlook.com")
        with c2:
            port = st.number_input("Port", min_value=1, max_value=65535,
                                   value=_port_default(), step=1)

        c3, c4 = st.columns(2)
        with c3:
            user = st.text_input(
                "Username (your email address)", value=cur["user"],
                placeholder="you@outlook.com",
            )
        with c4:
            password = st.text_input(
                "Password / App Password", value=cur["password"], type="password",
            )

        sender = st.text_input(
            "Sender name (optional)",
            value=cur["sender"],
            placeholder="PO Extractor <you@outlook.com>",
            help="How the From address appears. Defaults to Username when empty.",
        )
        use_tls = st.checkbox("Use STARTTLS (recommended)", value=_tls_default())

        saved = st.form_submit_button("💾 Save", type="primary",
                                      use_container_width=True)

    if saved:
        smtp_settings.save({
            "host": host, "port": int(port), "user": user,
            "password": password, "sender": sender, "use_tls": bool(use_tls),
        })
        # Clear preset so next open shows saved values, not preset overrides.
        st.session_state.pop(_SK_PRESET, None)
        st.success("✅ Saved.")
        st.rerun()

    # ── Test connection ───────────────────────────────────────────────────────
    st.divider()
    st.markdown("**Test connection**")
    if not smtp_settings.is_configured():
        st.info(
            "Fill in Host, Username (and Password), then click **Save** before testing.",
            icon="ℹ️",
        )
        return

    configured = smtp_settings.load()
    st.success(
        f"✅ Configured: `{configured['host']}:{configured['port']}` "
        f"as `{configured['user'] or configured['sender']}`",
    )

    default_to = get_user_email(st.session_state.username) or configured["user"]
    tcol1, tcol2 = st.columns([4, 1])
    with tcol1:
        to = st.text_input("Send test email to", value=default_to,
                           key="smtp_test_to", placeholder="you@example.com")
    with tcol2:
        st.write("")
        clicked = st.button("▶ Send test", use_container_width=True,
                            disabled=not to.strip(), key="smtp_test_btn")
    if clicked:
        try:
            with st.spinner(f"Connecting to {configured['host']}…"):
                send_test_email(to)
            st.success(f"✅ Test email delivered to **{to}**.")
        except EmailError as exc:
            st.error(f"❌ {exc}")
