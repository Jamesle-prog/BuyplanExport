"""Cutting Plan → Saved plans: browse, re-link, re-download, delete."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from po_extractor.exporters.cutting_plan_export import (
    build_standard_cut_plan, plan_header_from_parsed,
)
from ui.i18n import t
from ui.session_keys import SK
from ui.shared import _th, _tr, fragment_rerun
from ui.stores import get_cutting_plan_store
from ui.cutting_plan._shared import (
    XLSX_MIME, demand_matrix, link_rows, load_sky_east_items, po_label,
    select_pos,
)

_LIST_RENAME = {
    "id": "#", "plan_name": "Plan", "plan_date": "Plan date",
    "styles": "Styles", "colors": "Colors", "materials": "Materials",
    "order_qty": "Order qty", "cut_qty": "Cut qty",
    "total_markers": "Markers", "total_tables": "Tables",
    "fabric_length_m": "Fabric (m)", "efficiency_pct": "Efficiency %",
    "linked_pos": "Linked POs", "uploaded_at": "Uploaded",
    "uploaded_by": "By",
}


def show_plans_section() -> None:
    store = get_cutting_plan_store()
    df = store.list_plans()
    if df.empty:
        st.info(t("No cut plans saved yet — upload one in the "
                  "**Upload & Link** tab."))
        return

    search = st.text_input(
        t("Search"), key="cp_plans_search",
        placeholder=t("Plan name, style, colour or PO No."))
    view = _filter_plans(df, search, store)
    if view.empty:
        st.warning(t("No plans match the search."))
        return

    show = view[[c for c in _LIST_RENAME if c in view.columns]].copy()
    for col in ("fabric_length_m", "efficiency_pct"):
        if col in show.columns:
            show[col] = show[col].round(2)
    st.dataframe(show.rename(columns=_tr(_LIST_RENAME)),
                 use_container_width=True, hide_index=True)

    st.divider()
    ids = view["id"].tolist()
    labels = {
        int(r["id"]): f"#{int(r['id'])} — {r['plan_name']} "
                      f"({r.get('plan_date') or '—'}, {r.get('colors') or '—'})"
        for _, r in view.iterrows()
    }
    plan_id = st.selectbox(
        t("Open a plan"), ids, key="cp_plan_pick",
        format_func=lambda i: labels.get(int(i), str(i)))
    if plan_id is not None:
        _show_plan_detail(store, int(plan_id))


def _filter_plans(df: pd.DataFrame, search: str, store) -> pd.DataFrame:
    q = (search or "").strip().lower()
    if not q:
        return df
    text_cols = ["plan_name", "styles", "colors", "materials", "source_file",
                 "notes", "uploaded_by"]
    mask = pd.Series(False, index=df.index)
    for col in text_cols:
        if col in df.columns:
            mask |= df[col].fillna("").astype(str).str.lower().str.contains(
                q, regex=False)
    # Also match on a linked PC/PO number — that's how the cutting room looks
    # a plan up.
    hits = store.plans_for_pos(pc_nos=[search.strip()], po_nos=[search.strip()])
    if not hits.empty:
        mask |= df["id"].isin(hits["plan_id"].tolist())
    return df[mask]


def _show_plan_detail(store, plan_id: int) -> None:
    plan = store.get_plan(plan_id)
    if not plan:
        st.error(t("That plan no longer exists."))
        return

    st.markdown(f"### {plan.get('plan_name') or '—'}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("Order qty"), f"{int(plan.get('order_qty') or 0):,}")
    cut = int(plan.get("cut_qty") or 0)
    c2.metric(t("Cut qty"), f"{cut:,}",
              delta=(cut - int(plan.get("order_qty") or 0)) or None)
    c3.metric(t("Fabric length (m)"),
              f"{float(plan.get('fabric_length_m') or 0):,.1f}")
    c4.metric(t("Efficiency"), f"{float(plan.get('efficiency_pct') or 0):.2f} %")
    st.caption(
        f"{t('Styles')}: {plan.get('styles') or '—'} · "
        f"{t('Colors')}: {plan.get('colors') or '—'} · "
        f"{t('Materials')}: {plan.get('materials') or '—'} · "
        f"{t('Operator')}: {plan.get('operator') or '—'} · "
        f"{t('Client')}: {plan.get('client') or '—'} · "
        f"{t('Uploaded')}: {plan.get('uploaded_at') or '—'} "
        f"({plan.get('uploaded_by') or '—'})"
    )
    if plan.get("notes"):
        st.info(plan["notes"])

    tab_pos, tab_qty, tab_mat, tab_files = st.tabs(
        [t("Linked POs"), t("Quantities"), t("Materials & markers"),
         t("Files")])

    with tab_pos:
        _show_links(store, plan)
    with tab_qty:
        _show_quantities(store, plan_id)
    with tab_mat:
        _show_materials(plan)
    with tab_files:
        _show_files(store, plan)

    st.divider()
    with st.expander(f"🗑 {t('Delete this plan')}"):
        st.warning(t(
            "Deleting removes the plan, its PO links and the stored original "
            "file. This cannot be undone."))
        if st.checkbox(t("Yes, delete this cut plan"),
                       key=f"cp_del_ok_{plan_id}"):
            if st.button(t("Delete permanently"), type="primary",
                         key=f"cp_del_{plan_id}"):
                store.delete_plan(plan_id)
                st.session_state[SK.CP_FLASH] = (
                    "success", t("Cut plan deleted."))
                fragment_rerun()


def _show_links(store, plan: dict) -> None:
    links = plan.get("links") or []
    if links:
        st.dataframe(
            pd.DataFrame([{
                _th("PC No."): l.get("pc_no", ""),
                _th("PO No."): l.get("po_no", ""),
                _th("Linked"): l.get("linked_at", ""),
                _th("By"): l.get("linked_by", ""),
            } for l in links]),
            use_container_width=True, hide_index=True)
    else:
        st.warning(t("This plan isn't linked to any PO yet."))

    plan_id = int(plan["id"])
    editing = st.session_state.get(SK.CP_EDIT_ID) == plan_id
    if not editing:
        if st.button(t("Edit linked POs"), key=f"cp_edit_{plan_id}"):
            st.session_state[SK.CP_EDIT_ID] = plan_id
            # Seed the editor with the plan's current PC No.s.
            st.session_state["cp_edit_pcs"] = sorted(
                {l.get("pc_no", "") for l in links if l.get("pc_no")})
            st.session_state.pop("cp_edit_pos", None)
            fragment_rerun()
        return

    st.markdown(f"**{t('Edit linked POs')}**")
    pc_nos, po_nos, items = select_pos("cp_edit")
    rows = link_rows(pc_nos, po_nos, items)
    if rows:
        st.caption(t("Will link to:") + " " +
                   ", ".join(po_label(r["pc_no"], r["po_no"]) for r in rows[:12])
                   + (" …" if len(rows) > 12 else ""))
    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button(t("Save links"), type="primary", disabled=not rows,
                     use_container_width=True, key=f"cp_savelinks_{plan_id}"):
            store.set_links(plan_id, rows,
                            st.session_state.get(SK.USERNAME, ""))
            st.session_state[SK.CP_EDIT_ID] = None
            st.session_state[SK.CP_FLASH] = (
                "success", t("Linked POs updated."))
            fragment_rerun()
    with col_cancel:
        if st.button(t("Cancel"), use_container_width=True,
                     key=f"cp_cancel_{plan_id}"):
            st.session_state[SK.CP_EDIT_ID] = None
            fragment_rerun()


def _show_quantities(store, plan_id: int) -> None:
    df = store.list_demands(plan_id)
    if df.empty:
        st.info(t("This plan has no quantity breakdown."))
        return
    df = df.copy()
    df["diff"] = df["cut_qty"] - df["qty"]
    st.dataframe(
        df.rename(columns=_tr({
            "style": "Style", "color": "Color", "size": "Size",
            "qty": "Ordered", "cut_qty": "Cut", "diff": "Cut − Ordered",
        })),
        use_container_width=True, hide_index=True)
    over = int(df.loc[df["diff"] > 0, "diff"].sum())
    under = int(-df.loc[df["diff"] < 0, "diff"].sum())
    if over or under:
        st.caption(
            t("Overcut: {over:,} pcs · Short: {under:,} pcs — a marker ratio "
              "rarely divides the order exactly.").format(over=over, under=under))


def _show_materials(plan: dict) -> None:
    parsed = plan.get("parsed") or {}
    materials = parsed.get("materials") or []
    if not materials:
        st.info(t("No material blocks were found in this plan."))
        return
    for mat in materials:
        with st.expander(
                f"{mat.get('material') or '—'} — "
                f"{t('width')} {mat.get('width_cm') or '—'} cm · "
                f"{mat.get('n_markers') or 0} {t('markers')} · "
                f"{mat.get('total_tables') or 0} {t('tables')}",
                expanded=False):
            rows = []
            spreads = {s.get("marker_no"): s for s in mat.get("spreads", [])}
            for marker in mat.get("markers", []):
                no = marker.get("marker_no")
                spread = spreads.get(no, {})
                lines = spread.get("rows", [])
                ratio = " / ".join(
                    f"{c.get('size')}×{c.get('qty')}"
                    for c in marker.get("ratio", []))
                for line in (lines or [{}]):
                    rows.append({
                        _th("Marker"): no,
                        _th("Color"): line.get("color", ""),
                        _th("Ratio"): ratio,
                        _th("Plies"): line.get("plies"),
                        _th("Marker length (cm)"): _round(line.get("marker_length_cm")),
                        _th("Fabric (m)"): _round(line.get("fabric_length_m")),
                        _th("Efficiency %"): _round(line.get("efficiency_pct")),
                    })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True,
                             hide_index=True)
            st.caption(
                f"{t('File names')}: " + ", ".join(
                    (m.get("file_name") or "").split("\\")[-1]
                    for m in mat.get("markers", [])) or "—")


def _round(v, digits: int = 2):
    return None if v is None else round(float(v), digits)


def _show_files(store, plan: dict) -> None:
    plan_id = int(plan["id"])
    original = store.get_plan_file(plan_id)
    if original:
        fname, data = original
        st.download_button(
            f"⬇️ {t('Download original file')} ({fname})",
            data=data, file_name=fname, mime=XLSX_MIME,
            key=f"cp_dl_orig_{plan_id}", use_container_width=True)
    else:
        st.caption(t("The original file wasn't stored with this plan."))

    st.markdown("---")
    st.caption(t(
        "The standard version re-emits this plan in the house layout, with "
        "the Order demands block rebuilt from the linked PO(s) so it always "
        "reflects what was actually ordered."))
    if st.button(f"📄 {t('Build standard cut plan')}",
                 key=f"cp_std_{plan_id}", use_container_width=True):
        _build_standard_for_plan(store, plan)

    if st.session_state.get(f"cp_std_{plan_id}_bytes"):
        st.download_button(
            f"⬇️ {st.session_state[f'cp_std_{plan_id}_fname']}",
            data=st.session_state[f"cp_std_{plan_id}_bytes"],
            file_name=st.session_state[f"cp_std_{plan_id}_fname"],
            mime=XLSX_MIME, use_container_width=True,
            key=f"cp_std_dl_{plan_id}")


def _build_standard_for_plan(store, plan: dict) -> None:
    parsed = plan.get("parsed") or {}
    plan_id = int(plan["id"])
    links = plan.get("links") or []
    pc_nos = sorted({l.get("pc_no", "") for l in links if l.get("pc_no")})
    po_nos = sorted({l.get("po_no", "") for l in links if l.get("po_no")})

    items = load_sky_east_items(pc_nos)
    if not items.empty and po_nos:
        items = items[items["zalando_po"].astype(str).str.strip().isin(po_nos)]
    groups, colors, qty = demand_matrix(items)

    if not groups:
        # No PO data to rebuild from (unlinked, or the contract was deleted) —
        # fall back to the plan's own demand block so the export still works.
        groups, colors, qty = _demands_from_parsed(parsed)
        st.info(t("No PO quantities available — the plan's own Order demands "
                  "block was used instead."))

    header = plan_header_from_parsed(parsed)
    header["pc_summary"] = ", ".join(pc_nos)
    header["po_summary"] = ", ".join(po_nos)
    data = build_standard_cut_plan(
        header=header, groups=groups, colors=colors, demand_qty=qty,
        materials=parsed.get("materials") or [],
        sheet_name=plan.get("plan_name") or "Cut Plan")
    st.session_state[f"cp_std_{plan_id}_bytes"] = data
    st.session_state[f"cp_std_{plan_id}_fname"] = _std_filename(plan)


def _demands_from_parsed(parsed: dict):
    groups: dict[str, list[str]] = {}
    colors: list[str] = []
    qty: dict[tuple[str, str, str], int] = {}
    for d in parsed.get("demands", []):
        style, color, size = d.get("style", ""), d.get("color", ""), d.get("size", "")
        groups.setdefault(style, [])
        if size not in groups[style]:
            groups[style].append(size)
        if color not in colors:
            colors.append(color)
        qty[(style, color, size)] = qty.get((style, color, size), 0) + int(d.get("qty") or 0)
    return list(groups.items()), colors, qty


def _std_filename(plan: dict) -> str:
    base = (plan.get("plan_name") or f"cut_plan_{plan.get('id')}").strip()
    safe = "".join(ch for ch in base if ch not in '\\/:*?"<>|').strip() or "cut_plan"
    return f"{safe}_CutPlan_standard.xlsx"
