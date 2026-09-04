"""Fabric presentation sheets (面料推荐单) — build, export, and track.

Pick fabrics out of the master database, build a customer-facing
recommendation sheet from them, and export it with the price columns chosen
at export time.  Each sheet gets a QR code; scanning it on the LAN (via the
``web_scan`` service) records when the sheet went out and what was on it.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ui.i18n import t
from ui.shared import guard_multiselect_state
from ui.stores import get_fabric_presentation_store, get_app_settings_store
from po_extractor.exporters.fabric_presentation_export import (
    PRICE_BOTH, PRICE_MODE_LABELS, PRICE_MODES, PRICE_RMB, PRICE_USD,
    build_presentation_workbook,
)
from po_extractor.utils.fabric_quote import (
    DEFAULT_FX_RATE, DEFAULT_MARKUP, DEFAULT_ROUND_STEP, usd_per_yard,
)
from po_extractor.utils.qr import available as qr_available

# Where the QR codes point.  Stored in app settings so it survives restarts
# and is set once per site, not per sheet.
_SCAN_URL_KEY = "fabric_presentation_scan_base_url"

_XLSX_MIME = ("application/vnd.openxmlformats-officedocument"
              ".spreadsheetml.sheet")

_FABRIC_TYPES = [
    "New fabric (HHN-Initiated)",
    "New fabric (Client-Initiated)",
]


def _fabric_to_line(rec: dict) -> dict:
    """Map a fabric_master record onto a presentation line.

    Width prints as ``full/cuttable`` — the source sheet's own convention —
    and falls back to whichever of the two is present.
    """
    full = rec.get("full_width_in")
    cut = rec.get("cuttable_width_in")
    if full and cut:
        width = f"{full:g}/{cut:g}"
    elif full or cut:
        width = f"{(full or cut):g}"
    else:
        width = ""
    # cost_per_m is the negotiated over-MOQ price; spot_price_m is the
    # in-stock price and is the sensible fallback when no contract price
    # has been agreed yet.
    price = rec.get("cost_per_m") or rec.get("spot_price_m")
    return {
        "quality_no":  rec.get("quality_no") or "",
        "content":     rec.get("composition_en") or "",
        "description": rec.get("structure_en") or "",
        "weight_gsm":  rec.get("weight_gsm"),
        "width_in":    width,
        "moq_y":       rec.get("moq_y"),
        "mcq_y":       rec.get("mcq_y"),
        "price_rmb_m": price,
    }


def _fabric_db_presentation_section(store) -> None:
    """Render the presentation builder + history."""
    st.subheader(f"📋 {t('Fabric Presentation Sheets')}")
    st.caption(t(
        "Build a fabric recommendation sheet for a customer from the master "
        "database. Prices are frozen onto the sheet when you build it, so a "
        "quote you sent stays what you sent. Each sheet carries a QR code — "
        "scanning it on the LAN records when it went out."
    ))

    pres_store = get_fabric_presentation_store()
    _build_form(store, pres_store)
    st.divider()
    _history(pres_store)


# ── build ───────────────────────────────────────────────────────────────────

def _build_form(store, pres_store) -> None:
    with st.expander(f"➕ {t('Build a new presentation sheet')}", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            title = st.text_input(t("Sheet title"), value="GIII-SWIMMING",
                                  key="fp_title",
                                  help=t("Becomes the worksheet name."))
            customer = st.text_input(t("Customer"), value="GIII", key="fp_customer")
        with c2:
            season = st.text_input(t("Season"), key="fp_season")
            sub_date = st.date_input(t("Submission date"), value=date.today(),
                                     key="fp_date")
        with c3:
            fabric_type = st.selectbox(t("Type"), _FABRIC_TYPES, key="fp_type")

        st.markdown(f"**{t('Quoting parameters')}**")
        st.caption(t(
            "USD/Y = CEILING(RMB/M × markup ÷ FX × 0.9144, step). These are "
            "stored with the sheet so an old quote can always be reproduced."
        ))
        q1, q2, q3 = st.columns(3)
        markup = q1.number_input(t("Markup (×)"), value=float(DEFAULT_MARKUP),
                                 min_value=1.0, max_value=3.0, step=0.05,
                                 format="%.2f", key="fp_markup")
        fx = q2.number_input(t("FX rate (RMB per USD)"), value=float(DEFAULT_FX_RATE),
                             min_value=1.0, max_value=20.0, step=0.1,
                             format="%.2f", key="fp_fx")
        step = q3.number_input(t("Round up to ($)"), value=float(DEFAULT_ROUND_STEP),
                               min_value=0.0, max_value=1.0, step=0.01,
                               format="%.2f", key="fp_step")

        st.markdown(f"**{t('Choose fabrics')}**")
        query = st.text_input(
            f"🔍 {t('Search the fabric database')}", key="fp_search",
            placeholder="e.g. Jersey · HHN-JS · Polyester",
        )
        rows = store.search(query.strip(), limit=200) if query.strip() else []
        if query.strip() and not rows:
            st.warning(t("No fabrics match your search."))

        options = [r.get("quality_no") for r in rows if r.get("quality_no")]
        by_code = {r.get("quality_no"): r for r in rows}
        # Keep anything already picked from an earlier search visible in the
        # options list, or selecting across two searches silently drops the
        # first batch.
        picked_key = "fp_picked"
        already: dict = st.session_state.setdefault("fp_picked_recs", {})
        merged = list(dict.fromkeys(list(already.keys()) + options))
        by_code.update(already)
        guard_multiselect_state(picked_key, merged)
        picked = st.multiselect(t("Fabrics on this sheet"), merged, key=picked_key)
        st.session_state["fp_picked_recs"] = {
            c: by_code[c] for c in picked if c in by_code
        }

        if not picked:
            st.info(t("Search above, then tick the fabrics to include."))
            return

        lines = [_fabric_to_line(by_code[c]) for c in picked if c in by_code]
        preview = pd.DataFrame([{
            t("HHN_Fabric#"): l["quality_no"],
            t("Description"): l["description"],
            t("gsm"):         l["weight_gsm"],
            t("Width"):       l["width_in"],
            "RMB/M":          l["price_rmb_m"],
            "USD/Y":          usd_per_yard(l["price_rmb_m"], markup=markup,
                                           fx_rate=fx, round_step=step),
        } for l in lines])
        st.dataframe(preview, width="stretch", hide_index=True)

        missing = [l["quality_no"] for l in lines if not l["price_rmb_m"]]
        if missing:
            st.warning(
                f"⚠ {len(missing)} " +
                t("fabric(s) have no price in the database and will print "
                  "blank: ") + ", ".join(missing[:8]) +
                ("…" if len(missing) > 8 else ""))

        if st.button(f"📋 {t('Create sheet')}", type="primary", key="fp_create"):
            pres = pres_store.create(
                lines=lines, title=title, customer=customer, season=season,
                submission_date=str(sub_date), fabric_type=fabric_type,
                markup=markup, fx_rate=fx, round_step=step,
                created_by=st.session_state.get("username") or "",
            )
            st.success(
                f"{t('Sheet created.')} {t('Sheet ID:')} `{pres['token']}` — "
                + t("download it from the list below."))
            st.session_state[picked_key] = []
            st.session_state["fp_picked_recs"] = {}
            st.rerun()


# ── history + export ────────────────────────────────────────────────────────

def _history(pres_store) -> None:
    st.markdown(f"**{t('Presentation history')}**")

    base_url = _scan_base_url_control()

    df = pres_store.list_all()
    if df.empty:
        st.info(t("No presentation sheets yet."))
        return

    show = df.rename(columns={
        "title": t("Title"), "customer": t("Customer"),
        "submission_date": t("Submitted"), "n_lines": t("Fabrics"),
        "n_scans": t("Scans"), "first_scan": t("First scanned"),
        "token": t("Sheet ID"), "created_by": t("By"),
    })
    st.dataframe(
        show[[t("Sheet ID"), t("Title"), t("Customer"), t("Submitted"),
              t("Fabrics"), t("Scans"), t("First scanned"), t("By")]],
        width="stretch", hide_index=True)

    ids = df["id"].tolist()
    labels = {
        int(r.id): f"{r.token} · {r.title or '—'} · {r.customer or '—'} "
                   f"({int(r.n_lines)} {t('fabrics')})"
        for r in df.itertuples()
    }
    sel = st.selectbox(t("Select a sheet to export or delete"), ids,
                       format_func=lambda i: labels.get(int(i), str(i)),
                       key="fp_sel")
    if sel is None:
        return

    e1, e2 = st.columns([2, 1])
    with e1:
        mode = st.radio(
            t("Which price to show on the export"), PRICE_MODES,
            format_func=lambda m: t(PRICE_MODE_LABELS[m]),
            key="fp_price_mode", horizontal=False,
        )
        if mode in (PRICE_RMB, PRICE_BOTH):
            st.warning(t(
                "⚠ This export includes the internal RMB/M cost — it is a "
                "review copy, not for sending to the customer."))
    with e2:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if st.button(f"🗑 {t('Delete sheet')}", key="fp_del"):
            pres_store.delete(int(sel))
            st.success(t("Sheet deleted."))
            st.rerun()

    pres = pres_store.get(int(sel))
    lines = pres_store.lines(int(sel))
    if not pres or not lines:
        return

    if not qr_available():
        st.info(t(
            "QR codes need the `segno` package — run `pip install segno` to "
            "include them. The sheet exports fine without one."))
    elif not base_url:
        st.info(t(
            "Set the scanner URL above to put a working QR code on the sheet."))

    data = build_presentation_workbook(pres, lines, price_mode=mode,
                                       scan_base_url=base_url)
    safe_title = (pres.get("title") or "presentation").replace(" ", "_")
    st.download_button(
        f"⬇️ {t('Download presentation (.xlsx)')}",
        data=data,
        file_name=f"HHN_Presentation_{safe_title}_{pres.get('submission_date','')}.xlsx",
        mime=_XLSX_MIME, key="fp_dl", type="primary",
    )

    scans = pres_store.scans(int(sel))
    if scans:
        with st.expander(f"📱 {t('Scan log')} ({len(scans)})"):
            st.dataframe(
                pd.DataFrame(scans)[["scanned_at", "client_ip", "user_agent"]]
                  .rename(columns={"scanned_at": t("Scanned at"),
                                   "client_ip": t("From"),
                                   "user_agent": t("Device")}),
                width="stretch", hide_index=True)
    else:
        st.caption(t("Not scanned yet — the QR code has not been opened."))


def _scan_base_url_control() -> str:
    """Read/write the scanner base URL the QR codes point at."""
    settings = get_app_settings_store()
    current = settings.get(_SCAN_URL_KEY, "") or ""
    with st.expander(f"⚙️ {t('QR scanner URL')}", expanded=not current):
        st.caption(t(
            "The LAN address of the web_scan service (it prints this on "
            "start-up). QR codes on the sheets point here, and opening one "
            "records the scan."
        ))
        val = st.text_input(t("Scanner base URL"), value=current,
                            placeholder="http://192.168.0.153:8502",
                            key="fp_scan_url")
        if st.button(t("Save URL"), key="fp_scan_url_save"):
            settings.set(_SCAN_URL_KEY, val.strip(),
                         updated_by=st.session_state.get("username") or "")
            st.success(t("Saved."))
            st.rerun()
    return current
