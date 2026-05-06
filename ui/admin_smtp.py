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
    },
    {
        "label": "Office 365 (work)",
        "icon": "🏢",
        "host": "smtp.office365.com",
        "port": 587,
        "use_tls": True,
    },
    {
        "label": "Gmail",
        "icon": "🔴",
        "host": "smtp.gmail.com",
        "port": 587,
        "use_tls": True,
    },
    {
        "label": "Custom",
        "icon": "⚙️",
        "host": None,
        "port": None,
        "use_tls": None,
    },
]

_SK_PRESET = "smtp_admin_preset"

# Error substrings → actionable fix guidance
_ERROR_HINTS: list[tuple[str, str]] = [
    (
        "535",  # SMTP 535 = auth failed
        "**Authentication failed.** Microsoft has disabled basic (password) login for "
        "Outlook/Hotmail SMTP. You must use an **App Password** instead:\n\n"
        "1. Go to 🔗 https://account.microsoft.com/security\n"
        "2. Click **Advanced security options**\n"
        "3. Under *App passwords* click **Create a new app password**\n"
        "4. Copy the generated password and paste it in the **Password** field above, then Save.\n\n"
        "Also ensure SMTP AUTH is enabled for your mailbox:\n"
        "https://outlook.live.com/mail/0/options/mail/accounts/popImap "
        "→ turn on *Let devices and apps use POP* and *SMTP AUTH*.",
    ),
    (
        "authentication unsuccessful",
        "**Authentication unsuccessful.** Use an App Password — your normal Microsoft "
        "account password will not work for SMTP.\n\n"
        "Generate one at: https://account.microsoft.com/security → "
        "Advanced security options → App passwords.",
    ),
    (
        "smtp auth extension not supported",
        "**SMTP AUTH is disabled** on this mailbox. For Office 365 work accounts, "
        "ask your IT admin to enable SMTP AUTH for your account in the Microsoft 365 admin centre.",
    ),
    (
        "username and password not accepted",
        "**Credentials rejected.** For Gmail, you must use an App Password:\n\n"
        "1. Enable 2-Step Verification at https://myaccount.google.com/security\n"
        "2. Then create an App Password at https://myaccount.google.com/apppasswords\n"
        "3. Use that 16-character password in the Password field.",
    ),
]


def _smtp_error_hint(exc: EmailError) -> str | None:
    msg = str(exc).lower()
    for keyword, hint in _ERROR_HINTS:
        if keyword.lower() in msg:
            return hint
    return None


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
            ):
                st.session_state[_SK_PRESET] = i
                st.rerun()

    active_idx = st.session_state.get(_SK_PRESET)
    active = _PROVIDERS[active_idx] if active_idx is not None else None

    # Show provider-specific instructions
    if active:
        label = active["label"]
        if label == "Outlook / Hotmail":
            st.info(
                "**🔵 Outlook / Hotmail setup**\n\n"
                "Microsoft has **disabled basic password login** for SMTP. "
                "You must use an **App Password**:\n\n"
                "1. Go to 🔗 https://account.microsoft.com/security\n"
                "2. Click **Advanced security options**\n"
                "3. Under *App passwords* → **Create a new app password**\n"
                "4. Paste the generated password below (not your normal password)\n\n"
                "Also enable SMTP in your Outlook settings:  \n"
                "https://outlook.live.com/mail/0/options/mail/accounts/popImap  \n"
                "→ Turn on **Let devices and apps use POP** and **SMTP AUTH**",
                icon="ℹ️",
            )
        elif label == "Office 365 (work)":
            st.info(
                "**🏢 Office 365 setup**\n\n"
                "- Use your full work email as Username\n"
                "- Password: your normal Microsoft 365 password (or App Password if MFA is on)\n"
                "- Your IT admin must have **SMTP AUTH enabled** for your mailbox in the "
                "Microsoft 365 admin centre",
                icon="ℹ️",
            )
        elif label == "Gmail":
            st.info(
                "**🔴 Gmail setup**\n\n"
                "Gmail requires an **App Password** — your normal password will not work:\n\n"
                "1. Enable 2-Step Verification: https://myaccount.google.com/security\n"
                "2. Create App Password: https://myaccount.google.com/apppasswords\n"
                "3. Paste the 16-character password in the Password field below",
                icon="ℹ️",
            )

    cur = smtp_settings.load()

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
            user = st.text_input("Username (your full email address)", value=cur["user"],
                                 placeholder="you@outlook.com")
        with c4:
            password = st.text_input(
                "App Password", value=cur["password"], type="password",
                help="Use an App Password generated from your account security settings, "
                     "not your regular login password.",
            )

        sender = st.text_input(
            "Sender name (optional)", value=cur["sender"],
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
        st.session_state.pop(_SK_PRESET, None)
        st.success("✅ Saved.")
        st.rerun()

    # ── Test connection ───────────────────────────────────────────────────────
    st.divider()
    st.markdown("**Test connection**")
    if not smtp_settings.is_configured():
        st.info(
            "Fill in Host, Username and App Password, then click **Save** before testing.",
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
            hint = _smtp_error_hint(exc)
            st.error(f"❌ {exc}")
            if hint:
                st.warning(hint)
