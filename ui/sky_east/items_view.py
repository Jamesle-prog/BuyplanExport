"""Sky East items display and fabric enrichment panels.

Missing-fields editor lives in ui/sky_east/_missing.py.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.session_keys import SK
from ui.shared import XLSX_MIME, CSV_MIME, _th, _tr, build_image_cache_for_ids, persisted_download
from ui.stores import get_store, get_sky_east_store, get_fabric_master_store
from ui.sky_east._shared import live_label, _get_dual_header, _write_dual_header_excel, _write_wash_label_excel
from ui.sky_east._missing import _show_se_missing_fields_section  # re-export


# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------

def _show_se_results(results: list, image_cache: dict):
    """Render per-PC summary cards with amendment diffs."""
    st.divider()
    st.subheader("Processing Results")

    for r in results:
        pc_no     = r["pc_no"]
        new_items = r["new_items"]
        upd_items = r["updated_items"]
        dup_items = r["duplicate_items"]

        total = len(new_items) + len(upd_items) + len(dup_items)
        label = (
            f"PC {pc_no}  --  "
            f"{'New ' + str(len(new_items)) if new_items else ''}"
            f"{'  Amended ' + str(len(upd_items)) if upd_items else ''}"
            f"{'  Duplicate(s) ' + str(len(dup_items)) if dup_items else ''}"
            f"  ({total} item(s) total)"
        ).strip("  ")

        with st.expander(label, expanded=bool(upd_items)):
            if new_items:
                st.markdown(f"**{len(new_items)} New Item(s)**")
                rows = [{"Style": s, "Color": c, "Zalando PO": po}
                        for s, c, po in new_items]
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                             use_container_width=True)

            if upd_items:
                st.markdown(f"**{len(upd_items)} Amended Item(s)**")
                sz_keys = ["XS", "S", "M", "L", "XL", "2XL"]
                for row in upd_items:
                    if len(row) == 6:
                        style, color, po, old_sz, new_sz, changed = row
                    else:
                        style, color, po, old_sz, new_sz = row
                        changed = {}

                    st.markdown(f"- **{style}** · {color} · PO `{po}`")

                    if changed.get("sizes") or not changed:
                        diff_cols = st.columns(len(sz_keys) + 1)
                        diff_cols[0].markdown("&nbsp;", unsafe_allow_html=True)
                        for i, sk in enumerate(sz_keys):
                            diff_cols[i + 1].markdown(f"**{sk}**")

                        old_cols = st.columns(len(sz_keys) + 1)
                        old_cols[0].markdown("*Before*")
                        for i, sk in enumerate(sz_keys):
                            v = old_sz.get(sk, 0) or 0
                            old_cols[i + 1].markdown(str(v))

                        new_cols = st.columns(len(sz_keys) + 1)
                        new_cols[0].markdown("**After**")
                        for i, sk in enumerate(sz_keys):
                            ov = old_sz.get(sk, 0) or 0
                            nv = new_sz.get(sk, 0) or 0
                            delta = nv - ov
                            cell = f"**{nv}**"
                            if delta > 0:
                                cell += f' <span style="color:green">+{delta}</span>'
                            elif delta < 0:
                                cell += f' <span style="color:red">{delta}</span>'
                            new_cols[i + 1].markdown(cell, unsafe_allow_html=True)

                    non_size = {k: v for k, v in changed.items() if k != "sizes"}
                    if non_size:
                        field_labels = {"total_qty": "Total Qty", "fob_usd": "FOB (USD)"}
                        change_parts = []
                        for field, (old_v, new_v) in non_size.items():
                            lbl = field_labels.get(field, field)
                            change_parts.append(f"{lbl}: **{old_v}** -> **{new_v}**")
                        st.markdown(
                            "Changed: " + " &nbsp;·&nbsp; ".join(change_parts),
                            unsafe_allow_html=True,
                        )

                    st.markdown("---")

            if dup_items:
                st.markdown(
                    f"{len(dup_items)} item(s) were identical to stored "
                    "records and were skipped."
                )

            if image_cache:
                contracts = st.session_state.get(SK.SE_CONTRACTS) or []
                pc_items = [
                    item
                    for c in contracts if c.pc_no == pc_no
                    for item in c.items
                    if item.picture_id and item.picture_id in image_cache
                ]
                style_pics: dict[str, list[str]] = {}
                for item in pc_items:
                    if item.style not in style_pics:
                        style_pics[item.style] = []
                    if item.picture_id not in style_pics[item.style]:
                        if len(style_pics[item.style]) < 2:
                            style_pics[item.style].append(item.picture_id)

                styles_with_pics = [(s, ids) for s, ids in style_pics.items() if ids]
                if styles_with_pics:
                    st.markdown(f"**Style Photos ({len(styles_with_pics)} style(s))**")
                    STYLES_PER_ROW = 3
                    for row_start in range(0, len(styles_with_pics), STYLES_PER_ROW):
                        batch = styles_with_pics[row_start: row_start + STYLES_PER_ROW]
                        cols = st.columns(STYLES_PER_ROW)
                        for ci, (style, pic_ids) in enumerate(batch):
                            with cols[ci]:
                                st.caption(f"**{style}**")
                                img_cols = st.columns(len(pic_ids))
                                for j, pid in enumerate(pic_ids):
                                    img_bytes = image_cache.get(pid)
                                    if img_bytes:
                                        lbl = "Front" if j == 0 else "Back"
                                        img_cols[j].image(img_bytes,
                                                          caption=lbl,
                                                          use_container_width=True)


# ---------------------------------------------------------------------------
# Fabric master helpers
# ---------------------------------------------------------------------------

def _fabric_master_has_data() -> bool:
    """Live check whether the fabric master table has any rows."""
    return get_fabric_master_store().count() > 0


def _enrich_items_df(df_items):
    """Add fabric master columns to df_items; returns enriched copy."""
    fm_store = get_fabric_master_store()
    df = df_items.copy()

    fl = st.session_state.get(SK.SE_FABRIC_LOOKUP)
    if fl is not None and "fabric_item_no" in df.columns and "style" in df.columns:
        def _fill_hhn(row):
            fno = str(row.get("fabric_item_no", "") or "").strip()
            if fno and fno.lower() not in ("", "none", "nan"):
                return fno
            style = str(row.get("style", "")).strip()
            if isinstance(fl, dict):
                fp_list = fl.get(style)
                return fp_list[0].hhn_no if fp_list else fno
            else:
                parts = fl.get_fabric_parts(style)
                return parts[0][1] if parts else fno
        df["fabric_item_no"] = df.apply(_fill_hhn, axis=1)

    pl = st.session_state.get(SK.SE_PROGRESS_LKUP)
    if pl is not None and "contract_no" in df.columns and "style" in df.columns:
        def _fill_cno(row):
            cno = str(row.get("contract_no", "") or "").strip()
            if cno and cno.lower() not in ("", "none", "nan"):
                return cno
            return pl.get_contract_no(
                str(row.get("style", "")).strip(),
                str(row.get("color_name", "")).strip(),
            ) or cno
        df["contract_no"] = df.apply(_fill_cno, axis=1)

    if _fabric_master_has_data() and "fabric_item_no" in df.columns:
        unique_nos = df["fabric_item_no"].dropna().unique().tolist()
        cache = fm_store.get_batch_enrichment(unique_nos)

        def _get(fabric_no, field):
            if not fabric_no:
                return None
            rec = cache.get(str(fabric_no).strip())
            return rec.get(field) if rec else None

        df["fabric_display_key"] = df["fabric_item_no"].map(lambda x: (_get(x, "display_key") or None))
        df["composition_en"]     = df["fabric_item_no"].map(lambda x: _get(x, "composition_en"))
        df["cuttable_width_cm"]  = df["fabric_item_no"].map(lambda x: _get(x, "cuttable_width_cm"))
        df["shrinkage_rate"]     = df["fabric_item_no"].map(lambda x: _get(x, "shrinkage_rate"))
        df["short_rate"]         = df["fabric_item_no"].map(lambda x: _get(x, "short_rate"))
    else:
        df["fabric_display_key"] = None
        df["composition_en"]     = None
        df["cuttable_width_cm"]  = None
        df["shrinkage_rate"]     = None
        df["short_rate"]         = None
    return df


def _build_items_display_df(df_items):
    """Enrich df_items and return (display_df, col_cfg) for the UI table."""
    df = _enrich_items_df(df_items)

    _fabric_slots: list[int] = []
    if "style" in df.columns:
        styles = df["style"].dropna().unique().tolist()
        fp_map = get_store().load_fabric_parts_for_styles(styles, source="sky_east")
        if not fp_map:
            fp_map = get_store().load_fabric_parts_for_styles(styles)

        all_hhns = [p.hhn_no for parts in fp_map.values() for p in parts if p.hhn_no]
        fm_cache = get_fabric_master_store().get_batch_enrichment(all_hhns) if all_hhns else {}

        max_slots = min(max((len([p for p in parts if p.hhn_no])
                             for parts in fp_map.values()), default=0), 4)
        if max_slots == 0:
            max_slots = 1

        for slot in range(1, max_slots + 1):
            idx = slot - 1

            def _code_for_slot(style, _idx=idx):
                parts = [p for p in fp_map.get(str(style).strip(), []) if p.hhn_no]
                if _idx >= len(parts):
                    return ""
                p = parts[_idx]
                return f"{p.hhn_no} ({p.body_part})" if p.body_part else p.hhn_no

            def _key_for_slot(style, _idx=idx):
                parts = [p for p in fp_map.get(str(style).strip(), []) if p.hhn_no]
                if _idx >= len(parts):
                    return ""
                dk = (fm_cache.get(parts[_idx].hhn_no) or {}).get("display_key", "")
                return dk if dk else "NA"

            df[f"fabric_code_{slot}"] = df["style"].map(_code_for_slot)
            df[f"fabric_key_{slot}"]  = df["style"].map(_key_for_slot)

        _fabric_slots = list(range(1, max_slots + 1))

    size_cols = [c for c in ["xs", "s", "m", "l", "xl", "xxl"] if c in df.columns]

    _fabric_slot_cols = []
    for _s in _fabric_slots if "style" in df.columns else []:
        if f"fabric_code_{_s}" in df.columns:
            _fabric_slot_cols.append(f"fabric_code_{_s}")
        if f"fabric_key_{_s}" in df.columns:
            _fabric_slot_cols.append(f"fabric_key_{_s}")

    show_cols = [c for c in
                 ["pc_no", "contract_no", "style", "color_name", "brand", "zalando_po",
                  "config_sku", "article_name", "colour_code", "total_qty", *size_cols,
                  "ex_fty_date", *_fabric_slot_cols]
                 if c in df.columns]

    rename_map = {c: live_label(c, c) for c in show_cols}
    rename_map["zalando_po"]   = _th(live_label("po_number", "PO No."))
    rename_map["pc_no"]        = _th(live_label("pc_no", "PC No."))
    rename_map["contract_no"]  = _th("HHN Contract No.")
    rename_map["colour_code"]  = _th("Color Code")
    rename_map["total_qty"]    = _th("Total Qty")
    rename_map["ex_fty_date"]  = _th("Ex-Fty")
    rename_map["color_name"]   = _th("Color")
    rename_map["brand"]        = _th("Brand")
    rename_map["style"]        = _th("Style")
    rename_map["article_name"] = _th("Article Name")
    rename_map["config_sku"]   = _th("Config SKU")
    for _s in (_fabric_slots if "style" in df.columns else []):
        rename_map[f"fabric_code_{_s}"] = _th(f"Fabric {_s}")
        rename_map[f"fabric_key_{_s}"]  = _th(f"综合标识 Key {_s}")

    col_cfg = {}
    for _s in (_fabric_slots if "style" in df.columns else []):
        col_cfg[_th(f"Fabric {_s}")]       = st.column_config.TextColumn(width="medium")
        col_cfg[_th(f"综合标识 Key {_s}")] = st.column_config.TextColumn(width="large")

    return df[show_cols].rename(columns=rename_map), col_cfg
