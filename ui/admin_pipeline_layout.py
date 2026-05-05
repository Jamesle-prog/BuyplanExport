"""Admin: Per-pipeline buy-plan template layout JSON editor view."""
from __future__ import annotations

import json as _json

import pandas as pd
import streamlit as st

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def show_pipeline_layout_admin() -> None:
    """Admin UI: edit per-pipeline buy-plan template layout JSON configs.

    Lets admins tune column positions, header row, fabric-slot rows, and the
    Excel template file itself — for every client pipeline — without touching
    the codebase.
    """
    from po_extractor.exporters import template_config as tc

    st.subheader("🧩 Pipeline Buy-Plan Layouts")
    st.caption(
        "Per-client buy-plan template layouts. Edit the column mapping, "
        "data-start row, and fabric-slot rows for each pipeline — saved values "
        "override the auto-detection that runs against the .xlsx template. "
        "Leave a row blank to fall back to the template's auto-detected position."
    )

    pipelines = tc.list_pipelines()
    options = [f"{p.display_name}  [{p.pipeline_id}]" for p in pipelines]
    sel_idx = st.selectbox(
        "Pipeline",
        options=range(len(options)),
        format_func=lambda i: options[i],
        key="admin_pipe_sel",
    )
    pipe = pipelines[sel_idx]

    st.markdown(f"**{pipe.display_name}** — *{pipe.description}*")
    st.caption(
        f"Template file: `data/buyplan_templates/{pipe.template_file}` · "
        f"Config file: `data/buyplan_templates/{pipe.config_file}`"
    )

    cfg = tc.load_config(pipe.pipeline_id)

    with st.expander("📄 Template file", expanded=False):
        if tc.template_exists(pipe.pipeline_id):
            tpl_bytes = tc.read_template_bytes(pipe.pipeline_id)
            sz = len(tpl_bytes)
            cdl, cup = st.columns(2)
            cdl.download_button(
                f"⬇ Download {pipe.template_file}  ({sz:,} B)",
                data=tpl_bytes,
                file_name=pipe.template_file or "template.xlsx",
                mime=_XLSX_MIME,
                use_container_width=True,
                key=f"admin_pipe_dl_{pipe.pipeline_id}",
            )
            with cup:
                up = st.file_uploader(
                    "Replace template (.xlsx)",
                    type=["xlsx"],
                    key=f"admin_pipe_up_{pipe.pipeline_id}",
                )
                if up is not None and st.button(
                        "💾 Replace template",
                        key=f"admin_pipe_save_tpl_{pipe.pipeline_id}",
                        type="primary",
                        use_container_width=True):
                    try:
                        tc.write_template_bytes(pipe.pipeline_id, up.read())
                        st.success("Template replaced.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed: {exc}")
        else:
            st.info("No template installed yet.")
            up = st.file_uploader(
                "Upload template (.xlsx)",
                type=["xlsx"],
                key=f"admin_pipe_up_new_{pipe.pipeline_id}",
            )
            if up is not None and st.button(
                    "💾 Save template",
                    key=f"admin_pipe_save_new_{pipe.pipeline_id}",
                    type="primary"):
                try:
                    tc.write_template_bytes(pipe.pipeline_id, up.read())
                    st.success("Template saved.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed: {exc}")

    st.divider()

    st.markdown("**Data-table position**")
    rc1, rc2, rc3 = st.columns(3)
    new_header_row = rc1.number_input(
        "Header row",
        min_value=0, max_value=200, step=1,
        value=int(cfg.get("header_row") or 0),
        help="Row number of the column-header row (0 = leave to auto-detect).",
        key=f"admin_pipe_hr_{pipe.pipeline_id}",
    )
    new_data_row = rc2.number_input(
        "Data start row",
        min_value=0, max_value=200, step=1,
        value=int(cfg.get("data_start_row") or 0),
        help="Row number of the first data row (0 = header_row + 1, or auto-detected).",
        key=f"admin_pipe_dr_{pipe.pipeline_id}",
    )
    new_key_field = rc3.selectbox(
        "Fabric key field",
        options=["display_key", "composition"],
        index=0 if (cfg.get("fabric_key_field") or "display_key") == "display_key" else 1,
        help="Which fabric_master field to write into the fabric-key column.",
        key=f"admin_pipe_fkf_{pipe.pipeline_id}",
    )

    st.markdown("**Column mapping** — logical field → Excel column letter")
    col_map = cfg.get("column_map") or {}
    df_cols = pd.DataFrame(
        [{"Field": k, "Column (A,B,C…)": v} for k, v in col_map.items()]
        or [{"Field": "", "Column (A,B,C…)": ""}]
    )
    edited_cols = st.data_editor(
        df_cols,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config={
            "Field":           st.column_config.TextColumn("Field", help="e.g. Style, PO Number, Color, 合同号"),
            "Column (A,B,C…)": st.column_config.TextColumn("Column", help="Excel column letter (A, B, …, AA …) or 1-based number."),
        },
        key=f"admin_pipe_cols_{pipe.pipeline_id}",
    )

    st.markdown("**Size columns** — size label → Excel column letter")
    sz_map = cfg.get("size_column_map") or {}
    df_sz = pd.DataFrame(
        [{"Size": k, "Column": v} for k, v in sz_map.items()]
        or [{"Size": "XS", "Column": ""}, {"Size": "S", "Column": ""},
            {"Size": "M",  "Column": ""}, {"Size": "L", "Column": ""},
            {"Size": "XL", "Column": ""}, {"Size": "XXL", "Column": ""}]
    )
    edited_sz = st.data_editor(
        df_sz, num_rows="dynamic", width="stretch", hide_index=True,
        key=f"admin_pipe_sz_{pipe.pipeline_id}",
    )

    st.markdown("**Meta columns** — extra fields → Excel column letter")
    meta_map = cfg.get("meta_column_map") or {}
    df_meta = pd.DataFrame(
        [{"Field": k, "Column": v} for k, v in meta_map.items()]
        or [{"Field": "", "Column": ""}]
    )
    edited_meta = st.data_editor(
        df_meta, num_rows="dynamic", width="stretch", hide_index=True,
        key=f"admin_pipe_meta_{pipe.pipeline_id}",
    )

    edited_slots_df = None
    if pipe.supports_fabric_slots:
        st.markdown("**Fabric slots** — one row per fabric header in the template")
        st.caption(
            "Each slot has the row number and three columns: body part, HHN code, "
            "and the 综合标识 Key (display_key) cell."
        )
        slots = cfg.get("fabric_slots") or []
        if not slots:
            slots = [
                {"row": 2, "body_part": "B", "hhn": "C", "key": "E"},
                {"row": 3, "body_part": "B", "hhn": "C", "key": "E"},
                {"row": 4, "body_part": "B", "hhn": "C", "key": "E"},
                {"row": 5, "body_part": "B", "hhn": "C", "key": "E"},
            ]
        df_slots = pd.DataFrame(slots)
        for c in ("row", "body_part", "hhn", "key"):
            if c not in df_slots.columns:
                df_slots[c] = ""
        edited_slots_df = st.data_editor(
            df_slots[["row", "body_part", "hhn", "key"]],
            num_rows="dynamic", width="stretch", hide_index=True,
            column_config={
                "row":       st.column_config.NumberColumn("Row", min_value=1, max_value=200, step=1),
                "body_part": st.column_config.TextColumn("Body-part column"),
                "hhn":       st.column_config.TextColumn("HHN column"),
                "key":       st.column_config.TextColumn("综合标识 Key column"),
            },
            key=f"admin_pipe_slots_{pipe.pipeline_id}",
        )

    new_notes = st.text_area(
        "Notes (free-text, stored with the config)",
        value=str(cfg.get("notes") or ""),
        height=70,
        key=f"admin_pipe_notes_{pipe.pipeline_id}",
    )

    sc1, sc2 = st.columns([1, 3])
    if sc1.button("💾 Save layout", type="primary", use_container_width=True,
                  key=f"admin_pipe_save_{pipe.pipeline_id}"):
        new_col_map = {
            str(r["Field"]).strip(): str(r["Column (A,B,C…)"]).strip()
            for _, r in edited_cols.iterrows()
            if str(r.get("Field", "")).strip() and str(r.get("Column (A,B,C…)", "")).strip()
        }
        new_sz_map = {
            str(r["Size"]).strip().upper(): str(r["Column"]).strip()
            for _, r in edited_sz.iterrows()
            if str(r.get("Size", "")).strip() and str(r.get("Column", "")).strip()
        }
        new_meta_map = {
            str(r["Field"]).strip(): str(r["Column"]).strip()
            for _, r in edited_meta.iterrows()
            if str(r.get("Field", "")).strip() and str(r.get("Column", "")).strip()
        }
        new_slots: list[dict] = []
        if edited_slots_df is not None:
            for _, r in edited_slots_df.iterrows():
                try:
                    rn = int(r.get("row") or 0)
                except (TypeError, ValueError):
                    rn = 0
                if rn <= 0:
                    continue
                new_slots.append({
                    "row":       rn,
                    "body_part": str(r.get("body_part", "") or "").strip(),
                    "hhn":       str(r.get("hhn", "") or "").strip(),
                    "key":       str(r.get("key", "") or "").strip(),
                })

        new_cfg = {
            "header_row":       new_header_row or None,
            "data_start_row":   new_data_row or None,
            "write_headers":    bool(cfg.get("write_headers", False)),
            "column_map":       new_col_map,
            "size_column_map":  new_sz_map,
            "meta_column_map":  new_meta_map,
            "fabric_slots":     new_slots,
            "fabric_key_field": new_key_field,
            "notes":            new_notes,
        }
        try:
            path = tc.save_config(pipe.pipeline_id, new_cfg)
            st.success(f"Saved → `{path.name}` · takes effect on next export.")
        except Exception as exc:
            st.error(f"Save failed: {exc}")

    if sc2.button("↩️ Reload from disk", use_container_width=False,
                  key=f"admin_pipe_reload_{pipe.pipeline_id}"):
        st.rerun()

    with st.expander("👁  Current saved config (JSON)"):
        st.code(_json.dumps(cfg, indent=2, ensure_ascii=False), language="json")
