"""📄 CMPT Contracts tab — 加工合同 with factories + price ledger.

Prepare CMPT contracts from the user's own template (uploaded once, with
``{{placeholder}}`` tokens — see ``po_extractor/exporters/cmpt_contract_doc``)
and track agreed value vs. payments per contract:

  agreed = Σ(line qty × unit price)   paid = Σ(payments)   balance = agreed − paid

Totals are always computed from lines/payments, never stored.
"""
from __future__ import annotations

import os
from datetime import date

import pandas as pd
import streamlit as st

from ui.i18n import t
from ui.shared import fragment_rerun, XLSX_MIME
from ui.stores import (
    get_cmpt_contract_store,
    get_factory_progress_store,
    get_production_tracking_store,
)
from po_extractor.config import DATA_DIR
from po_extractor.store._cmpt_schema import (
    CONTRACT_STATUSES, CONTRACT_STATUS_LABELS,
)

_TEMPLATE_DIR  = os.path.join(DATA_DIR, "cmpt_templates")
_TEMPLATE_PATH = os.path.join(_TEMPLATE_DIR, "default.xlsx")

_LINE_COLS = ["po_number", "style", "color", "description", "qty", "unit_price"]

_PLACEHOLDER_HELP = """
**Template placeholders** — edit your contract template once in Excel, putting
these tokens where the data should go, then upload it below:

- Header (any cell, mixed with text): `{{contract_no}}` `{{contract_date}}`
  `{{factory}}` `{{company}}` `{{currency}}` `{{notes}}` `{{today}}`
  `{{total_qty}}` `{{total_amount}}` `{{total_amount_cn}}` (大写金额)
- Line items — ONE prototype row containing: `{{line.no}}` `{{line.po}}`
  `{{line.style}}` `{{line.color}}` `{{line.description}}` `{{line.qty}}`
  `{{line.unit_price}}` `{{line.amount}}` — that row is duplicated once per
  contract line; titles above and signature blocks below stay put.
"""


def show_cmpt_tab(username: str, admin_mode: bool) -> None:
    store = get_cmpt_contract_store()

    st.subheader(f"📄 {t('CMPT Contracts (加工合同)')}")
    st.caption(t(
        "Prepare processing contracts with factories from your own template, "
        "and track the agreed value vs. payments per contract."
    ))

    _contracts_table(store)
    st.divider()
    _new_contract_section(store, username)
    _contract_detail_section(store, username, admin_mode)
    if admin_mode:
        st.divider()
        _template_section()


# ─────────────────────────────────────────────────────────────────────────────
# Contracts overview
# ─────────────────────────────────────────────────────────────────────────────

def _contracts_table(store) -> None:
    contracts = store.list_contracts()
    if not contracts:
        st.info(t("No contracts yet — create one below."))
        return

    c1, c2 = st.columns(2)
    with c1:
        factories = store.list_factories()
        f_sel = st.selectbox(t("Factory"), options=["(all)"] + factories,
                             key="cmpt_filter_factory")
    with c2:
        s_sel = st.selectbox(
            t("Status"), options=["(all)"] + CONTRACT_STATUSES,
            format_func=lambda s: CONTRACT_STATUS_LABELS.get(s, s),
            key="cmpt_filter_status",
        )
    rows = [
        c for c in contracts
        if (f_sel == "(all)" or c["factory"] == f_sel)
        and (s_sel == "(all)" or c["status"] == s_sel)
    ]

    df = pd.DataFrame([{
        "Contract No.": c["contract_no"],
        "Factory":      c["factory"],
        "Date":         c["contract_date"] or "—",
        "Status":       CONTRACT_STATUS_LABELS.get(c["status"], c["status"]),
        "Qty":          c["total_qty"],
        "Agreed":       c["agreed_total"],
        "Paid":         c["paid_total"],
        "Balance":      c["balance"],
    } for c in rows])
    st.dataframe(
        df, width="stretch", hide_index=True,
        height=min(60 + 36 * len(df), 420),
        column_config={
            "Contract No.": st.column_config.TextColumn(t("Contract No."), width="medium"),
            "Factory":      st.column_config.TextColumn(t("Factory"), width="medium"),
            "Date":         st.column_config.TextColumn(t("Date"), width="small"),
            "Status":       st.column_config.TextColumn(t("Status"), width="small"),
            "Qty":          st.column_config.NumberColumn(t("Qty"), format="%d"),
            "Agreed":       st.column_config.NumberColumn(t("Agreed"), format="%.2f"),
            "Paid":         st.column_config.NumberColumn(t("Paid"), format="%.2f"),
            "Balance":      st.column_config.NumberColumn(t("Balance"), format="%.2f"),
        },
    )
    total_balance = sum(c["balance"] for c in rows)
    st.caption(
        f"{len(rows)} {t('contract(s)')} · "
        f"{t('outstanding balance total')}: {total_balance:,.2f}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# New contract
# ─────────────────────────────────────────────────────────────────────────────

def _blank_lines_df() -> pd.DataFrame:
    return pd.DataFrame([{c: (0 if c in ("qty",) else (0.0 if c == "unit_price" else ""))
                          for c in _LINE_COLS}])


def _lines_editor(key: str, initial: pd.DataFrame) -> pd.DataFrame:
    return st.data_editor(
        initial,
        num_rows="dynamic",
        key=key,
        width="stretch",
        column_config={
            "po_number":   st.column_config.TextColumn("PO"),
            "style":       st.column_config.TextColumn(t("Style")),
            "color":       st.column_config.TextColumn(t("Color")),
            "description": st.column_config.TextColumn(t("Description")),
            "qty":         st.column_config.NumberColumn(t("Qty"), min_value=0, step=1),
            "unit_price":  st.column_config.NumberColumn(
                t("Unit price"), min_value=0.0, step=0.01, format="%.2f"),
        },
    )


def _editor_lines(df: pd.DataFrame) -> list[dict]:
    lines = []
    for _, row in df.iterrows():
        lines.append({
            "po_number":   str(row.get("po_number") or "").strip(),
            "style":       str(row.get("style") or "").strip(),
            "color":       str(row.get("color") or "").strip(),
            "description": str(row.get("description") or "").strip(),
            "qty":         int(row.get("qty") or 0),
            "unit_price":  float(row.get("unit_price") or 0),
        })
    return [ln for ln in lines
            if ln["qty"] > 0 or ln["po_number"] or ln["style"] or ln["description"]]


def _new_contract_section(store, username: str) -> None:
    with st.expander(f"➕ {t('New contract')}", expanded=False):
        # Auto-suggest the next number in the CMPT-YYYY-NNN series (seeded
        # once per form; re-seeded after each successful create). The field
        # stays editable for houses with their own numbering.
        if "cmpt_new_no" not in st.session_state:
            st.session_state["cmpt_new_no"] = store.next_contract_no()
        c1, c2, c3 = st.columns(3)
        with c1:
            contract_no = st.text_input(
                t("Contract No."), key="cmpt_new_no",
                help=t("Auto-generated — edit if you use your own numbering."),
            )
        with c2:
            factory = st.text_input(t("Factory"), key="cmpt_new_factory")
        with c3:
            cdate = st.date_input(t("Contract date"), value=date.today(),
                                  key="cmpt_new_date")
        c4, c5 = st.columns(2)
        with c4:
            company = st.text_input(t("Client company (optional)"), key="cmpt_new_company")
        with c5:
            currency = st.text_input(t("Currency"), value="RMB", key="cmpt_new_currency")
        notes = st.text_input(t("Notes"), key="cmpt_new_notes")

        # Optional prefill from tracked PO/styles (qty from the order data).
        pt_records = get_production_tracking_store().list_all(allow_all=True)
        if pt_records:
            opts = list(range(len(pt_records)))
            sel = st.multiselect(
                t("Prefill lines from tracked PO/styles (optional)"),
                options=opts,
                format_func=lambda i: (
                    f"{pt_records[i]['po_number']} — {pt_records[i].get('style') or '—'}"
                ),
                key="cmpt_new_prefill",
            )
        else:
            sel = []

        if st.button(t("Load line editor"), key="cmpt_new_load"):
            if sel:
                pairs = [(pt_records[i]["po_number"], pt_records[i].get("style") or "")
                         for i in sel]
                qty_map = get_factory_progress_store().order_qty_for_pairs(pairs)
                st.session_state["cmpt_new_lines_df"] = pd.DataFrame([{
                    "po_number": po, "style": sty, "color": "", "description": "",
                    "qty": qty_map.get((po, sty), 0), "unit_price": 0.0,
                } for po, sty in pairs])
            else:
                st.session_state["cmpt_new_lines_df"] = _blank_lines_df()

        if "cmpt_new_lines_df" in st.session_state:
            edited = _lines_editor("cmpt_new_lines_editor",
                                   st.session_state["cmpt_new_lines_df"])
            lines = _editor_lines(edited)
            agreed = sum(ln["qty"] * ln["unit_price"] for ln in lines)
            st.caption(f"{t('Agreed value')}: {agreed:,.2f}")

            if st.button(f"✅ {t('Create contract')}", type="primary",
                         key="cmpt_new_create"):
                try:
                    store.create_contract(
                        contract_no, factory,
                        company=company, contract_date=cdate.isoformat(),
                        currency=currency, notes=notes,
                        lines=lines, created_by=username,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.pop("cmpt_new_lines_df", None)
                    st.session_state.pop("cmpt_new_no", None)   # re-seed next number
                    st.success(f"✅ {t('Contract created.')}")
                    fragment_rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Contract detail — header, lines, payments, document generation
# ─────────────────────────────────────────────────────────────────────────────

def _contract_detail_section(store, username: str, admin_mode: bool) -> None:
    contracts = store.list_contracts()
    if not contracts:
        return
    with st.expander(f"📋 {t('Contract detail / payments / document')}", expanded=False):
        by_id = {c["id"]: c for c in contracts}
        cid = st.selectbox(
            t("Contract"), options=list(by_id),
            format_func=lambda i: (
                f"{by_id[i]['contract_no']} · {by_id[i]['factory']} · "
                f"{CONTRACT_STATUS_LABELS.get(by_id[i]['status'], by_id[i]['status'])}"
            ),
            key="cmpt_detail_sel",
        )
        contract = store.get_contract(cid)
        if contract is None:
            st.warning(t("Contract not found — it may have been deleted."))
            return

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(t("Qty"), f"{contract['total_qty']:,}")
        m2.metric(t("Agreed"), f"{contract['agreed_total']:,.2f}")
        m3.metric(t("Paid"), f"{contract['paid_total']:,.2f}")
        m4.metric(t("Balance"), f"{contract['balance']:,.2f}")

        # ── Header update ───────────────────────────────────────────────────
        h1, h2 = st.columns(2)
        with h1:
            new_status = st.selectbox(
                t("Status"), options=CONTRACT_STATUSES,
                index=CONTRACT_STATUSES.index(contract["status"]),
                format_func=lambda s: CONTRACT_STATUS_LABELS.get(s, s),
                key=f"cmpt_detail_status_{cid}",
            )
        with h2:
            new_notes = st.text_input(t("Notes"), value=contract["notes"] or "",
                                      key=f"cmpt_detail_notes_{cid}")
        if st.button(t("Save header"), key=f"cmpt_detail_savehdr_{cid}"):
            store.update_contract(cid, status=new_status, notes=new_notes,
                                  updated_by=username)
            st.success(f"✅ {t('Saved.')}")
            fragment_rerun()

        # ── Lines editor ────────────────────────────────────────────────────
        st.markdown(f"**{t('Lines')}**")
        lines_df = pd.DataFrame(contract["lines"])[_LINE_COLS] \
            if contract["lines"] else _blank_lines_df()
        edited = _lines_editor(f"cmpt_detail_lines_{cid}", lines_df)
        if st.button(t("Save lines"), key=f"cmpt_detail_savelines_{cid}"):
            store.replace_lines(cid, _editor_lines(edited), updated_by=username)
            st.success(f"✅ {t('Saved.')}")
            fragment_rerun()

        # ── Payments ────────────────────────────────────────────────────────
        st.markdown(f"**{t('Payments')}**")
        if contract["payments"]:
            pay_df = pd.DataFrame([{
                "id":     p["id"],
                "Date":   p["pay_date"],
                "Amount": p["amount"],
                "Method": p["method"] or "—",
                "Note":   p["note"] or "",
                "By":     p["recorded_by"] or "—",
            } for p in contract["payments"]])
            st.dataframe(pay_df.drop(columns=["id"]), width="stretch",
                         hide_index=True)
        else:
            st.caption(t("No payments recorded yet."))

        p1, p2, p3, p4 = st.columns([1, 1, 1, 2])
        with p1:
            pay_date = st.date_input(t("Payment date"), key=f"cmpt_pay_date_{cid}")
        with p2:
            amount = st.number_input(t("Amount"), step=0.01, format="%.2f",
                                     key=f"cmpt_pay_amount_{cid}")
        with p3:
            method = st.text_input(t("Method"), key=f"cmpt_pay_method_{cid}",
                                   placeholder="电汇 / 承兑 / ...")
        with p4:
            pnote = st.text_input(t("Payment note"), key=f"cmpt_pay_note_{cid}")
        if st.button(f"➕ {t('Add payment')}", key=f"cmpt_pay_add_{cid}"):
            try:
                store.add_payment(cid, pay_date.isoformat(), float(amount),
                                  method=method, note=pnote,
                                  recorded_by=username)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success(f"✅ {t('Payment recorded.')}")
                fragment_rerun()

        if admin_mode and contract["payments"]:
            from ui.shared import guard_multiselect_state
            pay_opts = [p["id"] for p in contract["payments"]]
            guard_multiselect_state(f"cmpt_pay_del_{cid}", pay_opts)
            del_ids = st.multiselect(
                t("Delete payment(s) — corrections only"),
                options=pay_opts,
                format_func=lambda i: next(
                    f"#{i} · {p['pay_date']} · {p['amount']:,.2f}"
                    for p in contract["payments"] if p["id"] == i),
                key=f"cmpt_pay_del_{cid}",
            )
            if del_ids and st.button(f"🗑 {t('Delete')} {len(del_ids)}",
                                     key=f"cmpt_pay_del_go_{cid}"):
                store.delete_payments(del_ids)
                st.session_state.pop(f"cmpt_pay_del_{cid}", None)
                fragment_rerun()

        # ── Document generation ─────────────────────────────────────────────
        st.markdown(f"**{t('Contract document')}**")
        if not os.path.exists(_TEMPLATE_PATH):
            st.info(t(
                "No contract template uploaded yet — an admin can upload one "
                "in the Template section below (see the placeholder guide there)."
            ))
        else:
            from po_extractor.exporters.cmpt_contract_doc import (
                generate_cmpt_contract_xlsx,
            )
            try:
                with open(_TEMPLATE_PATH, "rb") as fh:
                    doc = generate_cmpt_contract_xlsx(fh.read(), contract)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.download_button(
                    f"⬇️ {t('Download contract document')}",
                    data=doc,
                    file_name=f"CMPT_{contract['contract_no']}.xlsx",
                    mime=XLSX_MIME,
                    key=f"cmpt_doc_dl_{cid}",
                )

        if admin_mode:
            if st.button(f"🗑 {t('Delete this contract (with lines and payments)')}",
                         key=f"cmpt_detail_del_{cid}"):
                store.delete_contract(cid)
                st.session_state.pop("cmpt_detail_sel", None)
                fragment_rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Template management (admin)
# ─────────────────────────────────────────────────────────────────────────────

def _template_section() -> None:
    with st.expander(f"🧾 {t('Contract template (admin)')}", expanded=False):
        st.markdown(_PLACEHOLDER_HELP)
        if os.path.exists(_TEMPLATE_PATH):
            st.caption(f"✅ {t('Template on file')}: {_TEMPLATE_PATH}")
            with open(_TEMPLATE_PATH, "rb") as fh:
                st.download_button(
                    f"⬇️ {t('Download current template')}", data=fh.read(),
                    file_name="cmpt_template.xlsx",
                    mime=XLSX_MIME,
                    key="cmpt_tpl_dl",
                )
        else:
            st.caption(f"— {t('No template uploaded yet.')}")
        up = st.file_uploader(
            t("Upload template (.xlsx with {{placeholders}})"),
            type=["xlsx"], key="cmpt_tpl_upload",
        )
        if up is not None and st.button(t("Save template"), key="cmpt_tpl_save"):
            os.makedirs(_TEMPLATE_DIR, exist_ok=True)
            with open(_TEMPLATE_PATH, "wb") as fh:
                fh.write(up.getvalue())
            st.success(f"✅ {t('Template saved.')}")
            fragment_rerun()
