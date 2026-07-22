"""Admin: User management view."""
from __future__ import annotations

import streamlit as st

from ui.i18n import t
from auth.companies import list_company_names
from ui.shared import guard_multiselect_state
from auth.users import (
    ALL_MODULES, MODULE_LABELS, ROLE_ADMIN, create_user, delete_user,
    get_user, list_users, set_user_companies, set_user_email,
    set_user_factories, set_user_modules, set_user_role,
)


def _known_factories() -> list[str]:
    """Factory names a user can be scoped to. Prefers the canonical factories
    from the dictionary (so one assignment covers all a factory's client
    spellings); falls back to the raw distinct strings on tracking records
    when the dictionary is empty. Never raises."""
    try:
        from ui.stores import get_factory_registry_store
        canon = get_factory_registry_store().canonical_names()
        if canon:
            return canon
    except Exception:
        pass
    try:
        from ui.stores import get_production_tracking_store
        return get_production_tracking_store().list_distinct_factories()
    except Exception:
        return []


def show_user_admin() -> None:
    st.subheader(f"⚙️ {t('User Management')}")
    all_companies = list_company_names()
    all_factories = _known_factories()
    users = list_users()

    for uname in users:
        info = get_user(uname) or {}
        role = info.get("role", "user")
        cos = info.get("companies", [])
        email = info.get("email", "")
        mods = info.get("modules", [])
        facs = info.get("factories", [])
        mod_summary = ", ".join(MODULE_LABELS.get(m, m) for m in mods) or t("all tabs")
        with st.expander(
            f"{'👑' if role == ROLE_ADMIN else '👤'} {uname}  |  {role}  |  "
            f"{t('companies:')} {', '.join(cos) or t('all (admin)')}  |  {t('tabs:')} {mod_summary}"
            + (f"  |  🏭 {len(facs)}" if facs else "")
            + (f"  |  ✉ {email}" if email else "")
        ):
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                new_role = st.selectbox(
                    t("Role"), ["admin", "user"],
                    index=0 if role == "admin" else 1,
                    format_func=lambda r: t(r),
                    key=f"role_{uname}",
                )
                if st.button(t("Set role"), key=f"setrole_{uname}"):
                    # Last-admin guard: demoting the only admin would leave
                    # no account able to manage users/companies (recovery
                    # would need setup_users.py on the server).
                    if role == ROLE_ADMIN and new_role != ROLE_ADMIN and not any(
                        u != uname and (get_user(u) or {}).get("role") == ROLE_ADMIN
                        for u in users
                    ):
                        st.error(t("Cannot demote the last admin account."))
                    else:
                        set_user_role(uname, new_role)
                        st.success(t("Role updated."))
                        st.rerun()
            with c2:
                # Seed once from the DB, then guard — key= together with
                # default= silently ignores DB changes once widget state
                # exists (banned pattern, CLAUDE.md).
                _cos_key = f"cos_{uname}"
                if _cos_key not in st.session_state:
                    st.session_state[_cos_key] = [c for c in cos if c in all_companies]
                else:
                    guard_multiselect_state(_cos_key, all_companies)
                new_cos = st.multiselect(
                    t("Allowed companies (leave empty = all for admin)"),
                    all_companies,
                    key=_cos_key,
                )
                if st.button(t("Set companies"), key=f"setcos_{uname}"):
                    set_user_companies(uname, new_cos)
                    st.success(t("Companies updated."))
                    st.rerun()
            with c3:
                if uname != st.session_state.username:
                    if st.button(f"🗑 {t('Delete user')}", key=f"del_{uname}"):
                        delete_user(uname)
                        st.success(f"{t('Deleted')} {uname}.")
                        st.rerun()
            _mods_key = f"mods_{uname}"
            if _mods_key not in st.session_state:
                st.session_state[_mods_key] = [m for m in mods if m in ALL_MODULES]
            else:
                guard_multiselect_state(_mods_key, ALL_MODULES)
            new_mods = st.multiselect(
                t("Allowed tabs (leave empty = all tabs)"),
                ALL_MODULES,
                format_func=lambda m: MODULE_LABELS.get(m, m),
                key=_mods_key,
                help=t("Restricts which top-level tabs this user sees. "
                       "'Sky East — Buy Plan only' hides Contract History / "
                       "Missing Fields and pins Generate/Export to Buy Plan mode."),
            )
            if st.button(t("Set allowed tabs"), key=f"setmods_{uname}"):
                set_user_modules(uname, new_mods)
                st.success(t("Allowed tabs updated."))
                st.rerun()

            # ── Factory scope (production tracking) ────────────────────────
            _facs_key = f"facs_{uname}"
            if _facs_key not in st.session_state:
                st.session_state[_facs_key] = [f for f in facs if f in all_factories]
            else:
                guard_multiselect_state(_facs_key, all_factories)
            new_facs = st.multiselect(
                t("Factory scope — Tracking (empty = all factories)"),
                all_factories,
                key=_facs_key,
                help=t("A user with factories set sees ONLY those factories' "
                       "rows in 🏭 Tracking and may only record progress "
                       "(actual dates, quantity reports, status notes) — not "
                       "planned dates, and no adding/removing rows."),
            )
            if st.button(t("Set factory scope"), key=f"setfac_{uname}"):
                set_user_factories(uname, new_facs)
                st.success(t("Factory scope updated."))
                st.rerun()

            new_email = st.text_input(
                t("Email (used for sending generated files)"),
                value=email, key=f"email_{uname}",
                placeholder="user@example.com",
            )
            if st.button(t("Set email"), key=f"setemail_{uname}"):
                set_user_email(uname, new_email)
                st.success(t("Email updated."))
                st.rerun()

    st.divider()
    st.markdown(f"**{t('Create new user')}**")
    nc1, nc2, nc3, nc4, nc5 = st.columns([1, 1, 1, 1, 1.4])
    with nc1:
        new_uname = st.text_input(t("Username"), key="new_uname")
    with nc2:
        new_pw = st.text_input(t("Password"), type="password", key="new_pw")
    with nc3:
        new_role = st.selectbox(t("Role"), ["user", "admin"],
                                format_func=lambda r: t(r), key="new_role")
    with nc4:
        new_cos = st.multiselect(t("Companies"), all_companies, key="new_cos")
    with nc5:
        new_email = st.text_input(t("Email (optional)"), key="new_email",
                                  placeholder="user@example.com")
    new_mods = st.multiselect(
        t("Allowed tabs (leave empty = all tabs)"),
        ALL_MODULES,
        format_func=lambda m: MODULE_LABELS.get(m, m),
        key="new_mods",
    )
    new_facs = st.multiselect(
        t("Factory scope — Tracking (empty = all factories)"),
        all_factories,
        key="new_facs",
        help=t("Set this to make a factory login: they see only these "
               "factories in 🏭 Tracking and can only record progress."),
    )
    if st.button(f"➕ {t('Create user')}", type="primary"):
        if new_uname and new_pw:
            create_user(new_uname, new_pw, role=new_role,
                        companies=new_cos, email=new_email, modules=new_mods,
                        factories=new_facs)
            st.success(f"{t('User')} '{new_uname}' {t('created.')}")
            st.rerun()
        else:
            st.error(t("Username and password are required."))
