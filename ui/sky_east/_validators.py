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
    """Surface import-time warnings for Sky East contracts."""
    import re as _re
    from datetime import datetime as _dt

    _HHN_RE = _re.compile(r'^[A-Za-z]{2,5}-[A-Za-z]{1,5}-?\d{4,8}$')

    n_total = n_neg = n_hhn = n_missing = n_bad_date = n_sku = 0
    bad_neg: list[str] = []
    bad_hhn: list[str] = []
    bad_mis: list[str] = []
    bad_dt:  list[str] = []

    for contract in contracts:
        for item in contract.items:
            n_total += 1
            if not (item.style and item.style.strip()):
                n_missing += 1
                bad_mis.append(f"PC {contract.pc_no}: item with blank style")
            if not (item.color_name and item.color_name.strip()):
                n_missing += 1
                bad_mis.append(f"PC {contract.pc_no}: {item.style} -- blank color_name")
            neg_szs = [f"{s}:{q}" for s, q in (item.sizes or {}).items() if q < 0]
            if neg_szs:
                n_neg += 1
                bad_neg.append(
                    f"PC {contract.pc_no}: {item.style}/{item.color_name} "
                    f"-- negative qty: {', '.join(neg_szs)}"
                )
            hhn = (item.fabric_item_no or "").strip()
            if hhn and not _HHN_RE.match(hhn):
                n_hhn += 1
                bad_hhn.append(
                    f"PC {contract.pc_no}: {item.style}/{item.color_name} "
                    f"-- HHN '{hhn}' does not match expected format"
                )
            dt_raw = (item.ex_fty_date or "").strip()
            if dt_raw:
                parsed_ok = False
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                            "%Y/%m/%d", "%d.%m.%Y"):
                    try:
                        _dt.strptime(dt_raw, fmt)
                        parsed_ok = True
                        break
                    except ValueError:
                        pass
                if not parsed_ok:
                    n_bad_date += 1
                    bad_dt.append(
                        f"PC {contract.pc_no}: {item.style} "
                        f"-- ex_fty_date '{dt_raw}' could not be parsed"
                    )
            if item.config_sku and item.config_sku.strip():
                n_sku += 1

    if n_total == 0:
        return

    pct_sku = round(100 * n_sku / n_total, 1)
    sku_msg = (f"Config SKU coverage: {n_sku}/{n_total} items ({pct_sku}%)"
               + (" OK" if pct_sku >= 95 else " (low -- upload Config SKU file?)"))
    st.write(f"  {sku_msg}")
    log.append(f"{sku_msg}")

    for issues, label in [
        (bad_mis, "Missing style/color"),
        (bad_neg, "Negative size quantities"),
        (bad_hhn, "Non-standard HHN format"),
        (bad_dt,  "Unparseable ex_fty_date"),
    ]:
        if issues:
            st.warning(f"{label} -- {len(issues)} issue(s) found")
            log.append(f"{label} ({len(issues)} issue(s)):")
            for msg in issues[:20]:
                log.append(f"  {msg}")
            if len(issues) > 20:
                log.append(f"  ... and {len(issues) - 20} more")
