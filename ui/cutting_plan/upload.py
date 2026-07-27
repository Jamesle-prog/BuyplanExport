"""Cutting Plan → Upload & Link.

The plan file itself is produced outside the app (Optitex and friends); this
screen reads it, shows what it found, and records which PO(s) it covers.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from po_extractor.parsers.cutting_plan import CuttingPlanParseError, parse_cut_plan
from po_extractor.store.cutting_plan_store import consumption, summarise_plan
from ui.i18n import t
from ui.session_keys import SK
from ui.shared import _th, fragment_rerun
from ui.stores import get_cutting_plan_store
from ui.cutting_plan._shared import (
    demand_frame, demand_matrix, link_rows, po_label, select_pos,
)


def _files_signature(files) -> str:
    return "|".join(f"{f.name}:{f.size}" for f in (files or []))


def show_upload_section() -> None:
    st.markdown(f"**{t('Cut plan file(s)')}**")
    st.caption(t(
        "Upload the cutting plan produced by the marker software (Optitex "
        "Cut Plan export, .xlsx). Marker ratios, plies, efficiency and fabric "
        "length are read from the file — nothing is recalculated here."
    ))
    files = st.file_uploader(
        t("Upload cut plan file(s)"),
        type=["xlsx", "xlsm"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="cp_uploader",
    )

    sig = _files_signature(files)
    if sig != st.session_state.get(SK.CP_PARSE_SIG):
        st.session_state[SK.CP_PARSED] = _parse_all(files)
        st.session_state[SK.CP_PARSE_SIG] = sig

    parsed = st.session_state.get(SK.CP_PARSED) or []
    if not parsed:
        if files:
            st.error(t("None of the uploaded files could be read as a cut plan."))
        return

    for entry in parsed:
        _show_parsed_plan(entry)

    ok = [e for e in parsed if e.get("plan")]
    if not ok:
        return

    st.divider()
    st.markdown(f"**{t('Link to PO(s) and styles')}**")
    st.caption(t(
        "A cut plan usually covers several POs at once, and only some of the "
        "styles inside them. Pick everything it covers — the link is what "
        "makes the plan show up against those POs and styles."
    ))
    selection = select_pos("cp_up")
    items = selection.items

    if items is not None and not items.empty:
        groups, colors, qty = demand_matrix(items)
        df = demand_frame(groups, colors, qty)
        if not df.empty:
            with st.expander(t("PO quantities for the selection"),
                             expanded=False):
                st.dataframe(df, use_container_width=True, hide_index=True)
            _show_coverage(ok, groups, colors, qty)

    links = link_rows(selection)
    if links:
        st.caption(t("Will link to:") + " " +
                   ", ".join(po_label(l["pc_no"], l["po_no"], l["style"])
                             for l in links[:10])
                   + (" …" if len(links) > 10 else ""))

    notes = st.text_input(t("Notes (optional)"), key="cp_up_notes")

    disabled = not links
    if disabled:
        st.info(t("Select at least one PC No. to link the plan to."))
    if st.button(t("Save cut plan(s)"), type="primary",
                 use_container_width=True, key="cp_save",
                 disabled=disabled):
        _save(ok, links, notes, selection.styles)


def _parse_all(files) -> list[dict]:
    out: list[dict] = []
    for f in files or []:
        try:
            data = f.getvalue()
        except Exception:                              # noqa: BLE001
            f.seek(0)
            data = f.read()
        entry: dict = {"name": f.name, "bytes": data}
        try:
            entry["plan"] = parse_cut_plan(f)
        except CuttingPlanParseError as exc:
            entry["error"] = str(exc)
        except Exception as exc:                       # noqa: BLE001 - user file
            entry["error"] = f"{type(exc).__name__}: {exc}"
        out.append(entry)
    return out


def _show_parsed_plan(entry: dict) -> None:
    name = entry.get("name", "?")
    if entry.get("error"):
        st.error(f"**{name}** — {entry['error']}")
        return

    plan = entry["plan"]
    summary = summarise_plan(plan)
    dupe = get_cutting_plan_store().find_by_hash(entry.get("bytes") or b"")

    with st.expander(f"✅ {name} — {summary['plan_name'] or '—'}", expanded=True):
        if dupe:
            st.warning(t(
                "This exact file was already uploaded on {when} by {who} "
                "(plan #{id}). Saving again creates a second copy."
            ).format(when=dupe.get("uploaded_at", "?"),
                     who=dupe.get("uploaded_by") or "?",
                     id=dupe.get("id")))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("Order qty"), f"{summary['order_qty']:,}")
        c2.metric(t("Cut qty"), f"{summary['cut_qty']:,}",
                  delta=(summary["cut_qty"] - summary["order_qty"]) or None)
        c3.metric(t("Markers"), summary["total_markers"])
        c4.metric(t("Tables"), summary["total_tables"])

        st.caption(
            f"{t('Styles')}: {summary['styles'] or '—'} · "
            f"{t('Colors')}: {summary['colors'] or '—'} · "
            f"{t('Operator')}: {summary['operator'] or '—'} · "
            f"{t('Client')}: {summary['client'] or '—'} · "
            f"{t('Plan date')}: {summary['plan_date'] or '—'}"
        )

        # Per fabric, never combined: shell and lining are different fabrics
        # at different widths, so one total metre count says nothing useful.
        mats = pd.DataFrame([{
            _th("Fabric"): m.get("material"),
            _th("Width (cm)"): m.get("width_cm"),
            _th("Markers"): m.get("n_markers"),
            _th("Tables"): m.get("total_tables"),
            _th("Plies"): sum(int(line.get("plies") or 0)
                              for s in m.get("spreads", [])
                              for line in s.get("rows", [])) or None,
            _th("Pieces"): m.get("cut_qty"),
            _th("Fabric (m)"): (round(m["fabric_length_m"], 2)
                                if m.get("fabric_length_m") else None),
            _th("m/unit"): consumption(m.get("fabric_length_m"),
                                       summary["cut_qty"]),
            _th("m/piece"): consumption(m.get("fabric_length_m"),
                                        m.get("cut_qty")),
            _th("Efficiency %"): (round(m["total_efficiency_pct"], 2)
                                  if m.get("total_efficiency_pct") else None),
            _th("Cost"): (round(m["total_cost"], 2)
                          if m.get("total_cost") else None),
        } for m in plan.get("materials", [])])
        if not mats.empty:
            st.dataframe(mats, use_container_width=True, hide_index=True)


def _show_coverage(entries: list[dict], groups, colors, qty) -> None:
    """Compare each plan's demand block against the selected POs' quantities.

    Purely informational: cut plans legitimately cover more or fewer POs than
    the ones being linked, and overcut is normal. It just makes an obvious
    mismatch (wrong plan picked) visible before saving.
    """
    po_total = sum(qty.values())
    if not po_total:
        return
    # The PO total counts each style separately; a plan's order_qty is
    # per-style, so compare against the same shape.
    per_style: dict[str, int] = {}
    for (style, _c, _s), n in qty.items():
        per_style[style] = per_style.get(style, 0) + n
    po_per_style = max(per_style.values()) if per_style else 0

    for entry in entries:
        plan_qty = summarise_plan(entry["plan"])["order_qty"]
        if not plan_qty or not po_per_style:
            continue
        if plan_qty == po_per_style:
            st.success(
                f"✅ {entry['name']}: " + t(
                    "plan quantity matches the selected PO(s) ({n:,} pcs)."
                ).format(n=plan_qty))
        else:
            st.info(
                f"ℹ️ {entry['name']}: " + t(
                    "plan is for {plan:,} pcs, the selected PO(s) total "
                    "{po:,} pcs per style. Check this is the right plan."
                ).format(plan=plan_qty, po=po_per_style))


def _save(entries: list[dict], links: list[dict], notes: str,
          styles: list[str] | None = None) -> None:
    store = get_cutting_plan_store()
    saved = 0
    for entry in entries:
        try:
            store.save_plan(
                entry["plan"],
                source_file=entry.get("name", ""),
                file_bytes=entry.get("bytes"),
                uploaded_by=st.session_state.get(SK.USERNAME, ""),
                notes=notes or "",
                links=links,
            )
            saved += 1
        except Exception as exc:                       # noqa: BLE001
            st.error(f"{entry.get('name')}: {type(exc).__name__}: {exc}")
    if saved:
        n_pos = len({(l["pc_no"], l["po_no"]) for l in links})
        n_styles = len({l["style"] for l in links if l["style"]})
        st.session_state[SK.CP_FLASH] = (
            "success",
            t("Saved {n} cut plan(s), linked to {m} PO(s) and "
              "{s} style(s).").format(n=saved, m=n_pos, s=n_styles),
        )
        # Clear the staged uploads so a rerun doesn't offer to save them twice.
        st.session_state[SK.CP_PARSED] = []
        st.session_state[SK.CP_PARSE_SIG] = None
        fragment_rerun()
