"""Settlement statistics (结算统计表) — import, browse, and the money views.

The workbook stays the master; this reads it in and answers the questions a
spreadsheet makes awkward: what is owed and by whom, which lines are at
discount risk, what a contract actually earned once the factory, the port and
the tax are paid, and which lines name a PO the system has never seen.

Amounts are never added across currencies — the SC book is in GBP — so every
total on this screen is grouped by currency.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.i18n import t
from ui.session_keys import SK
from ui.shared import _th, _tr, fragment_rerun, guard_multiselect_state, lazy_sections
from ui.stores import get_settlement_store

# Column order of the lines table.  Contract facts, then what shipped, then
# money in, then money out — the order the line actually moves through.
_LIST_RENAME = {
    "invoice_no": "Invoice No.", "client": "Client", "year": "Year",
    "po_number": "PO#", "style": "Style", "contract_no": "Contract No.",
    "factory": "Factory", "repeat_or_new": "New / repeat",
    "contract_qty": "Contract qty", "shipped_qty": "Shipped qty",
    "over_short_pct": "Over / short",
    "unit_cost": "Unit cost", "fob": "FOB", "contract_amount": "Contract amt",
    "ex_factory": "X-factory",
    "invoice_amount": "Invoiced", "received": "Received",
    "received_date": "Received on", "outstanding": "Outstanding",
    "pay_fabric": "Fabric paid", "pay_trim": "Trim paid", "pay_cmt": "CMT paid",
    "fee_port": "Port & freight", "fee_other1": "Other 1",
    "fee_other2": "Tax / other 2",
    "cost_total": "Cost total", "margin": "Margin",
    "discount_risk": "Discount risk", "contract_status": "Contract",
    "currency": "Ccy", "sheet": "Sheet",
}
_MONEY = ("unit_cost", "fob", "contract_amount", "invoice_amount", "received",
          "outstanding", "pay_fabric", "pay_trim", "pay_cmt", "fee_port",
          "fee_other1", "fee_other2", "cost_total", "margin")


def show_settlement_tab() -> None:
    st.subheader(f"💰 {t('Settlement')}")
    st.caption(t(
        "The 结算统计表 workbook, read into the system. Excel stays the master "
        "— re-upload to refresh. Amounts are never added across currencies."))

    flash = st.session_state.pop(SK.ST_FLASH, None)
    if flash:
        getattr(st, flash[0], st.info)(flash[1])

    lazy_sections([
        (f"📥 {t('Import')}",        _render_import),
        (f"📋 {t('Lines')}",         _render_lines),
        (f"💵 {t('Receivables')}",   _render_receivables),
        (f"⚠️ {t('Risk & gaps')}",   _render_risk),
        (f"🧵 {t('Samples')}",       _render_samples),
    ], key=SK.ST_NAV)


# ── Import ──────────────────────────────────────────────────────────────────

def _render_import() -> None:
    store = get_settlement_store()
    st.markdown(f"#### {t('Import the settlement workbook')}")
    st.caption(t(
        "Only the sheets in the file are replaced — a book carrying one "
        "client-year cannot delete the years it doesn't mention. 到期未付款明细 "
        "and 折扣风险明细 are not imported: they are views of the same rows and "
        "this tab recomputes them, so a stored copy would go stale."))

    up = st.file_uploader(t("结算统计表 workbook (.xlsx)"), type=["xlsx"],
                          key="st_upload")
    if up is not None:
        sig = f"{up.name}:{up.size}"
        if st.session_state.get(SK.ST_PARSE_SIG) != sig:
            with st.spinner(t("Reading the workbook…")):
                st.session_state[SK.ST_PARSED] = _parse(up)
                st.session_state[SK.ST_PARSE_SIG] = sig

    parsed = st.session_state.get(SK.ST_PARSED)
    if parsed and parsed.get("error"):
        st.error(parsed["error"])
    elif parsed:
        sheets = pd.DataFrame(parsed["sheets"])
        st.dataframe(sheets.rename(columns=_tr({
            "sheet": "Sheet", "kind": "Kind", "rows": "Rows",
            "client": "Client", "year": "Year", "currency": "Ccy"})),
            use_container_width=True, hide_index=True)
        if parsed.get("skipped"):
            st.caption(t("Not imported") + ": " + "; ".join(parsed["skipped"]))
        if st.button(f"📥 {t('Import into the system')}", type="primary",
                     key="st_do_import", use_container_width=True):
            res = store.import_parsed(
                parsed, source_file=parsed.get("source_file", ""),
                file_bytes=parsed.get("file_bytes"),
                imported_by=st.session_state.get(SK.USERNAME, ""))
            _report_import(res)
            st.session_state[SK.ST_PARSED] = None
            st.session_state[SK.ST_PARSE_SIG] = None
            fragment_rerun()

    held = store.rows_by_sheet()
    if held:
        st.divider()
        st.markdown(f"##### {t('Currently held')}")
        st.dataframe(
            pd.DataFrame([{_th("Sheet"): k, _th("Rows"): v}
                          for k, v in sorted(held.items())]),
            use_container_width=True, hide_index=True)
    imports = store.list_imports()
    if not imports.empty:
        with st.expander(f"🕘 {t('Import history')}"):
            st.dataframe(
                imports[["imported_at", "imported_by", "source_file",
                         "sheets", "n_rows", "n_samples"]].rename(
                    columns=_tr({"imported_at": "When", "imported_by": "By",
                                 "source_file": "File", "sheets": "Sheets",
                                 "n_rows": "Rows", "n_samples": "Samples"})),
                use_container_width=True, hide_index=True)


def _parse(upload) -> dict:
    """Parse an upload, returning ``{"error": ...}`` instead of raising.

    A bad workbook must leave the tab usable — the held data is still there
    and still worth looking at.
    """
    from io import BytesIO
    from po_extractor.parsers.settlement import parse_settlement
    data = upload.getbuffer().tobytes()
    try:
        parsed = parse_settlement(BytesIO(data))
    except Exception as exc:                                # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
    parsed["source_file"] = upload.name
    parsed["file_bytes"] = data
    return parsed


def _report_import(res: dict) -> None:
    lines = [f"{s['sheet']}: {s['before']} → {s['after']}"
             for s in res.get("sheets", [])]
    msg = (f"{t('Imported')} {res['n_rows']} {t('settlement line(s)')}"
           f", {res['n_samples']} {t('sample row(s)')}. " + " · ".join(lines))
    if res.get("untouched"):
        msg += (" · " + t("Left untouched") + ": "
                + ", ".join(res["untouched"]))
    st.session_state[SK.ST_FLASH] = ("success", msg)


# ── Lines ───────────────────────────────────────────────────────────────────

def _filters(store, key_prefix: str) -> dict:
    """Client / year / factory filters plus a free-text search."""
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    out = {}
    for col, field, label in ((c1, "client", "Client"), (c2, "year", "Year"),
                              (c3, "factory", "Factory")):
        opts = store.distinct(field)
        key = f"{key_prefix}_{field}"
        guard_multiselect_state(key, opts)
        out[field] = col.multiselect(t(label), opts, key=key)
    out["search"] = c4.text_input(
        t("Search"), key=f"{key_prefix}_search",
        placeholder=t("Invoice, PO#, style, contract or factory"))
    return out


def _render_lines() -> None:
    store = get_settlement_store()
    f = _filters(store, "st_lines")
    df = store.list_rows(clients=f["client"], years=f["year"],
                         factories=f["factory"], search=f["search"])
    if df.empty:
        st.info(t("No settlement lines — import the workbook first."))
        return

    _totals_by_currency(df)
    show = df[[c for c in _LIST_RENAME if c in df.columns]].copy()
    show["discount_risk"] = show["discount_risk"].map({1: "⚠️", 0: ""})
    show["contract_status"] = show["contract_status"].map(
        {"sent": "📤 " + t("Sent"), "signed": "✅ " + t("Signed")}).fillna("")
    st.dataframe(
        show.rename(columns=_tr(_LIST_RENAME)),
        use_container_width=True, hide_index=True,
        column_config={
            _th("Over / short"): st.column_config.NumberColumn(format="%+.2f %%"),
            **{_th(_LIST_RENAME[c]): st.column_config.NumberColumn(format="%.2f")
               for c in _MONEY if c in show.columns},
        })
    st.caption(t(
        "**Outstanding** is what has been invoiced (or contracted, when no "
        "invoice is raised yet) less what has been received. **Margin** is "
        "money in less every payment and fee on the line, and is blank until "
        "something has been paid out — blank means not costed yet, not "
        "break-even."))


def _totals_by_currency(df: pd.DataFrame) -> None:
    """One metric row per currency. Adding GBP to USD would mean nothing."""
    for ccy, part in df.groupby(df["currency"].fillna("—")):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"{t('Lines')} · {ccy}", f"{len(part):,}")
        c2.metric(t("Invoiced"), f"{part['invoice_amount'].sum():,.2f}")
        c3.metric(t("Received"), f"{part['received'].sum():,.2f}")
        c4.metric(t("Outstanding"), f"{part['outstanding'].sum():,.2f}",
                  help=t("Invoiced (or contracted) less received."))


# ── Receivables ─────────────────────────────────────────────────────────────

def _render_receivables() -> None:
    store = get_settlement_store()
    st.markdown(f"#### {t('Outstanding by client')}")
    st.caption(t(
        "Lines that have shipped but not been received in full. This is the "
        "到期未付款明细 sheet, recomputed from the lines themselves so it "
        "cannot fall behind them."))
    df = store.list_rows()
    if df.empty:
        st.info(t("No settlement lines — import the workbook first."))
        return

    only_open = st.checkbox(t("Only lines still owed"), value=True,
                            key="st_recv_open")
    view = df[df["outstanding"].round(2) > 0] if only_open else df
    if view.empty:
        st.success(t("Nothing outstanding."))
        return

    grouped = (view.groupby(["currency", "client", "year"], dropna=False)
               .agg(lines=("id", "count"),
                    invoiced=("invoice_amount", "sum"),
                    received=("received", "sum"),
                    outstanding=("outstanding", "sum"))
               .reset_index()
               .sort_values("outstanding", ascending=False))
    st.dataframe(
        grouped.rename(columns=_tr({
            "currency": "Ccy", "client": "Client", "year": "Year",
            "lines": "Lines", "invoiced": "Invoiced", "received": "Received",
            "outstanding": "Outstanding"})),
        use_container_width=True, hide_index=True)

    st.markdown(f"##### {t('Oldest first')}")
    st.caption(t("By ex-factory date — the line that shipped longest ago is "
                 "the one that has been owed longest."))
    cols = ["ex_factory", "client", "invoice_no", "po_number", "style",
            "contract_no", "factory", "currency", "invoice_amount",
            "received", "outstanding"]
    oldest = view[[c for c in cols if c in view.columns]].copy()
    oldest = oldest.sort_values("ex_factory", na_position="last")
    st.dataframe(oldest.rename(columns=_tr(_LIST_RENAME)),
                 use_container_width=True, hide_index=True)


# ── Risk & gaps ─────────────────────────────────────────────────────────────

def _render_risk() -> None:
    store = get_settlement_store()
    df = store.list_rows()
    if df.empty:
        st.info(t("No settlement lines — import the workbook first."))
        return

    st.markdown(f"#### {t('Discount risk')}")
    st.caption(t(
        "Lines the workbook marks in red on the invoice number. The flag is "
        "carried only as a cell colour in Excel, so it is read from the "
        "sheet's own legend rather than guessed."))
    risk = df[df["discount_risk"] == 1]
    if risk.empty:
        st.success(t("No line is flagged at discount risk."))
    else:
        cols = ["client", "year", "invoice_no", "po_number", "style",
                "contract_no", "factory", "ex_factory", "currency",
                "contract_amount", "invoice_amount", "outstanding"]
        st.dataframe(
            risk[[c for c in cols if c in risk.columns]].rename(
                columns=_tr(_LIST_RENAME)),
            use_container_width=True, hide_index=True)
        for ccy, part in risk.groupby(risk["currency"].fillna("—")):
            st.metric(f"{t('At risk')} · {ccy}",
                      f"{part['invoice_amount'].fillna(part['contract_amount']).sum():,.2f}")

    st.divider()
    st.markdown(f"#### {t('Lines the system cannot match')}")
    st.caption(t(
        "Matched on the client's PO **and** the style — a PO covers several "
        "styles and each is invoiced separately, so the PO alone would fan "
        "one line across all of them. A line here names a PO/style pair no "
        "Sky East contract in the system has, so nothing can be checked "
        "against it."))
    unmatched = store.unmatched_pos()
    if unmatched.empty:
        st.success(t("Every line with a PO matches an order in the system."))
        return
    cols = ["client", "year", "invoice_no", "po_number", "style",
            "contract_no", "contract_qty", "shipped_qty"]
    st.dataframe(
        unmatched[[c for c in cols if c in unmatched.columns]].rename(
            columns=_tr(_LIST_RENAME)),
        use_container_width=True, hide_index=True)

    st.divider()
    st.markdown(f"#### {t('Quantity disagreements')}")
    st.caption(t("Where the settlement line and the order it matches state "
                 "different quantities."))
    matched = store.match_orders()
    if matched.empty or "se_qty" not in matched.columns:
        st.info(t("Nothing to compare — no matching orders in the system."))
        return
    got = matched.dropna(subset=["se_qty"]).copy()
    got["diff"] = (pd.to_numeric(got["contract_qty"], errors="coerce")
                   - pd.to_numeric(got["se_qty"], errors="coerce"))
    gaps = got[got["diff"].fillna(0) != 0]
    if gaps.empty:
        st.success(t("Every matched line agrees with its order."))
        return
    st.dataframe(
        gaps[["client", "year", "invoice_no", "po_number", "style",
              "contract_no", "contract_qty", "se_qty", "diff", "se_pc_no",
              "se_ex_fty"]].rename(columns=_tr({
                  **_LIST_RENAME, "se_qty": "Order qty", "diff": "Difference",
                  "se_pc_no": "PC No.", "se_ex_fty": "Order X-factory"})),
        use_container_width=True, hide_index=True)


# ── Samples ─────────────────────────────────────────────────────────────────

def _render_samples() -> None:
    df = get_settlement_store().list_samples()
    if df.empty:
        st.info(t("No sample costs — the 样品 sheet was empty or absent."))
        return
    st.markdown(f"#### {t('Sample cost by style')}")
    cols = ["client", "style", "factory", "fabric", "lining", "rib", "trim",
            "total"]
    st.dataframe(
        df[[c for c in cols if c in df.columns]].rename(columns=_tr({
            "client": "Client", "style": "Style", "factory": "Factory",
            "fabric": "Fabric", "lining": "Lining", "rib": "Rib",
            "trim": "Trim", "total": "Total"})),
        use_container_width=True, hide_index=True)
    st.metric(t("Total sample cost"),
              f"{pd.to_numeric(df['total'], errors='coerce').sum():,.2f}")
