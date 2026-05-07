"""Sky East missing-fields section — editor grid, auto-fill, and section B."""
from __future__ import annotations

import base64

import streamlit as st

from ui.session_keys import SK
from ui.shared import build_image_cache_for_ids, _th, _tr
from ui.stores import get_sky_east_store


def _se_missing_style_photo_map(df) -> dict[str, str]:
    """Return {style -> base64-image-data-url} for styles that have pictures."""
    style_to_pid: dict[str, str] = {}
    if "picture_id" in df.columns:
        for _, r in df.iterrows():
            s   = str(r.get("style", "") or "").strip()
            pid = str(r.get("picture_id", "") or "").strip()
            if s and pid and s not in style_to_pid:
                style_to_pid[s] = pid
    all_pids = list(set(style_to_pid.values()))
    loaded   = build_image_cache_for_ids(all_pids)
    return {
        s: f"data:image/png;base64,{base64.b64encode(loaded[pid]).decode()}"
        for s, pid in style_to_pid.items()
        if pid in loaded
    }


def _se_missing_apply_auto_fill(df_a, fl, pl):
    """Apply Fabric / Progress lookups to df_a in-place; return (orig_a, auto_mask)."""
    orig_a = df_a.copy()
    for idx, row in df_a.iterrows():
        style = str(row.get("style", "") or "").strip()
        color = str(row.get("color_name", "") or "").strip()
        if fl and not str(row.get("fabric_item_no", "") or "").strip():
            if isinstance(fl, dict):
                fp_list = fl.get(style)
                if fp_list:
                    df_a.at[idx, "fabric_item_no"] = fp_list[0].hhn_no or ""
            else:
                parts = fl.get_fabric_parts(style)
                if parts:
                    df_a.at[idx, "fabric_item_no"] = parts[0][1]
        if pl and not str(row.get("contract_no", "") or "").strip():
            cno = pl.get_contract_no(
                style, color, str(row.get("zalando_po", "") or "").strip(),
                pc_no=str(row.get("pc_no", "") or "").strip())
            if cno:
                df_a.at[idx, "contract_no"] = cno
    af_mask = (
        (df_a["fabric_item_no"].fillna("").str.strip()
         != orig_a["fabric_item_no"].fillna("").str.strip()) |
        (df_a["contract_no"].fillna("").str.strip()
         != orig_a["contract_no"].fillna("").str.strip())
    )
    return orig_a, af_mask


def _se_missing_show_autofill_controls(df_a, orig_a, af_mask, fl, pl) -> None:
    """Render the lookup-driven preview + 'Auto-fill & Save' button."""
    if not (fl or pl):
        return
    hint = [n for n, v in [("Fabric lookup", fl), ("Progress lookup", pl)] if v]
    auto_resolvable = int(af_mask.sum())
    st.info(f"Reference files in session: **{', '.join(hint)}**. "
            f"**{auto_resolvable}** item(s) can be auto-filled.")

    if auto_resolvable:
        preview = df_a[af_mask][["pc_no", "style", "color_name",
                                 "fabric_item_no", "contract_no"]].copy()
        orig_vals = orig_a[af_mask][["fabric_item_no", "contract_no"]]
        preview.insert(3, "Fabric No. (was)",       orig_vals["fabric_item_no"].values)
        preview.insert(5, "HHN Contract No. (was)", orig_vals["contract_no"].values)
        st.dataframe(preview.rename(columns=_tr({
            "pc_no": "PC No.", "style": "Style", "color_name": "Color",
            "fabric_item_no": "Fabric No. -> (new)",
            "contract_no": "HHN Contract No. -> (new)",
        })), use_container_width=True, hide_index=True)

    if st.button("Auto-fill & Save", type="primary", key="se_missing_autofill"):
        store = get_sky_east_store()
        saved = sum(
            store.update_item_fields(
                str(row["pc_no"]), str(row["style"]), str(row["color_name"]),
                str(row["zalando_po"]),
                str(row.get("fabric_item_no", "") or ""),
                str(row.get("contract_no", "") or ""),
            )
            for _, row in df_a[af_mask].iterrows()
        )
        st.success(f"Auto-filled and saved {saved} item(s).")
        st.rerun()


def _se_missing_edit_grid(df_a, pid_b64_a: dict) -> None:
    """Render the editable grid + 'Save Changes' button for Section A."""
    st.caption("Edit cells below and click **Save Changes**:")

    pc_opts = ["All"] + sorted(df_a["pc_no"].unique().tolist())
    sel_pc  = st.selectbox("Filter by PC No.", pc_opts, key="se_missing_pc_filter")
    edit_df = df_a[df_a["pc_no"] == sel_pc].copy() if sel_pc != "All" else df_a.copy()

    disp_cols = [c for c in
                 ["pc_no", "zalando_po", "style", "color_name", "brand",
                  "fabric_item_no", "contract_no", "ex_fty_date", "total_qty"]
                 if c in edit_df.columns]
    edit_df = edit_df[disp_cols].copy()
    drename = _tr({
        "pc_no": "PC No.", "zalando_po": "PO No.", "style": "Style",
        "color_name": "Color", "brand": "Brand",
        "fabric_item_no": "Fabric No.", "contract_no": "HHN Contract No.",
        "ex_fty_date": "Ex-Fty", "total_qty": "Units",
    })
    edit_display = edit_df.rename(columns=drename)
    _style_col  = _th("Style")
    _photo_col  = _th("Photo")
    _fabno_col  = _th("Fabric No.")
    _cno_col    = _th("HHN Contract No.")
    if pid_b64_a and _style_col in edit_display.columns:
        edit_display.insert(
            edit_display.columns.get_loc(_style_col) + 1,
            _photo_col,
            edit_display[_style_col].map(lambda s: pid_b64_a.get(str(s).strip())),
        )
    _disabled = [drename.get(c, c) for c in
                 ["pc_no", "zalando_po", "style", "color_name", "brand",
                  "ex_fty_date", "total_qty"]]
    if pid_b64_a:
        _disabled.append(_photo_col)
    edited = st.data_editor(
        edit_display,
        width="stretch", hide_index=True,
        disabled=_disabled,
        column_config={
            _photo_col: st.column_config.ImageColumn(_th("Photo"), width="small"),
            _fabno_col: st.column_config.TextColumn(_fabno_col, help="e.g. HHN-JA-01715"),
            _cno_col:   st.column_config.TextColumn(_cno_col),
        },
        key="se_missing_editor",
    )
    if st.button("Save Changes", key="se_missing_save"):
        store = get_sky_east_store()
        rev = {v: k for k, v in drename.items()}
        ei  = edited.drop(columns=["Photo"], errors="ignore").rename(columns=rev)
        saved = sum(
            store.update_item_fields(
                str(r.get("pc_no", "")), str(r.get("style", "")),
                str(r.get("color_name", "")), str(r.get("zalando_po", "")),
                str(r.get("fabric_item_no", "")), str(r.get("contract_no", "")),
            )
            for _, r in ei.iterrows()
        )
        (st.success(f"Updated {saved} item(s).") if saved
         else st.warning("No rows updated."))
        if saved:
            st.rerun()


def _se_missing_section_b(df_b, pid_b64_b: dict) -> None:
    """Render Section B: read-only items missing composition / cuttable width."""
    st.markdown("#### Missing Composition or Cuttable Width")
    st.caption(
        "These items have a Fabric No. but the **Fabric DB** does not have their composition "
        "or cuttable width. Import the 面料统计表 in the **Fabric DB** tab to resolve them."
    )
    if df_b.empty:
        st.success("No items missing composition or cuttable width.")
        return
    show_b = [c for c in
              ["pc_no", "style", "color_name", "brand", "fabric_item_no",
               "composition_en", "cuttable_width_cm"]
              if c in df_b.columns]
    df_b_disp = df_b[show_b].rename(columns=_tr({
        "pc_no": "PC No.", "style": "Style", "color_name": "Color", "brand": "Brand",
        "fabric_item_no": "Fabric No.", "composition_en": "Composition",
        "cuttable_width_cm": "Cuttable Width (cm)",
    }))
    b_col_cfg = {}
    _sc = _th("Style")
    if pid_b64_b and _sc in df_b_disp.columns:
        _pc = _th("Photo")
        df_b_disp.insert(
            df_b_disp.columns.get_loc(_sc) + 1,
            _pc,
            df_b_disp[_sc].map(lambda s: pid_b64_b.get(str(s).strip())),
        )
        b_col_cfg[_pc] = st.column_config.ImageColumn(_th("Photo"), width="small")
    st.dataframe(df_b_disp, width="stretch", hide_index=True,
                 column_config=b_col_cfg)


def _show_se_missing_fields_section(missing_df) -> None:
    """Let users manually fill in missing fabric_item_no / contract_no; shows fabric DB gaps."""
    st.subheader("Items with Missing Fields")

    if missing_df.empty:
        st.success("All items are complete -- no missing fields.")
        return

    for _col in ("composition_en", "cuttable_width_cm"):
        if _col not in missing_df.columns:
            missing_df[_col] = None

    grp_a_mask = (
        missing_df["fabric_item_no"].fillna("").str.strip().eq("") |
        missing_df["contract_no"].fillna("").str.strip().eq("")
    )
    grp_b_mask = ~grp_a_mask & (
        missing_df["composition_en"].fillna("").str.strip().eq("") |
        missing_df["cuttable_width_cm"].fillna(0).eq(0)
    )
    df_a = missing_df[grp_a_mask].copy()
    df_b = missing_df[grp_b_mask].copy()

    pid_b64_a = _se_missing_style_photo_map(df_a)
    pid_b64_b = _se_missing_style_photo_map(df_b)

    if df_a.empty:
        st.success("All items have Fabric No. and HHN Contract No.")
    else:
        fl = st.session_state.get(SK.SE_FABRIC_LOOKUP)
        pl = st.session_state.get(SK.SE_PROGRESS_LKUP)
        orig_a, af_mask = _se_missing_apply_auto_fill(df_a, fl, pl)
        _se_missing_show_autofill_controls(df_a, orig_a, af_mask, fl, pl)
        st.divider()
        _se_missing_edit_grid(df_a, pid_b64_a)

    st.divider()
    _se_missing_section_b(df_b, pid_b64_b)
