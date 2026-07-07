"""Sky East import-time validation helpers."""
from __future__ import annotations

import streamlit as st


def _se_report_sku_conflicts(config_sku_lookup, log: list[str]) -> None:
    """Surface Config-SKU conflicts in the UI and log."""
    if not (config_sku_lookup and config_sku_lookup.conflicts):
        return
    n_conf = len(config_sku_lookup.conflicts)
    st.warning(
        f"{n_conf} Config SKU conflict(s) detected -- "
        "the same PO + Color + Brand + Style maps to multiple different Config SKU values."
    )
    log.append(f"{n_conf} Config SKU conflict(s) -- review required:")
    for c in config_sku_lookup.conflicts:
        msg = (f"  PO={c['po']} | Color={c['color']} | "
               f"Brand={c['brand']} | Style={c['style']} "
               f"-> conflicting values: {', '.join(c['values'])}")
        st.error(msg)
        log.append(f'<span style="color:#dc3545">{msg}</span>')


def _se_validate_contracts(contracts, log: list[str]) -> None:
    """Surface import-time warnings for Sky East contracts.

    The checks themselves live in the backend
    (po_extractor.parsers.sky_east_validation) — this wrapper only renders
    the results into the Streamlit status panel and the HTML log.
    """
    from po_extractor.parsers.sky_east_validation import (
        ISSUE_CATEGORIES, validate_contracts,
    )

    report = validate_contracts(contracts)
    if report["total_items"] == 0:
        return

    n_sku, n_total = report["sku_covered"], report["total_items"]
    pct_sku = report["sku_coverage_pct"]
    sku_msg = (f"Config SKU coverage: {n_sku}/{n_total} items ({pct_sku}%)"
               + (" OK" if pct_sku >= 95 else " (low -- upload Config SKU file?)"))
    st.write(f"  {sku_msg}")
    log.append(f"{sku_msg}")

    for key, label in ISSUE_CATEGORIES:
        issues = report["issues"][key]
        if issues:
            st.warning(f"{label} -- {len(issues)} issue(s) found")
            log.append(f"{label} ({len(issues)} issue(s)):")
            for msg in issues[:20]:
                log.append(f"  {msg}")
            if len(issues) > 20:
                log.append(f"  ... and {len(issues) - 20} more")
