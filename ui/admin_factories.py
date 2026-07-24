"""Admin: Factory dictionary — canonical factories, aliases, and resolving
the unknown factory strings that turn up on loaded POs.

Two sections:
  1. **Needs review** — factory names present in loaded data but not in the
     dictionary. For each, the admin links it as an alias of an existing
     factory (a fuzzy suggestion is pre-selected) or approves it as new.
  2. **Dictionary** — the canonical factories with their aliases; add /
     rename / delete, and add aliases by hand.

Regular users never see this; they load POs uninterrupted and the unknown
names collect here for an admin to resolve.
"""
from __future__ import annotations

import streamlit as st

from ui.i18n import t
from ui.shared import fragment_rerun
from ui.stores import get_factory_registry_store


def _current_user() -> str:
    return st.session_state.get("username", "") or ""


def show_factory_admin() -> None:
    st.subheader(f"🏭 {t('Factory Dictionary')}")
    st.caption(t(
        "Different clients write the same factory differently. Link each name "
        "to one canonical factory so tracking and factory logins treat them "
        "as one."
    ))
    store = get_factory_registry_store()

    _render_unresolved(store)
    st.divider()
    _render_dictionary(store)


def _render_unresolved(store) -> None:
    unresolved = store.list_unresolved()
    st.markdown(f"### {t('Needs review')} ({len(unresolved)})")
    if not unresolved:
        st.success(t("Every factory name in your data is in the dictionary."))
        return
    st.caption(t(
        "These factory names appear on loaded POs but aren't linked yet. For "
        "each, link it to an existing factory (it's just a different name) or "
        "add it as a new factory."
    ))

    cans = store.list_canonical()
    can_names = [c["name"] for c in cans]
    name_to_id = {c["name"]: c["id"] for c in cans}

    for item in unresolved:
        raw = item["raw"]
        sugg = item["suggestion"]
        key = "".join(ch for ch in raw if ch.isalnum())[:40] or str(abs(hash(raw)))
        with st.container(border=True):
            st.markdown(f"**{raw}**")
            if sugg:
                st.caption("💡 " + t("Looks like") + f": **{sugg['name']}**")

            choices = [t("Link to existing factory"), t("Add as new factory")]
            # Default to "link" when we have canonicals to link to, else "new".
            default_choice = 0 if can_names else 1
            choice = st.radio(
                t("Resolve"), choices, index=default_choice,
                horizontal=True, key=f"fac_res_{key}",
                label_visibility="collapsed",
            )

            if choice == choices[0] and can_names:
                # Pre-select the fuzzy suggestion if there is one.
                idx = 0
                if sugg and sugg["name"] in can_names:
                    idx = can_names.index(sugg["name"])
                target = st.selectbox(
                    t("Canonical factory"), can_names, index=idx,
                    key=f"fac_link_{key}",
                )
                if st.button(f"🔗 {t('Link')}", key=f"fac_linkbtn_{key}",
                             type="primary"):
                    try:
                        store.add_alias(raw, name_to_id[target],
                                        created_by=_current_user())
                        st.success(f"✅ {raw} → {target}")
                        fragment_rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            else:
                new_name = st.text_input(
                    t("New factory name"), value=raw, key=f"fac_new_{key}")
                code = st.text_input(
                    t("Short code (optional)"), key=f"fac_code_{key}",
                    placeholder="e.g. 01423")
                if st.button(f"➕ {t('Add factory')}", key=f"fac_newbtn_{key}",
                             type="primary"):
                    try:
                        cid = store.add_canonical(
                            new_name, code=code, created_by=_current_user())
                        # If they renamed it, also alias the original raw string
                        # so the data row resolves.
                        if store.canonical_name(raw) is None:
                            store.add_alias(raw, cid, created_by=_current_user())
                        st.success(f"✅ {t('Added')}: {new_name}")
                        fragment_rerun()
                    except ValueError as exc:
                        st.error(str(exc))


def _render_dictionary(store) -> None:
    cans = store.list_canonical()
    st.markdown(f"### {t('Dictionary')} ({len(cans)})")

    with st.expander(f"➕ {t('Add a factory')}", expanded=not cans):
        c1, c2 = st.columns([3, 1])
        name = c1.text_input(t("Factory name"), key="fac_add_name")
        code = c2.text_input(t("Code"), key="fac_add_code",
                             placeholder="01423")
        if st.button(f"➕ {t('Add factory')}", key="fac_add_btn",
                     type="primary"):
            try:
                store.add_canonical(name, code=code, created_by=_current_user())
                st.success(f"✅ {t('Added')}: {name}")
                fragment_rerun()
            except ValueError as exc:
                st.error(str(exc))

    if not cans:
        st.info(t("No factories yet. Add one above, or resolve a name under "
                  "Needs review."))
        return

    for c in cans:
        title = c["name"] + (f"  ·  {c['code']}" if c["code"] else "")
        with st.expander(f"🏭 {title}  ({len(c['aliases'])} {t('names')})"):
            st.caption(t("Client-specific names that map to this factory:"))
            from po_extractor.store.factory_registry_store import norm as _fnorm
            _is_canon = {a: _fnorm(a) == _fnorm(c["name"]) for a in c["aliases"]}
            for alias in c["aliases"]:
                ac1, ac2 = st.columns([5, 1])
                ac1.markdown(f"• {alias}"
                             + (" *(" + t("canonical") + ")*" if _is_canon[alias] else ""))
                # The alias equal to the factory's own name can't be removed —
                # deleting it would leave the factory unresolvable by its name.
                if len(c["aliases"]) > 1 and not _is_canon[alias]:
                    if ac2.button("🗑", key=f"fac_dela_{c['id']}_{abs(hash(alias))}",
                                  help=t("Remove this name")):
                        store.remove_alias(alias)
                        fragment_rerun()

            new_alias = st.text_input(
                t("Add another name for this factory"),
                key=f"fac_addalias_{c['id']}")
            b1, b2 = st.columns([1, 1])
            if b1.button(f"🔗 {t('Add name')}", key=f"fac_addaliasbtn_{c['id']}"):
                try:
                    store.add_alias(new_alias, c["id"], created_by=_current_user())
                    st.success(f"✅ {new_alias} → {c['name']}")
                    fragment_rerun()
                except ValueError as exc:
                    st.error(str(exc))

            with b2:
                if st.button(f"🗑 {t('Delete factory')}",
                             key=f"fac_delc_{c['id']}"):
                    store.delete_canonical(c["id"])
                    st.success(f"{t('Deleted')}: {c['name']}")
                    fragment_rerun()
