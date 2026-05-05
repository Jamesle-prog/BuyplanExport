"""Validation and cross-system consistency checks for the Fabric DB tab."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from ui.fabric_db._shared import CSV_MIME, XLSX_MIME
from ui.stores import get_store


def _fabric_db_validation_section(store) -> None:
    """Run all fabric record checks and surface issues in two expanders.

    Check 1 — Composition (面料成分):
        SUM   percentages must total 100 %
        SPELL fiber names must be in the known-fiber dictionary
        CASE  each fiber name must start with a capital letter
        PARSE string could not be tokenised at all

    Check 2 — Numeric fields:
        MISSING  required field is empty
        RANGE    value outside expected thresholds
        CONSISTENCY  cuttable width > full width
        FORMAT   quality_no does not match expected pattern
    """
    from po_extractor.utils.composition_check import validate_all
    from po_extractor.utils.fabric_validators import validate_all_records

    # Run both validators
    comp_issues  = validate_all(store.list_all_compositions())
    field_issues = validate_all_records(store.list_all_for_validation())

    # Helper: download buttons
    def _dl_buttons(df: pd.DataFrame, stem: str) -> None:
        dl1, dl2 = st.columns(2)
        csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        dl1.download_button(
            "⬇ Download issues (.csv)", data=csv_bytes,
            file_name=f"{stem}.csv", mime=CSV_MIME,
            key=f"{stem}_csv", use_container_width=True,
        )
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            df.to_excel(xw, index=False, sheet_name="Issues")
        dl2.download_button(
            "⬇ Download issues (.xlsx)", data=buf.getvalue(),
            file_name=f"{stem}.xlsx", mime=XLSX_MIME,
            key=f"{stem}_xlsx", use_container_width=True,
        )

    # Expander 1: Composition
    n_comp = len(comp_issues)
    if n_comp:
        c_parts = []
        for kind, tag in [("SUM","sum"),("SPELL","spelling"),("CASE","case"),("PARSE","parse")]:
            k = sum(1 for i in comp_issues if i.kind == kind)
            if k: c_parts.append(f"{k} {tag}")
        comp_label = "⚠️ 面料成分 — " + " · ".join(c_parts)
    else:
        comp_label = "✅ 面料成分 checks passed"

    with st.expander(comp_label, expanded=bool(n_comp)):
        if not n_comp:
            st.caption(
                "Every composition string sums to 100 %, uses known fiber names, "
                "and each fiber starts with a capital letter."
            )
        else:
            df_comp = pd.DataFrame([{
                "公司面料编号":    i.quality_no,
                "面料成分（英文）": i.composition,
                "Issue":           i.kind,
                "Detail":          i.detail,
                "Total %":         round(i.total_pct, 2) if i.total_pct else None,
                "Suggested Fix":   i.suggestions,
            } for i in comp_issues])
            st.dataframe(
                df_comp, width="stretch", hide_index=True,
                column_config={
                    "面料成分（英文）": st.column_config.TextColumn(width="medium"),
                    "Detail":          st.column_config.TextColumn(width="large"),
                    "Total %":         st.column_config.NumberColumn(format="%.2f"),
                },
            )
            _dl_buttons(df_comp, "fabric_composition_issues")

    # Expander 2: Field checks
    n_field = len(field_issues)
    if n_field:
        f_parts = []
        for kind, tag in [("MISSING","missing"),("RANGE","range"),
                          ("CONSISTENCY","consistency"),("FORMAT","format")]:
            k = sum(1 for i in field_issues if i.kind == kind)
            if k: f_parts.append(f"{k} {tag}")
        field_label = "⚠️ Field checks — " + " · ".join(f_parts)
    else:
        field_label = "✅ Field checks passed"

    with st.expander(field_label, expanded=bool(n_field)):
        if not n_field:
            st.caption(
                "All weight, width, shrinkage and short-rate values are within "
                "expected ranges and quality_no formats are valid."
            )
        else:
            st.caption(
                f"Thresholds: weight 50–800 g/m² · width 30–250 cm · "
                f"shrinkage ≤ 30% · short rate ≤ 15%"
            )
            df_field = pd.DataFrame([{
                "公司面料编号": i.quality_no,
                "Field":        i.field,
                "Issue":        i.kind,
                "Value":        i.value,
                "Detail":       i.detail,
            } for i in field_issues])
            st.dataframe(
                df_field, width="stretch", hide_index=True,
                column_config={
                    "Detail": st.column_config.TextColumn(width="large"),
                },
            )
            _dl_buttons(df_field, "fabric_field_issues")


def _fabric_db_cross_system_section(fabric_store) -> None:
    """Check consistency between fabric_master, style_fabric_parts, and live PO/SE data.

    Three sub-checks
    ----------------
    1. HHN Orphans     — HHN codes in style_fabric_parts that have no fabric_master record
    2. Coverage Gaps   — PO/SE styles with no fabric mapping (style_fabric_parts entry)
    3. Mapping orphans — style_fabric_parts entries whose style no longer appears in any PO/SE
    """
    po_store = get_store()  # BUG-29: was POStore(DB_PATH) — ran full migrations on every render
    known_qnos    = set(fabric_store.list_all_quality_nos())
    mapped_hhn    = set(po_store.list_all_hhn_nos())
    po_styles     = set(po_store.list_all_po_styles())
    mapped_styles = set(po_store.list_all_mapped_styles())

    # 1. HHN orphans
    orphan_hhn = sorted(mapped_hhn - known_qnos)

    # 2. Coverage gaps
    uncovered_styles = sorted(po_styles - mapped_styles)

    # 3. Mapping orphans (mapped styles no longer in any PO)
    stale_mappings = sorted(mapped_styles - po_styles)

    any_issue = bool(orphan_hhn or uncovered_styles or stale_mappings)

    if any_issue:
        parts = []
        if orphan_hhn:       parts.append(f"{len(orphan_hhn)} HHN orphan(s)")
        if uncovered_styles: parts.append(f"{len(uncovered_styles)} style(s) without mapping")
        if stale_mappings:   parts.append(f"{len(stale_mappings)} stale mapping(s)")
        label = "⚠️ Cross-system checks — " + " · ".join(parts)
    else:
        label = "✅ Cross-system checks passed"

    with st.expander(label, expanded=any_issue):
        if not any_issue:
            st.caption(
                "All mapped HHN codes exist in fabric_master, "
                "every PO style has at least one fabric mapping, "
                "and no stale mappings were found."
            )
            return

        # Sub-section 1: HHN orphans
        if orphan_hhn:
            st.markdown("**🔴 HHN codes in fabric mapping with no fabric_master record**")
            st.caption(
                "These HHN numbers appear in your fabric mapping (style_fabric_parts) "
                "but do not exist in the fabric master database. "
                "The fabric master record may be missing or the HHN code was entered incorrectly."
            )
            df_hhn = pd.DataFrame({"HHN No. (公司面料编号)": orphan_hhn})
            st.dataframe(df_hhn, width="stretch", hide_index=True)
            csv_hhn = df_hhn.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                "⬇ Download HHN orphans (.csv)", data=csv_hhn,
                file_name="hhn_orphans.csv", mime=CSV_MIME,
                key="xsys_hhn_csv", use_container_width=False,
            )
            st.divider()

        # Sub-section 2: Coverage gaps
        if uncovered_styles:
            st.markdown("**🟡 PO styles with no fabric mapping**")
            st.caption(
                "These style numbers appear in your PO/buy-plan history but have "
                "no entry in the fabric mapping table (style_fabric_parts). "
                "Add a fabric mapping so fabric data flows into the buy plan export."
            )
            df_cov = pd.DataFrame({"Style No. (款号)": uncovered_styles})
            st.dataframe(df_cov, width="stretch", hide_index=True)
            csv_cov = df_cov.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                "⬇ Download coverage gaps (.csv)", data=csv_cov,
                file_name="style_coverage_gaps.csv", mime=CSV_MIME,
                key="xsys_cov_csv", use_container_width=False,
            )
            st.divider()

        # Sub-section 3: Stale mappings
        if stale_mappings:
            st.markdown("**🔵 Fabric mappings for styles no longer in PO history**")
            st.caption(
                "These styles have a fabric mapping but no matching PO/SE records. "
                "This is usually harmless (archived styles), but you may want to "
                "clean up the mapping table to keep it tidy."
            )
            df_stale = pd.DataFrame({"Style No. (款号)": stale_mappings})
            st.dataframe(df_stale, width="stretch", hide_index=True)
