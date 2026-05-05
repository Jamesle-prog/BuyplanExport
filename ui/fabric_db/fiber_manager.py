"""Known-fiber dictionary management UI for the Fabric DB tab."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from ui.fabric_db._shared import XLSX_MIME


def _fiber_excel_template(custom: dict, known: dict) -> bytes:
    """Build an Excel workbook for the fiber dictionary download."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Sheet 1 — custom only (what users edit)
        df_c = pd.DataFrame(
            [{"Key (lowercase)": k, "Display Name": v}
             for k, v in sorted(custom.items())]
        ) if custom else pd.DataFrame(columns=["Key (lowercase)", "Display Name"])
        df_c.to_excel(writer, sheet_name="Custom Fibers", index=False)
        # Sheet 2 — full list for reference
        df_all = pd.DataFrame(
            [{"Key (lowercase)": k, "Display Name": v,
              "Source": "custom" if k in custom else "built-in"}
             for k, v in sorted({**known, **custom}.items())]
        )
        df_all.to_excel(writer, sheet_name="All Fibers (reference)", index=False)
    return buf.getvalue()


def _fabric_db_fiber_manager() -> None:
    """Expander that lets users view, add, delete and import fiber name entries."""
    from po_extractor.utils.composition_check import (
        KNOWN_FIBERS, load_custom_fibers, save_custom_fibers,
    )

    with st.expander("🧵 Manage Known Fiber Names", expanded=False):
        st.caption(
            "The checker uses this dictionary to validate 面料成分（英文）. "
            "Built-in entries cannot be edited here. Add custom entries below — "
            "they take priority over built-in ones and persist across sessions."
        )
        custom = load_custom_fibers()

        # Download / Upload Excel
        dl_col, up_col = st.columns(2)
        with dl_col:
            st.download_button(
                "⬇ Export fiber list (.xlsx)",
                data=_fiber_excel_template(custom, KNOWN_FIBERS),
                file_name="fiber_names.xlsx",
                mime=XLSX_MIME,
                use_container_width=True,
                key="fiber_dl_xlsx",
                help="Downloads 'Custom Fibers' sheet (editable) + 'All Fibers' reference sheet",
            )
        with up_col:
            xl_file = st.file_uploader(
                "Import from Excel (.xlsx)",
                type=["xlsx"],
                key="fiber_ul_xlsx",
                help="Upload a file with 'Key (lowercase)' and 'Display Name' columns. "
                     "Rows are merged into custom fibers.",
            )

        if xl_file is not None:
            try:
                df_up = pd.read_excel(xl_file)
                df_up.columns = [c.strip() for c in df_up.columns]
                key_col = next(
                    (c for c in df_up.columns if c.lower() in {"key (lowercase)", "key"}), None
                )
                name_col = next(
                    (c for c in df_up.columns if c.lower() in {"display name", "displayname", "name"}), None
                )
                if key_col is None or name_col is None:
                    st.error(
                        f"Could not find required columns. Expected 'Key (lowercase)' and "
                        f"'Display Name'. Found: {list(df_up.columns)}"
                    )
                else:
                    new_entries = {
                        str(row[key_col]).lower().strip(): str(row[name_col]).strip()
                        for _, row in df_up.iterrows()
                        if pd.notna(row[key_col]) and pd.notna(row[name_col])
                        and str(row[key_col]).strip() and str(row[name_col]).strip()
                    }
                    merged = {**custom, **new_entries}
                    save_custom_fibers(merged)
                    st.success(
                        f"Imported **{len(new_entries)}** entries from Excel "
                        f"({len(merged)} total custom fibers). "
                        "Re-run the composition check to see updated results."
                    )
                    st.rerun()
            except Exception as exc:
                st.error(f"Failed to read Excel: {exc}")

        st.divider()

        # Custom fibers (inline editable table)
        st.markdown("**Custom fibers** *(user-defined, editable)*")
        if custom:
            df_custom = pd.DataFrame(
                [{"Key (lowercase)": k, "Display Name": v} for k, v in sorted(custom.items())]
            )
        else:
            df_custom = pd.DataFrame(columns=["Key (lowercase)", "Display Name"])

        edited_df = st.data_editor(
            df_custom,
            num_rows="dynamic",
            width="stretch",
            key="fiber_manager_editor",
            column_config={
                "Key (lowercase)": st.column_config.TextColumn(
                    "Key (lowercase)",
                    help="Lowercase lookup key, e.g. 'organic cotton'",
                    width="medium",
                ),
                "Display Name": st.column_config.TextColumn(
                    "Display Name",
                    help="Canonical name shown in reports, e.g. 'Organic Cotton'",
                    width="medium",
                ),
            },
        )

        save_col, reset_col, _ = st.columns([1, 1, 4])
        if save_col.button("💾 Save custom fibers", key="fiber_manager_save",
                           use_container_width=True):
            new_custom: dict[str, str] = {}
            for _, row in edited_df.iterrows():
                k = str(row.get("Key (lowercase)") or "").lower().strip()
                v = str(row.get("Display Name") or "").strip()
                if k and v:
                    new_custom[k] = v
            save_custom_fibers(new_custom)
            st.success(f"Saved {len(new_custom)} custom fiber(s). "
                       "Re-run the composition check to see updated results.")
            st.rerun()

        if reset_col.button("🗑 Clear all custom", key="fiber_manager_clear",
                            use_container_width=True):
            save_custom_fibers({})
            st.success("Custom fibers cleared.")
            st.rerun()

        # Built-in fibers (read-only reference)
        with st.expander(f"📖 View built-in fiber list ({len(KNOWN_FIBERS)} entries)",
                         expanded=False):
            df_builtin = pd.DataFrame(
                [{"Key (lowercase)": k, "Display Name": v}
                 for k, v in sorted(KNOWN_FIBERS.items())]
            )
            st.dataframe(df_builtin, width="stretch", hide_index=True,
                         height=300)
            st.caption("These are read-only. Add overrides in the custom fibers editor above.")
