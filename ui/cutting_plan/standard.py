"""Cutting Plan → Standard output.

Pick PO(s), get the cutting plan in the house layout.  The Order demands block
always comes from the PO — that is the point of standardising: whatever format
the factory's own plan arrived in, the quantities on the sheet are the ordered
ones.  Marker/spreading/solution blocks are filled in from the cut plans linked
to those POs, or left as an empty scaffold when there aren't any yet.
"""
from __future__ import annotations

import streamlit as st

from po_extractor.exporters.cutting_plan_export import (
    build_standard_cut_plan, plan_header_from_parsed, today_header,
)
from ui.i18n import t
from ui.session_keys import SK
from ui.shared import guard_multiselect_state
from ui.stores import get_cutting_plan_store
from ui.cutting_plan._shared import (
    XLSX_MIME, cleanup_color_map, demand_frame, demand_matrix,
    pdf_export_block, safe_filename, select_pos,
)


def show_standard_section() -> None:
    st.caption(t(
        "Choose the PO(s) and download the cutting plan in the standard "
        "layout. Quantities come from the PO; marker ratios, plies, "
        "efficiency and fabric length come from the cut plan(s) linked to "
        "those POs."
    ))

    selection = select_pos("cp_std")
    pc_nos, po_nos, styles, items = selection
    if not pc_nos or items is None or items.empty:
        return

    groups, colors, qty = demand_matrix(items)
    if not groups:
        st.warning(t("The selected PO(s) have no size quantities."))
        return

    df = demand_frame(groups, colors, qty)
    st.markdown(f"**{t('Order demands (from the PO)')}**")
    st.dataframe(df, use_container_width=True, hide_index=True)

    store = get_cutting_plan_store()
    linked = store.plans_for_pos(pc_nos=pc_nos, po_nos=po_nos, styles=styles)
    plan_ids: list[int] = []
    if linked.empty:
        st.info(t(
            "No cut plan is linked to this selection yet. The download will "
            "use the standard layout with the marker sections left blank for "
            "the cutting room to fill in."))
    else:
        options = linked.drop_duplicates(subset=["plan_id"])
        labels = {
            int(r["plan_id"]): f"#{int(r['plan_id'])} — {r['plan_name']} "
                               f"({r.get('colors') or '—'}, "
                               f"{int(r.get('order_qty') or 0):,} pcs)"
            for _, r in options.iterrows()
        }
        ids = list(labels)
        guard_multiselect_state("cp_std_plans", ids)
        st.session_state.setdefault("cp_std_plans", ids)
        plan_ids = st.multiselect(
            t("Cut plan(s) to include"), ids, key="cp_std_plans",
            format_func=lambda i: labels.get(int(i), str(i)),
            help=t("Each plan contributes its own material blocks. Clear the "
                   "selection to produce a blank standard template."))

    clean = st.checkbox(
        t("Clean for the cutting room (Chinese labels, marker names only)"),
        value=True, key="cp_std_clean",
        help=t("Replaces the English headings with the Chinese the cutting "
               "room reads and reduces marker paths to the marker name — the "
               "cleanup that used to be a hand-run Excel macro. Untick to keep "
               "the raw English layout (that copy can be re-uploaded and "
               "re-parsed; the cleaned one cannot)."))

    if st.button(f"📄 {t('Build standard cut plan')}", type="primary",
                 use_container_width=True, key="cp_std_build"):
        _build(store, plan_ids, pc_nos, po_nos, styles, items,
               groups, colors, qty, clean=clean)

    if st.session_state.get(SK.CP_STD_BYTES):
        st.download_button(
            f"⬇️ {st.session_state.get(SK.CP_STD_FNAME)}",
            data=st.session_state[SK.CP_STD_BYTES],
            file_name=st.session_state[SK.CP_STD_FNAME],
            mime=XLSX_MIME, use_container_width=True, key="cp_std_dl")
        pdf_export_block(
            st.session_state[SK.CP_STD_BYTES],
            str(st.session_state[SK.CP_STD_FNAME]).removesuffix(".xlsx"),
            key="cp_std")


def _build(store, plan_ids: list[int], pc_nos: list[str], po_nos: list[str],
           styles: list[str], items, groups, colors, qty,
           clean: bool = True) -> None:
    materials: list[dict] = []
    newest_parsed: dict | None = None
    for pid in plan_ids:
        rec = store.get_plan(int(pid))
        if not rec:
            continue
        parsed = rec.get("parsed") or {}
        if newest_parsed is None:
            newest_parsed = parsed
        materials.extend(parsed.get("materials") or [])

    order_name = " + ".join(pc_nos) if pc_nos else "Cut Plan"
    if newest_parsed:
        header = plan_header_from_parsed(newest_parsed)
        header["order_name"] = order_name
    else:
        styles = [{"name": s, "file": ""} for s, _sizes in groups]
        buyer = ""
        if items is not None and not items.empty and "brand" in items.columns:
            brands = [b for b in items["brand"].dropna().unique().tolist() if b]
            buyer = ", ".join(map(str, brands[:3]))
        header = today_header(order_name, client=buyer, styles=styles)
    header["pc_summary"] = ", ".join(pc_nos)
    header["po_summary"] = ", ".join(po_nos) if po_nos else t("All POs")
    header["style_summary"] = (", ".join(styles) if styles
                               else ", ".join(s for s, _sizes in groups))

    data = build_standard_cut_plan(
        header=header, groups=groups, colors=colors, demand_qty=qty,
        materials=materials, sheet_name=order_name, clean=clean,
        color_map=cleanup_color_map() if clean else None)

    st.session_state[SK.CP_STD_BYTES] = data
    st.session_state[SK.CP_STD_FNAME] = (
        f"{safe_filename(order_name)}_CutPlan_standard.xlsx")
    # A previously built PDF belongs to the old workbook — drop it so the
    # download button can't hand back a stale sheet.
    st.session_state.pop("cp_std_pdf_bytes", None)
    if not materials:
        st.success(t("Standard template built (marker sections blank)."))
    else:
        st.success(t("Standard cut plan built from {n} linked plan(s).")
                   .format(n=len(plan_ids)))
