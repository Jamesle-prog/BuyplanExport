"""Admin: 🔐 Login Log — who signed in, when, and how it went.

Admin-only by placement (rendered only inside the Admin panel, which the
router shows only to admins). Reads the append-only ``login_log`` table:
successful sign-ins plus the security-relevant failures and lockouts.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.i18n import t
from ui.shared import fragment_rerun, CSV_MIME
from ui.stores import get_login_log_store
from po_extractor.store.login_log_store import (
    OUTCOME_SUCCESS, OUTCOME_FAILED, OUTCOME_LOCKED,
)

_OUTCOME_BADGE = {
    OUTCOME_SUCCESS: "✅ ",
    OUTCOME_FAILED:  "❌ ",
    OUTCOME_LOCKED:  "🔒 ",
}
_ALL = "__all__"


def show_login_log_admin() -> None:
    st.subheader(f"🔐 {t('Login Log')}")
    st.caption(t("Every sign-in attempt — successful logins plus wrong "
                 "passwords and lockouts. Visible to admins only."))
    store = get_login_log_store()

    c = store.counts()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("Successful logins"), f"{c['success']:,}")
    m2.metric(t("Distinct users"),    f"{c['users']:,}")
    m3.metric(t("Failed"),            f"{c['failed']:,}")
    m4.metric(t("Locked out"),        f"{c['locked']:,}")

    # ── Filters ──────────────────────────────────────────────────────────────
    f1, f2, f3 = st.columns([2, 2, 1])
    with f1:
        outcome_opt = st.selectbox(
            t("Outcome"), [_ALL, OUTCOME_SUCCESS, OUTCOME_FAILED, OUTCOME_LOCKED],
            format_func=lambda o: {
                _ALL: t("All"),
                OUTCOME_SUCCESS: t("Successful only"),
                OUTCOME_FAILED: t("Failed only"),
                OUTCOME_LOCKED: t("Locked only"),
            }[o],
            key="ll_outcome",
        )
    with f2:
        uname_like = st.text_input(t("Filter by username"), key="ll_uname",
                                   placeholder=t("type to filter…"))
    with f3:
        limit = st.selectbox(t("Show"), [100, 250, 500, 1000], index=1,
                             key="ll_limit")

    rows = store.list_recent(
        limit=int(limit),
        outcome=None if outcome_opt == _ALL else outcome_opt,
        username_like=uname_like or None,
    )
    if not rows:
        st.info(t("No sign-in events match the current filters."))
        return

    df = pd.DataFrame([{
        "Time":     r["ts"],
        "Username": r["username"] or "—",
        "Outcome":  _OUTCOME_BADGE.get(r["outcome"], "") + t(r["outcome"]),
        "Detail":   r["detail"] or "",
        "IP":       r["ip"] or "",
    } for r in rows])
    st.dataframe(
        df, width="stretch", hide_index=True,
        height=min(60 + 35 * len(df), 560),
        column_config={
            "Time":     st.column_config.TextColumn(t("Time"), width="small"),
            "Username": st.column_config.TextColumn(t("Username"), width="small"),
            "Outcome":  st.column_config.TextColumn(t("Outcome"), width="small"),
            "Detail":   st.column_config.TextColumn(t("Detail"), width="medium"),
            "IP":       st.column_config.TextColumn(t("IP address"), width="small"),
        },
    )

    d1, d2 = st.columns([1, 3])
    with d1:
        st.download_button(
            "⬇️ " + t("Download (.csv)"),
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="login_log.csv", mime=CSV_MIME,
            key="ll_csv", width="stretch",
        )

    # ── Maintenance ──────────────────────────────────────────────────────────
    with st.expander(f"🧹 {t('Maintenance')}", expanded=False):
        mc1, mc2 = st.columns(2)
        with mc1:
            from po_extractor.config import LOGIN_LOG_RETENTION_DAYS
            days = st.number_input(t("Delete events older than (days)"),
                                   min_value=0, value=LOGIN_LOG_RETENTION_DAYS,
                                   step=30, key="ll_purge_days")
            if st.button(t("Purge old events"), key="ll_purge_btn"):
                n = store.purge_older_than(int(days))
                st.success(f"✅ {n} {t('old event(s) removed.')}")
                fragment_rerun()
        with mc2:
            st.caption(t("Clearing the log is permanent and cannot be undone."))
            confirm = st.checkbox(t("I understand — delete the entire log"),
                                  key="ll_clear_confirm")
            if st.button(t("Clear the whole log"), key="ll_clear_btn",
                         type="secondary", disabled=not confirm):
                n = store.clear()
                st.success(f"✅ {n} {t('event(s) cleared.')}")
                fragment_rerun()
