"""Admin: 📝 Change Log — who changed what, and when.

Admin-only by placement (rendered only inside the Admin panel, which the
router shows only to admins). Reads the append-only ``change_log`` table.

This answers the question the per-module history tables cannot:
``sky_east_item_history`` keeps whole superseded rows and
``po_version_history`` keeps prior PO versions, but each covers only its own
corner and neither records who acted. This view is the cross-module trail —
filter by person, by kind of record, or by the record itself.
"""
from __future__ import annotations

import streamlit as st

from ui.i18n import t
from ui.shared import fragment_rerun, CSV_MIME, csv_safe, _th
from ui.stores import get_change_log_store

_ALL = "__all__"

# Friendly names for the entity codes stored in the table.
_ENTITY_LABELS = {
    "boat_sample_req": "🚢 船样要求",
    "sky_east_item":   "🛍 Sky East item",
    "sky_east_contract": "📄 Sky East contract",
    "user":            "👤 User account",
}

_ACTION_BADGE = {"create": "🟢 ", "update": "🔵 ", "delete": "🔴 "}


def show_change_log_admin() -> None:
    st.subheader(f"📝 {t('Change Log')}")
    st.caption(t(
        "Who changed what, across the whole app. Each row is one field: the "
        "value before and after, the person, and the time. Records are never "
        "edited or overwritten — only added."
    ))
    store = get_change_log_store()

    c = store.counts()
    m1, m2, m3 = st.columns(3)
    m1.metric(t("Changes recorded"), f"{c['total']:,}")
    m2.metric(t("People"),           f"{c['users']:,}")
    m3.metric(t("Today"),            f"{c['today']:,}")

    if not c["total"]:
        st.info(t(
            "Nothing recorded yet. Changes appear here as people edit "
            "船样要求, contracts and accounts."
        ))
        return

    # ── Filters ─────────────────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
    with f1:
        users = store.users()
        who = st.selectbox(
            t("Person"), [_ALL] + users,
            format_func=lambda u: t("Everyone") if u == _ALL else u,
            key="cl_user")
    with f2:
        ents = store.entities()
        entity = st.selectbox(
            t("Kind"), [_ALL] + ents,
            format_func=lambda e: (t("All kinds") if e == _ALL
                                   else _ENTITY_LABELS.get(e, e)),
            key="cl_entity")
    with f3:
        rec = st.text_input(t("Filter by record"), key="cl_record",
                            placeholder=t("e.g. a brand or PC No."))
    with f4:
        limit = st.selectbox(t("Show"), [100, 250, 500, 1000], index=1,
                             key="cl_limit")

    df = store.list_recent(
        limit=int(limit),
        username=None if who == _ALL else who,
        entity=None if entity == _ALL else entity,
        record_key=rec or None,
    )
    if df.empty:
        st.info(t("No changes match the current filters."))
        return

    show = df.rename(columns={
        "ts": _th("Time"), "username": _th("Who"),
        "entity": _th("Kind"), "record_key": _th("Record"),
        "action": _th("Action"), "field": _th("Field"),
        "old_value": _th("Before"), "new_value": _th("After"),
    })
    show[_th("Kind")] = show[_th("Kind")].map(
        lambda e: _ENTITY_LABELS.get(e, e))
    show[_th("Action")] = show[_th("Action")].map(
        lambda a: _ACTION_BADGE.get(a, "") + t(a))
    show[_th("Who")] = show[_th("Who")].replace("", "—")

    st.dataframe(
        show[[_th("Time"), _th("Who"), _th("Kind"), _th("Record"),
              _th("Action"), _th("Field"), _th("Before"), _th("After")]],
        width="stretch", hide_index=True,
        height=min(60 + 35 * len(show), 560),
    )

    st.download_button(
        "⬇️ " + t("Download (.csv)"),
        data=csv_safe(show).to_csv(index=False).encode("utf-8-sig"),
        file_name="change_log.csv", mime=CSV_MIME, key="cl_csv")

    # ── Maintenance ─────────────────────────────────────────────────────────
    with st.expander(f"🧹 {t('Maintenance')}", expanded=False):
        st.caption(t("Old entries can be trimmed; nothing else removes them."))
        days = st.number_input(t("Delete entries older than (days)"),
                               min_value=0, value=365, step=30,
                               key="cl_purge_days")
        if st.button(t("Purge old entries"), key="cl_purge_btn"):
            n = store.purge_older_than(int(days))
            st.success(f"✅ {n} {t('old entr(ies) removed.')}")
            fragment_rerun()
