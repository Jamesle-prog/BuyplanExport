"""Admin: unified template management.

Single place to upload, replace, download, amend, and seed every template the
app uses:

  • Sky East buy-plan templates (Sky_East.xlsx, Sky_East_P.xlsx) — file-system
    files used by the Sky East exporter.
  • Sky_East_config.json — column-header overrides for the Sky East exporter.
  • GIII per-client buy-plan templates (data/buyplan_templates/<client>.xlsx)
    used by the GIII exporter.
  • Blank / sample templates (download only) — GIII buy-plan sample,
    1.1.PO_Client mapping template, Style-Fabric mapping template.

This view replaces the older single-purpose "Buy Plan Templates" admin tab.
The pre-existing admin function name is re-exported via
``ui/admin_buyplan_template.py`` for backward compatibility.
"""
from __future__ import annotations

import io
import os
import tempfile

import pandas as pd
import streamlit as st

from auth.companies import list_company_names
from po_extractor.exporters.buyplan_export import (
    delete_client_template, list_client_templates, save_client_template,
)
from po_extractor.exporters.sky_east_buyplan_export import (
    SE_TEMPLATE_CATALOG, list_sky_east_templates,
    read_sky_east_config_text, read_sky_east_template,
    replace_sky_east_template, write_sky_east_config_text,
)
from po_extractor.ui_helpers import (
    detect_template_header_row, generate_fabric_mapping_template,
    make_sample_buyplan_template,
)
from po_extractor.utils.client_template import CLIENT_ALIASES, create_template

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (shared across sub-sections)
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_bytes(n: int) -> str:
    return f"{n:,} B" if n else "—"


def _preview_giii_template_columns(xlsx_bytes: bytes, header_row: int) -> None:
    """Render an expander showing which columns were auto-detected in a GIII template."""
    try:
        from po_extractor.exporters.buyplan_export import _auto_detect_columns
        import openpyxl as _xl
        wb = _xl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True)
        ws = wb.worksheets[0]
        col_map, sz_map = _auto_detect_columns(ws, header_row)
        wb.close()
    except Exception:
        return

    total_found = len(col_map) + len(sz_map)
    if total_found == 0:
        st.caption("ℹ️ No standard column headers detected — will use sequential write.")
        return

    with st.expander(
        f"🔍 Auto-detected columns ({total_found} found — expand to verify)",
        expanded=False,
    ):
        if col_map:
            st.markdown("**Named fields**")
            rows = [{"Field": k, "Column": v} for k, v in sorted(col_map.items())]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if sz_map:
            st.markdown("**Size columns**")
            rows = [{"Size": k, "Column": v} for k, v in sorted(sz_map.items())]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(
            "These mappings are detected automatically each time the template is used. "
            "No config file needed — just ensure the header row labels match standard names."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section A — Sky East buy-plan templates
# ─────────────────────────────────────────────────────────────────────────────

def _sky_east_section() -> None:
    st.markdown("### 🛍 Sky East Templates")
    st.caption(
        "These two workbooks drive the Sky East buy-plan and 核料 exporters. "
        "They live on disk at `data/buyplan_templates/` and are loaded directly by the "
        "Sky East exporter — replace them here whenever the layout changes."
    )

    rows = list_sky_east_templates()
    df = pd.DataFrame([
        {
            "Kind":     r["label"],
            "File":     r["file"],
            "Status":   "✅ installed" if r["exists"] else "⚠️ missing",
            "Size":     _fmt_bytes(r["size_bytes"]),
            "Modified": r["modified"] or "—",
        }
        for r in rows
    ])
    st.dataframe(df, width="stretch", hide_index=True)

    # ── Per-template upload + download ────────────────────────────────────────
    for r in rows:
        kind = r["kind"]
        with st.expander(f"📄 {r['label']}  —  `{r['file']}`", expanded=False):
            st.caption(r["description"])

            up = st.file_uploader(
                "Replace template (.xlsx)",
                type=["xlsx"],
                key=f"se_tpl_up_{kind}",
                help="Pick the new workbook here, then click 'Save' below to overwrite the file on disk.",
            )

            col_l, col_r = st.columns(2)
            with col_l:
                if up is not None:
                    if st.button("💾 Save replacement",
                                 key=f"se_tpl_save_{kind}", type="primary",
                                 use_container_width=True):
                        try:
                            path = replace_sky_east_template(kind, up.read())
                            st.success(f"✅ Saved to `{path.name}`. Next export will use the new template.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed to save: {exc}")
                else:
                    st.button("💾 Save replacement",
                              key=f"se_tpl_save_disabled_{kind}",
                              disabled=True, use_container_width=True,
                              help="Pick a file above first.")

            with col_r:
                if r["exists"]:
                    try:
                        st.download_button(
                            f"⬇ Download current `{r['file']}`",
                            data=read_sky_east_template(kind),
                            file_name=r["file"],
                            mime=_XLSX_MIME,
                            key=f"se_tpl_dl_{kind}",
                            use_container_width=True,
                        )
                    except Exception as exc:
                        st.warning(f"Cannot read template: {exc}")
                else:
                    st.info("Template file is missing. Upload one to install it.")

    # ── Sky East config (column overrides) ────────────────────────────────────
    with st.expander("⚙️ Column-header overrides  —  `Sky_East_config.json`", expanded=False):
        st.caption(
            "Optional JSON file that lets you remap column-header text to the canonical "
            "Sky East field names without editing the template. Leave empty to delete and "
            "fall back to the template's own headers."
        )
        cur = read_sky_east_config_text()
        new = st.text_area(
            "Sky_East_config.json contents",
            value=cur,
            height=240,
            key="se_cfg_text",
            help="Must be valid JSON. Saved as UTF-8.",
        )
        if st.button("💾 Save config", key="se_cfg_save", type="primary"):
            try:
                path = write_sky_east_config_text(new)
                action = "deleted (defaults restored)" if not new.strip() else f"saved to `{path.name}`"
                st.success(f"✅ Config {action}.")
                st.rerun()
            except Exception as exc:
                st.error(f"Invalid config: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Section B — GIII per-client buy-plan templates
# ─────────────────────────────────────────────────────────────────────────────

def _giii_section() -> None:
    st.markdown("### 📋 GIII Per-Client Buy-Plan Templates")
    st.caption(
        "Each client can have its own buy-plan Excel template. "
        "When exporting, the system picks the template matching the PO's company name. "
        "**default** is used as a fallback when no client-specific template exists. "
        "Without any template the built-in format is used."
    )

    installed = list_client_templates()
    if installed:
        df_tpl = pd.DataFrame(installed)
        df_tpl["size_bytes"] = df_tpl["size_bytes"].apply(lambda x: f"{x:,} B")
        df_tpl.columns = ["Client", "File", "Size"]
        st.dataframe(df_tpl, width="stretch", hide_index=True)
    else:
        st.info("No per-client templates installed yet — all GIII exports use the built-in format.")

    st.markdown("#### Upload / replace a client template")

    companies = list_company_names()
    client_options = ["default"] + sorted(companies)
    sel_client = st.selectbox(
        "Client",
        client_options,
        key="admin_tpl_client",
        help="Select the client this template applies to. "
             "'default' is the shared fallback for any client without a specific template.",
    )

    up = st.file_uploader(
        "Template file (.xlsx)",
        type=["xlsx"],
        key="admin_tpl_upload",
        help=(
            "First sheet is the per-style master. "
            "Use {{data_start}} to mark where the data table starts. "
            "Placeholders: {{factory}}, {{style}}, {{xfactory_date}}, "
            "{{xport_date}}, {{coo}}, {{division}}, {{created_at}}"
        ),
    )

    if up is not None:
        xlsx_bytes = up.read()
        detected_row = detect_template_header_row(xlsx_bytes)

        if detected_row:
            st.success(
                f"✅ Found `{{{{data_start}}}}` at row **{detected_row}** — "
                "data table will start there."
            )
            header_row_val = detected_row
        else:
            st.warning(
                "⚠️ No `{{data_start}}` found. If this is a Sky East template, upload it via "
                "the **Sky East Templates** section above instead. Otherwise, set the header "
                "row manually below."
            )
            header_row_val = 5

        _preview_giii_template_columns(xlsx_bytes, header_row_val)

        cfg_row = st.number_input(
            "Header row (fallback if no {{data_start}})",
            min_value=1, max_value=50,
            value=header_row_val, step=1,
            key="admin_tpl_header_row",
            help="Row where column headers (PO Number, Style, Color…) will be written.",
        )

        if st.button("💾 Save template", key="admin_tpl_save", type="primary"):
            try:
                save_client_template(sel_client, xlsx_bytes, header_row=int(cfg_row))
                st.success(
                    f"✅ Template saved for **{sel_client}**. "
                    "It will be used on the next export for matching POs."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to save template: {exc}")

    # ── Download / delete existing client template ────────────────────────────
    if installed:
        st.markdown("#### Download / delete an existing client template")
        del_client = st.selectbox(
            "Select template",
            [t["client"] for t in installed],
            key="admin_tpl_del_sel",
        )
        selected_tpl = next((t for t in installed if t["client"] == del_client), None)
        if selected_tpl:
            from po_extractor.exporters.buyplan_export import _TEMPLATES_DIR
            tpl_path = _TEMPLATES_DIR / selected_tpl["file"]
            dc1, dc2 = st.columns(2)
            with open(tpl_path, "rb") as fh:
                tpl_bytes = fh.read()
            dc1.download_button(
                f"⬇ Download {selected_tpl['file']}",
                data=tpl_bytes,
                file_name=selected_tpl["file"],
                mime=_XLSX_MIME,
                use_container_width=True,
                key="admin_tpl_dl_existing",
            )
            if dc2.button("🗑 Delete this template", key="admin_tpl_delete",
                          use_container_width=True):
                delete_client_template(del_client)
                st.success(f"Deleted template for '{del_client}'.")
                st.rerun()
            detected_hdr = detect_template_header_row(tpl_bytes) or 5
            _preview_giii_template_columns(tpl_bytes, detected_hdr)


# ─────────────────────────────────────────────────────────────────────────────
# Section C — Blank / sample template downloads
# ─────────────────────────────────────────────────────────────────────────────

def _blank_templates_section() -> None:
    st.markdown("### 📥 Blank / Sample Templates (download only)")
    st.caption(
        "Pre-built blank templates to hand to clients or to use as a starting point. "
        "These are generated on demand — they aren't stored on disk."
    )

    # ── GIII buy-plan sample template ─────────────────────────────────────────
    with st.expander("📄 GIII Buy-Plan Sample Template", expanded=False):
        st.caption(
            "Ready-made sample with all `{{placeholders}}` — rename and upload it to a "
            "client slot in the **GIII Per-Client Buy-Plan Templates** section above."
        )
        st.download_button(
            "⬇ Download sample buy-plan template",
            data=make_sample_buyplan_template(),
            file_name="GIII_BuyPlan_Template_Sample.xlsx",
            mime=_XLSX_MIME,
            key="blank_tpl_dl_giii_buyplan",
            use_container_width=True,
        )

    # ── 1.1.PO_Client mapping template ────────────────────────────────────────
    with st.expander("📄 Client PO Mapping Template (1.1.PO_Client)", expanded=False):
        st.caption(
            "Two-row header workbook used by the GIII Excel pipeline to import a client's "
            "PO data. Pre-fill the row-1 client headers for a known client below."
        )
        client_for_tpl = st.selectbox(
            "Pre-fill client headers",
            ["(generic)"] + list(CLIENT_ALIASES.keys()),
            key="blank_tpl_client_profile",
        )
        if st.button("Generate mapping template", key="blank_tpl_gen_client"):
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
                tf_path = tf.name
            try:
                create_template(
                    tf_path,
                    client=None if client_for_tpl == "(generic)" else client_for_tpl,
                )
                with open(tf_path, "rb") as f:
                    tpl_buf = f.read()
            finally:
                if os.path.exists(tf_path):
                    os.unlink(tf_path)
            suffix = "" if client_for_tpl == "(generic)" else f"_{client_for_tpl}"
            st.download_button(
                "⬇ Download mapping template",
                data=tpl_buf,
                file_name=f"PO_Client_Mapping_Template{suffix}.xlsx",
                mime=_XLSX_MIME,
                key="blank_tpl_dl_client",
                use_container_width=True,
            )

    # ── Style-Fabric mapping template ─────────────────────────────────────────
    with st.expander("📄 Style-Fabric Mapping Template (HHN codes)", expanded=False):
        st.caption(
            "Used by both the GIII Reference panel and the Sky East tab to map each style "
            "to up to 4 HHN fabric codes. Same template for both pipelines."
        )
        st.download_button(
            "⬇ Download fabric mapping template",
            data=generate_fabric_mapping_template(),
            file_name="Style_Fabric_Mapping_Template.xlsx",
            mime=_XLSX_MIME,
            key="blank_tpl_dl_fabric",
            use_container_width=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section D — Placeholder / format reference
# ─────────────────────────────────────────────────────────────────────────────

def _reference_section() -> None:
    with st.expander("📖 Placeholder reference (GIII per-client templates)"):
        st.markdown("""
| Placeholder | Description |
|---|---|
| `{{factory}}` | Factory name + code |
| `{{style}}` | Style number |
| `{{xfactory_date}}` | X-Factory Date (X-Port minus 10 days) |
| `{{xport_date}}` | Orig X-Port Date |
| `{{coo}}` | Country of Origin |
| `{{division}}` | Division code + name |
| `{{created_at}}` | Timestamp when the file was generated |
| `{{data_start}}` | **Marker only** — marks the row where the data table starts |

**Template lookup order:** client-specific → `default` → built-in format

**Tips:**
- Rows *above* `{{data_start}}` are your metadata / branding area.
- `{{data_start}}` row is overwritten with column headers (PO Number, Style, Color…).
- Data rows and the grand-total row are written immediately below.
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def show_templates_admin() -> None:
    """Render the unified Templates admin view."""
    st.subheader("📄 Templates")
    st.caption(
        "Single place to upload, replace, download, and amend every template the app uses. "
        "Sky East templates are at the top, GIII per-client buy-plan templates in the middle, "
        "and blank/sample template downloads at the bottom."
    )

    _sky_east_section()
    st.divider()
    _giii_section()
    st.divider()
    _blank_templates_section()
    st.divider()
    _reference_section()
