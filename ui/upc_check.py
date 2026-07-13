"""UPC Check — PDA barcode-scanner module.

A PDA / handheld scanner acts as a keyboard: it "types" the scanned UPC and
presses Enter into the focused field. Each scan box uses an ``on_change``
callback that reads the value, clears the box (ready for the next scan), and
records the result — the standard Streamlit scan-and-clear pattern.

Three modes:
* 🔍 Lookup   — scan a UPC → show its PO/style/color/size/client/warehouse/units.
* ✓ Verify    — pick a PO, scan each UPC → does it belong to that PO?
* 🧮 Stocktake — scan to +1 / -1 a physical count per UPC (盘点).
"""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

from auth.users import get_user_companies
from ui.i18n import t
from ui.session_keys import SK
from ui.stores import get_store

_COLS = {
    "po_number": "PO", "style": "Style", "color": "Color", "size": "Size",
    "units": "Units", "company": "Client", "destination_code": "Warehouse",
    "ship_to": "Destination", "buyer": "Buyer", "xfty_date": "X-Factory",
}


def _xlsx(df: pd.DataFrame, sheet: str) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name=sheet)
    return buf.getvalue()


def show_upc_check_tab() -> None:
    store = get_store()
    user_cos = get_user_companies(st.session_state.get(SK.USERNAME, "")) or None

    st.subheader("📷 " + t("UPC Check (PDA scanner)"))
    st.caption(t("Use a PDA/barcode scanner — it types the UPC and presses "
                 "Enter into the scan box. Keep the box focused between scans."))

    mode = st.radio(
        t("Mode"),
        ["lookup", "verify", "count"],
        format_func=lambda m: {
            "lookup": "🔍 " + t("Lookup"),
            "verify": "✓ " + t("Verify against PO"),
            "count":  "🧮 " + t("Stocktake 盘点"),
        }[m],
        horizontal=True, key="upc_mode",
    )
    st.divider()

    if mode == "lookup":
        _mode_lookup(store, user_cos)
    elif mode == "verify":
        _mode_verify(store, user_cos)
    else:
        _mode_count(store, user_cos)


# ── 1) Lookup ─────────────────────────────────────────────────────────────────

def _mode_lookup(store, user_cos):
    def _on_scan():
        upc = str(st.session_state.get("upc_lk_input", "")).strip()
        st.session_state["upc_lk_input"] = ""
        if not upc:
            return
        rows = store.find_by_upc(upc, companies=user_cos)
        st.session_state["upc_lk_last"] = {"upc": upc, "rows": rows}
        hist = st.session_state.setdefault("upc_lk_hist", [])
        hist.insert(0, {"UPC": upc, "Matches": len(rows)})
        del hist[50:]

    st.text_input(t("Scan UPC"), key="upc_lk_input", on_change=_on_scan,
                  placeholder=t("Scan or type a UPC, then Enter"))

    last = st.session_state.get("upc_lk_last")
    if last:
        if not last["rows"]:
            st.error(f"❌ `{last['upc']}` — " + t("not found in any stored PO"))
        else:
            st.success(f"✅ `{last['upc']}` — {len(last['rows'])} " + t("match(es)"))
            df = pd.DataFrame(last["rows"])
            df = df[[c for c in _COLS if c in df.columns]].rename(columns=_COLS)
            st.dataframe(df, use_container_width=True, hide_index=True)

    hist = st.session_state.get("upc_lk_hist")
    if hist:
        with st.expander(f"🕑 {t('Scan history')} ({len(hist)})"):
            st.dataframe(pd.DataFrame(hist), use_container_width=True, hide_index=True)


# ── 2) Verify against a selected PO ───────────────────────────────────────────

def _mode_verify(store, user_cos):
    df_pos = store.list_pos(companies=user_cos)
    pos = df_pos["po_number"].tolist() if not df_pos.empty else []
    if not pos:
        st.info(t("No POs stored yet."))
        return

    po = st.selectbox(t("Select PO to verify against"), pos, key="upc_vf_po")
    # Reset the tally when the PO selection changes.
    if st.session_state.get("upc_vf_po_active") != po:
        st.session_state["upc_vf_po_active"] = po
        st.session_state["upc_vf_results"] = []

    expected = store.load_size_rows([po])
    exp_upcs = set(expected["UPC"].astype(str)) if not expected.empty else set()

    def _on_scan():
        upc = str(st.session_state.get("upc_vf_input", "")).strip()
        st.session_state["upc_vf_input"] = ""
        if not upc:
            return
        rows = store.find_by_upc(upc, companies=user_cos)
        here = next((r for r in rows if r["po_number"] == po), None)
        other = "、".join(sorted({r["po_number"] for r in rows if r["po_number"] != po}))
        st.session_state.setdefault("upc_vf_results", []).insert(0, {
            "ok": here is not None, "UPC": upc,
            "Size": here["size"] if here else "",
            "Color": here["color"] if here else "",
            "Units": here["units"] if here else "",
            "Note": "" if here else (t("belongs to ") + other if other
                                     else t("not in any PO")),
        })

    st.text_input(t("Scan UPC to verify"), key="upc_vf_input", on_change=_on_scan,
                  placeholder=t("Scan each carton/piece UPC, then Enter"))

    results = st.session_state.get("upc_vf_results", [])
    matched_upcs = {r["UPC"] for r in results if r["ok"]}
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ " + t("Matched"), f"{len(matched_upcs)}/{len(exp_upcs)}")
    c2.metric(t("Scans"), len(results))
    c3.metric("❌ " + t("Not in PO"), sum(1 for r in results if not r["ok"]))

    last = results[0] if results else None
    if last:
        (st.success if last["ok"] else st.error)(
            f"{'✅' if last['ok'] else '❌'} `{last['UPC']}`"
            + (f" — {last['Color']} / {last['Size']} × {last['Units']}"
               if last["ok"] else f" — {last['Note']}"))

    # sizes/colours still unscanned on this PO
    if not expected.empty:
        remaining = expected[~expected["UPC"].astype(str).isin(matched_upcs)]
        if not remaining.empty:
            with st.expander(f"⏳ {t('Not yet scanned')} ({len(remaining)})", expanded=False):
                st.dataframe(remaining, use_container_width=True, hide_index=True)
    if results:
        with st.expander(f"🕑 {t('Scan results')} ({len(results)})", expanded=True):
            st.dataframe(pd.DataFrame([{k: v for k, v in r.items() if k != "ok"}
                                       for r in results]),
                         use_container_width=True, hide_index=True)


# ── 3) Stocktake (盘点) ───────────────────────────────────────────────────────

def _mode_count(store, user_cos):
    st.radio(t("Scan action"), ["add", "remove"],
             format_func=lambda d: {"add": "➕ " + t("Add (+1)"),
                                    "remove": "➖ " + t("Remove (−1)")}[d],
             horizontal=True, key="upc_ct_dir")

    def _on_scan():
        upc = str(st.session_state.get("upc_ct_input", "")).strip()
        st.session_state["upc_ct_input"] = ""
        if not upc:
            return
        delta = 1 if st.session_state.get("upc_ct_dir") == "add" else -1
        qty = store.adjust_stocktake(upc, delta)
        rows = store.find_by_upc(upc, companies=user_cos)
        r0 = rows[0] if rows else {}
        st.session_state["upc_ct_last"] = {
            "upc": upc, "qty": qty, "delta": delta,
            "style": r0.get("style", ""), "color": r0.get("color", ""),
            "size": r0.get("size", ""), "known": bool(rows)}

    st.text_input(t("Scan UPC to count"), key="upc_ct_input", on_change=_on_scan,
                  placeholder=t("Each scan adjusts the count by ±1, then Enter"))

    last = st.session_state.get("upc_ct_last")
    if last:
        sign = "➕" if last["delta"] > 0 else "➖"
        ctx = (f"{last['style']} / {last['color']} / {last['size']}"
               if last["known"] else "⚠ " + t("UPC not in any stored PO"))
        st.info(f"{sign} `{last['upc']}` → **{last['qty']}**  ·  {ctx}")

    data = store.load_stocktake()
    if data:
        df = pd.DataFrame(data).rename(columns={
            "upc": "UPC", "qty": "Count", "po_number": "PO", "style": "Style",
            "color": "Color", "size": "Size", "updated_at": "Updated"})
        st.caption(f"**{len(df)}** {t('UPCs counted')}  ·  "
                   f"{t('total units')} **{int(df['Count'].sum())}**")
        st.dataframe(df, use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ " + t("Download stocktake (.xlsx)"),
                           data=_xlsx(df, "盘点"), file_name="stocktake.xlsx",
                           mime=_XLSX_MIME, use_container_width=True, key="upc_ct_dl")
        if c2.button("🗑 " + t("Clear stocktake"), use_container_width=True,
                     key="upc_ct_clear"):
            store.clear_stocktake()
            st.session_state.pop("upc_ct_last", None)
            st.success(t("Stocktake cleared."))
            st.rerun()
    else:
        st.caption(t("No counts yet — start scanning."))
