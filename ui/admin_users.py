"""Admin: User management view."""
from __future__ import annotations

import streamlit as st

from auth.companies import list_company_names
from auth.users import (
    ROLE_ADMIN, create_user, delete_user, get_user, list_users,
    set_user_companies, set_user_role,
)


def show_user_admin() -> None:
    st.subheader("⚙️ User Management")
    all_companies = list_company_names()
    users = list_users()

    for uname in users:
        info = get_user(uname) or {}
        role = info.get("role", "user")
        cos = info.get("companies", [])
        with st.expander(
            f"{'👑' if role == ROLE_ADMIN else '👤'} {uname}  |  {role}  |  "
            f"companies: {', '.join(cos) or 'all (admin)'}"
        ):
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                new_role = st.selectbox(
                    "Role", ["admin", "user"],
                    index=0 if role == "admin" else 1,
                    key=f"role_{uname}",
                )
                if st.button("Set role", key=f"setrole_{uname}"):
                    set_user_role(uname, new_role)
                    st.success("Role updated.")
                    st.rerun()
            with c2:
                new_cos = st.multiselect(
                    "Allowed companies (leave empty = all for admin)",
                    all_companies,
                    default=[c for c in cos if c in all_companies],
                    key=f"cos_{uname}",
                )
                if st.button("Set companies", key=f"setcos_{uname}"):
                    set_user_companies(uname, new_cos)
                    st.success("Companies updated.")
                    st.rerun()
            with c3:
                if uname != st.session_state.username:
                    if st.button("🗑 Delete user", key=f"del_{uname}"):
                        delete_user(uname)
                        st.success(f"Deleted {uname}.")
                        st.rerun()

    st.divider()
    st.markdown("**Create new user**")
    nc1, nc2, nc3, nc4 = st.columns([1, 1, 1, 1])
    with nc1:
        new_uname = st.text_input("Username", key="new_uname")
    with nc2:
        new_pw = st.text_input("Password", type="password", key="new_pw")
    with nc3:
        new_role = st.selectbox("Role", ["user", "admin"], key="new_role")
    with nc4:
        new_cos = st.multiselect("Companies", all_companies, key="new_cos")
    if st.button("➕ Create user", type="primary"):
        if new_uname and new_pw:
            create_user(new_uname, new_pw, role=new_role, companies=new_cos)
            st.success(f"User '{new_uname}' created.")
            st.rerun()
        else:
            st.error("Username and password are required.")
