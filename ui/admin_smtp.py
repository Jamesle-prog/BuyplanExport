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
        "label": "SendGrid",
        "icon": "📨",
        "host": "smtp.sendgrid.net",
        "port": 587,
        "use_tls": True,
    },
    {
        "label": "Brevo",
        "icon": "💌",
        "host": "smtp-relay.brevo.com",
        "port": 587,
        "use_tls": True,
    },
    {
        "label": "Resend",
        "icon": "⚡",
        "host": "smtp.resend.com",
        "port": 465,
        "use_tls": False,  # Resend uses SSL on 465, not STARTTLS
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
        "535",
        "**Authentication failed — Microsoft has blocked basic SMTP auth for this account.**\n\n"
        "Even App Passwords are blocked on some personal Outlook/Hotmail accounts. "
        "The most reliable fix is to use **SendGrid** as a free relay:\n\n"
        "1. Sign up free at https://sendgrid.com (100 emails/day free)\n"
        "2. Go to **Settings → API Keys → Create API Key** (Full Access)\n"
        "3. In PO Extractor → Admin → 📧 Email → click **📨 SendGrid** preset\n"
        "4. **Username:** `apikey` (literally type: apikey)\n"
        "5. **App Password:** paste your SendGrid API key\n"
        "6. **Sender:** your verified email address\n\n"
        "Alternatively, if you have a Gmail account, the **🔴 Gmail** preset "
        "with an App Password works reliably.",
    ),
    (
        "authentication unsuccessful",
        "**Authentication unsuccessful.** Microsoft has blocked basic SMTP auth on this account.\n\n"
        "Switch to **📨 SendGrid** (free) or **🔴 Gmail** — both work reliably. "
        "See the SendGrid setup guide above.",
    ),
    (
        "smtp auth extension not supported",
        "**SMTP AUTH is disabled** on this mailbox. For Office 365 work accounts, "
        "ask your IT admin to enable SMTP AUTH in the Microsoft 365 admin centre, "
        "or use **📨 SendGrid** as a relay instead.",
    ),
    (
        "username and password not accepted",
        "**Credentials rejected.** For Gmail, use an App Password:\n\n"
        "1. Enable 2-Step Verification: https://myaccount.google.com/security\n"
        "2. Create App Password: https://myaccount.google.com/apppasswords\n"
        "3. Use the 16-character password in the Password field.",
    ),
]


def _smtp_error_hint(exc: EmailError, host: str = "") -> str | None:
    msg = str(exc).lower()
    h = (host or "").lower()

    # Brevo-specific: 535 means wrong username (must be Brevo account email)
    if "brevo" in h and "535" in msg:
        return (
            "**Brevo: wrong username.**\n\n"
            "For Brevo the **Username** must be the email address you used to "
            "register on brevo.com — NOT your hotmail/gmail address.\n\n"
            "Find it at https://app.brevo.com/settings/keys/smtp → "
            "the login shown next to your SMTP key is your Brevo username."
        )

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

    # Provider-specific instructions
    if active:
        label = active["label"]
        if label == "Outlook / Hotmail":
            st.warning(
                "⚠️ **Microsoft has disabled basic SMTP auth for most personal Outlook/Hotmail "
                "accounts** — even App Passwords are blocked in many regions.\n\n"
                "If you keep getting error 535, switch to **📨 SendGrid** (free) or **🔴 Gmail** instead.",
            )
            st.info(
                "**If you still want to try Outlook:**\n\n"
                "1. Enable 2FA at https://account.microsoft.com/security\n"
                "2. Create App Password → Advanced security options → App passwords\n"
                "3. Enable POP/IMAP at https://outlook.live.com/mail/0/options/mail/accounts/popImap\n"
                "4. Use your full email as Username and the App Password below",
                icon="ℹ️",
            )
        elif label == "Office 365 (work)":
            st.info(
                "**🏢 Office 365 setup**\n\n"
                "- Username: your full work email address\n"
                "- Password: your Microsoft 365 password (or App Password if MFA is on)\n"
                "- Your IT admin must have **SMTP AUTH enabled** for your mailbox",
                icon="ℹ️",
            )
        elif label == "Gmail":
            st.info(
                "**🔴 Gmail setup**\n\n"
                "1. Enable 2-Step Verification: https://myaccount.google.com/security\n"
                "2. Create App Password: https://myaccount.google.com/apppasswords\n"
                "3. Username: your Gmail address\n"
                "4. Password: the 16-character App Password (not your normal password)",
                icon="ℹ️",
            )
        elif label == "SendGrid":
            st.success(
                "**📨 SendGrid — 100 emails/day free**\n\n"
                "1. Sign up at https://sendgrid.com\n"
                "2. **Settings → API Keys → Create API Key** → Full Access → Create\n"
                "3. **Username:** `apikey` (literally)\n"
                "4. **Password:** paste your API key\n"
                "5. **Sender:** verify at https://app.sendgrid.com/settings/sender_auth",
            )
        elif label == "Brevo":
            st.success(
                "**💌 Brevo — 300 emails/day free (best free tier)**\n\n"
                "1. Sign up at https://brevo.com\n"
                "2. Go to **Settings → SMTP & API → Generate a new SMTP key**\n"
                "3. **Username:** your Brevo account email address\n"
                "4. **Password:** paste the SMTP key (not your login password)\n"
                "5. **Sender:** any address you've verified in Brevo\n\n"
                "300 emails/day free — 3× more than SendGrid.",
            )
        elif label == "Resend":
            st.success(
                "**⚡ Resend — 100 emails/day free, 3,000/month**\n\n"
                "1. Sign up at https://resend.com\n"
                "2. Go to **API Keys → Create API Key**\n"
                "3. **Username:** `resend` (literally)\n"
                "4. **Password:** paste your API key\n"
                "5. **Sender:** must use a verified domain (e.g. `you@yourdomain.com`)\n"
                "   — free accounts can also use `onboarding@resend.dev` for testing\n\n"
                "Uses SSL on port 465 (configured automatically).",
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
                                 placeholder="smtp.sendgrid.net")
        with c2:
            port = st.number_input("Port", min_value=1, max_value=65535,
                                   value=_port_default(), step=1)

        c3, c4 = st.columns(2)
        with c3:
            user = st.text_input(
                "Username",
                value=cur["user"],
                placeholder="apikey  (for SendGrid) / you@gmail.com",
            )
        with c4:
            password = st.text_input(
                "Password / API Key / App Password",
                value=cur["password"],
                type="password",
            )

        sender = st.text_input(
            "Sender (From address)",
            value=cur["sender"],
            placeholder="PO Extractor <you@example.com>",
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
            "Fill in Host, Username and Password/API Key, then click **Save** before testing.",
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
            hint = _smtp_error_hint(exc, host=configured["host"])
            st.error(f"❌ {exc}")
            if hint:
                st.warning(hint)
