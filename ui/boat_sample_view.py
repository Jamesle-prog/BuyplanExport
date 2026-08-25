"""船样要求 (shipping-sample requirements) editor, shared by two mount points.

The requirement text is stored per **(company, brand)** and written into the
船样要求 column of every matching Sky East buy-plan row at export time.

Who may edit what is decided in one place — :func:`editable_companies` — and
enforced again on save, not merely by filtering the dropdown: a widget key
outlives the options that populated it, so a company can still be sitting in
session state after the user's access to it has gone.

Mount points:
  • 📐 Reference Data → 🚢 船样要求 — any signed-in user, their own companies
    only (see :func:`show_boat_sample_section`).
  • Admin → 🚢 船样要求 — every company (``ui.admin_boat_sample``).

Before this existed the only ways to set a requirement were the admin panel and
the one-shot prompt shown when a brand was first uploaded, so a user without
admin rights could not correct their own company's text afterwards.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from auth.companies import list_company_names
from auth.users import get_user_brands, get_user_companies, is_admin
from ui.i18n import t
from ui.session_keys import SK
from ui.shared import _th, delete_button
from ui.stores import get_boat_sample_store, list_all_brands


def editable_companies(username: str) -> list[str]:
    """Companies whose 船样要求 *username* may change, in display order.

    Admins get every active company. Everyone else gets their own, intersected
    with the active list so a deactivated company doesn't linger.

    The empty list is why this is a function rather than a one-liner at each
    call site: ``get_user_companies`` returns ``[]`` for an admin meaning
    "unrestricted", and ``[]`` for an unassigned regular user meaning "none at
    all". Reading it without checking the role is how a restricted account ends
    up editing every company's data.
    """
    active = list_company_names(active_only=True) or []
    if is_admin(username):
        return active
    mine = set(get_user_companies(username) or [])
    return [c for c in active if c in mine]


def show_boat_sample_section() -> None:
    """📐 Reference Data → 🚢 船样要求 — the current user's own companies."""
    user = st.session_state.get(SK.USERNAME, "") or ""
    companies = editable_companies(user)

    st.caption(t(
        "The shipping-sample requirement written into the 船样要求 column of "
        "every matching row when a Sky East buy plan is generated. Set per "
        "brand, per company."
    ))

    if not companies:
        st.info(t(
            "Your account isn't assigned to a company yet, so there's nothing "
            "to edit here. Ask an administrator to assign one."
        ))
        return

    # Brand scope narrows within the companies above. Empty = every brand of
    # those companies, which is what an account with no brands assigned has
    # always had — adding the field takes nothing away from anyone.
    my_brands = get_user_brands(user)
    if not is_admin(user):
        if my_brands:
            st.caption("🔒 " + t("You look after") + ": **"
                       + "**, **".join(my_brands) + "**. "
                       + t("Ask an administrator to change which brands are "
                           "yours."))
        else:
            st.caption("🔒 " + t("You can edit the companies your account is "
                                 "assigned to. Administrators can edit all of "
                                 "them under Admin → 船样要求."))
    render_boat_sample_editor(companies, key_prefix="bsr_ref",
                              brands_allowed=my_brands)


def render_boat_sample_editor(companies: list[str], *, key_prefix: str,
                              brands_allowed: list[str] | None = None) -> None:
    """The editor itself, restricted to *companies* and optionally to
    *brands_allowed*.

    *brands_allowed* is the brand scope from the signed-in user's account.
    ``None`` or empty means no brand restriction — every brand of *companies*,
    which is how this behaved before brand scope existed and what every
    unassigned account still gets. That is safe because company access has
    already been decided by the caller; brands only narrow within it. (Do not
    make an empty list mean "nothing" here by analogy with the company list —
    the two answer different questions. See auth.users.get_user_brands.)

    *key_prefix* keeps the two mount points' widgets independent — an admin who
    has used both in one session should not find the Reference Data selection
    dragged along into the admin panel.
    """
    store = get_boat_sample_store()
    allowed = set(companies)
    brand_scope = {b for b in (brands_allowed or []) if b}
    # Every read is scoped here, so nothing downstream has to remember to.
    rows = [r for r in store.list_all() if r.get("company") in allowed]
    if brand_scope:
        rows = [r for r in rows if r.get("brand") in brand_scope]

    st.markdown(f"##### {t('Existing requirements')}")
    if rows:
        df = pd.DataFrame(rows, columns=["company", "brand", "req_text", "updated_at"])
        df.columns = [_th("Company"), _th("Brand"),
                      _th("Requirement Text"), _th("Last Updated")]
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info(t("No requirements defined yet."))

    st.divider()
    st.markdown(f"##### {t('Add / Edit requirement')}")

    # Outside the form so choosing a company reruns and refreshes the brands.
    # A single company needs no chooser — showing a one-option dropdown just
    # asks for a click that can only be answered one way.
    if len(companies) == 1:
        selected_company = companies[0]
        st.caption(f"{t('Company')}: **{selected_company}**")
    else:
        co_key = f"{key_prefix}_company"
        # Stale-value guard: the stored key survives a change in access.
        if st.session_state.get(co_key) not in companies:
            st.session_state[co_key] = companies[0]
        selected_company = st.selectbox(
            t("Company"), options=companies, key=co_key,
            help=t("Requirements are stored per company."),
        )

    brands: list[str] = list_all_brands(selected_company) if selected_company else []
    if brand_scope:
        brands = [b for b in brands if b in brand_scope]

    pending = [r for r in rows
               if r.get("company") == selected_company
               and not (r.get("req_text") or "").strip()]
    if pending:
        names = ", ".join(f"**{r['brand']}**" for r in pending[:8])
        if len(pending) > 8:
            names += f" … +{len(pending) - 8} " + t("more")
        st.warning(
            f"⏳ {len(pending)} " + t("brand(s) under") + f" **{selected_company}** "
            + t("still need a 船样要求") + f": {names}", icon="⏳")

    if not brands:
        st.caption("ℹ️ " + t(
            "No brands on file for this company yet. They appear automatically "
            "once Sky East orders are processed, or after colour data is "
            "imported."
        ))

    # Brand sits outside the form for the same reason as company: picking one
    # has to rerun the page so the text box below can load what's on file.
    # Inside a form nothing applies until submit, and the box would stay empty.
    brand_key = f"{key_prefix}_brand"
    if st.session_state.get(brand_key) not in brands:
        st.session_state[brand_key] = None
    selected_brand = st.selectbox(
        t("Brand"), options=brands, index=None,
        placeholder=t("— select brand —"), key=brand_key,
    )

    # Load the stored text whenever the target changes, so editing is a
    # correction rather than a retype from memory — the whole reason someone
    # comes back here after the first upload. Assigned into session state, not
    # passed as value=: Streamlit ignores value= once a keyed widget exists.
    text_key = f"{key_prefix}_text"
    target = (selected_company, selected_brand)
    if st.session_state.get(f"{key_prefix}_loaded") != target:
        st.session_state[f"{key_prefix}_loaded"] = target
        st.session_state[text_key] = (
            store.get(selected_company, selected_brand) if selected_brand else "")

    with st.form(f"{key_prefix}_form"):
        req_text = st.text_area(
            t("Requirement Text (船样要求)"), height=100,
            placeholder=t("Enter the shipping-sample requirement text…"),
            key=text_key,
        )
        submitted = st.form_submit_button(f"💾 {t('Save')}", type="primary",
                                          width="stretch")

    if submitted:
        company_v = (selected_company or "").strip()
        brand_v = (selected_brand or "").strip()
        text_v = (req_text or "").strip()
        # Re-checked at the point of writing, not just when the options were
        # drawn — see the module docstring.
        if company_v not in allowed:
            st.error(t("You don't have access to that company."))
        elif brand_scope and brand_v not in brand_scope:
            # Re-checked at the point of writing, not just when the options
            # were drawn — a widget key outlives the list that filled it.
            st.error(t("You don't have access to that brand."))
        elif not brand_v:
            st.error(t("No brand selected."))
        elif not text_v:
            # Blank is never accepted: the 船样要求 is compulsory, and a brand
            # left blank is asked about again on every Sky East screen and
            # holds its buy plan.
            st.error("⚠️ " + t("A 船样要求 is required — it cannot be left "
                               "blank."))
        else:
            store.upsert(company_v, brand_v, text_v)
            st.success(f"{t('Saved requirement for')} **{company_v} / {brand_v}**.")
            st.rerun()

    if not rows:
        return

    st.divider()
    st.markdown(f"##### {t('Delete requirement')}")
    options = [f"{r['company']} / {r['brand']}" for r in rows]
    del_idx = st.selectbox(
        t("Select entry to delete"), options=range(len(options)),
        format_func=lambda i: options[i], index=None,
        placeholder=t("— choose —"), key=f"{key_prefix}_del",
    )
    if delete_button(t("Delete selected"), disabled=del_idx is None,
                     key=f"{key_prefix}_del_btn"):
        if del_idx is not None:
            target = rows[del_idx]
            if target["company"] not in allowed:      # same guard as the save
                st.error(t("You don't have access to that company."))
            elif brand_scope and target["brand"] not in brand_scope:
                st.error(t("You don't have access to that brand."))
            elif store.delete(target["company"], target["brand"]):
                st.success(f"{t('Deleted')}: {options[del_idx]}")
                st.rerun()
            else:
                st.warning(t("Entry not found (already deleted?)."))
