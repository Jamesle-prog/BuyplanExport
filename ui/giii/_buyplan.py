"""Shared GIII buy-plan builder — the single 生产计划单 code path.

Both the upload-flow auto-download and Reports → **Create Buy Plan (生产计划单)**
build the same enriched production plan through :func:`build_giii_production_plan`,
so there is ONE buy-plan implementation, not two. The legacy grid exporter
(``export_buyplan``) is retained elsewhere only as the cross-check's totals
source, not as a user-facing download.

This module is UI-framework-agnostic (no Streamlit import at module load) so it
stays unit-testable; callers pass the CPRS client in.
"""
from __future__ import annotations

import pandas as pd

from po_extractor.exporters.giii_production_plan import generate_giii_production_plan


class _ReqRow:
    __slots__ = ("po_number", "warehouse_code", "ship_to", "buyer", "is_prepack",
                 "style", "coo")

    def __init__(self, po_number, warehouse_code, ship_to, buyer, is_prepack,
                 style="", coo=""):
        self.po_number = po_number
        self.warehouse_code = warehouse_code
        self.ship_to = ship_to
        self.buyer = buyer
        self.is_prepack = is_prepack
        self.style = style
        self.coo = coo


def _s(rec: dict, *keys) -> str:
    for k in keys:
        v = rec.get(k)
        s = "" if v is None else str(v).strip()
        if s and s.lower() not in ("nan", "none", "nat"):
            return s
    return ""


def resolve_reqs(cprs, meta_df: pd.DataFrame, manual: dict | None = None,
                 translate=None):
    """Resolve CPRS requirements per PO (grouped by brand so a multi-brand
    selection resolves against the right client). Returns
    ``(reqs_by_po, warnings, preview)`` where reqs is ``{po_number:
    RowRequirements}`` — empty when CPRS is unconfigured (the buy plan still
    builds, brand-dependent cells blank). Brand comes off the PO itself
    (division field, else the documented CS/LS/DW prefix); nothing is inferred.
    """
    from po_extractor.ui_helpers.giii_requirements import (
        brand_from_po, prepack_flag, resolve_requirements,
    )
    rows_by_brand: dict[str, list[_ReqRow]] = {}
    for rec in meta_df.to_dict("records"):
        row = _ReqRow(
            po_number=_s(rec, "po_number"),
            warehouse_code=_s(rec, "destination_code"),
            ship_to=_s(rec, "ship_to"),
            buyer=_s(rec, "buyer", "customer"),
            is_prepack=prepack_flag(_s(rec, "packaging"), _s(rec, "hanger")),
            style=_s(rec, "style"),
            coo=_s(rec, "country_of_origin"),
        )
        brand = _s(rec, "division_name") or brand_from_po(_s(rec, "po_number"))
        rows_by_brand.setdefault(brand, []).append(row)

    reqs_by_po: dict[str, object] = {}
    warns: list[str] = []
    preview: list[dict] = []
    for brand, rows in rows_by_brand.items():
        res, w = resolve_requirements(cprs, brand, rows, manual=manual,
                                      translate=translate)
        warns.extend(w)
        for r in rows:
            q = res.get(id(r))
            if q is None:
                continue
            reqs_by_po[r.po_number] = q
            preview.append({
                "PO": r.po_number, "品牌": brand,
                "仓库": q.warehouse, "Account": q.account, "Channel": q.channel,
                "红色箱贴": q.red_sticker, "主箱唛": q.carton_mark,
                "预包比例": q.prepack_ratio, "每箱件数": q.pcs_box,
                "MSRP": q.msrp, "RFID": q.rfid,
            })
    return reqs_by_po, list(dict.fromkeys(warns)), preview


def progress_maps(store, meta_df: pd.DataFrame):
    """合同号 maps + EN→CN colour lookup from the 大货进度表 (per company)."""
    from po_extractor.ui_helpers.combined_summary import build_contract_maps
    from ui.fabric_mapping_view import _company_to_source

    progress: list[dict] = []
    if not meta_df.empty and "company" in meta_df.columns:
        for comp in meta_df["company"].dropna().unique():
            progress.extend(store.load_progress_records(_company_to_source(str(comp))))
    by_po, by_style = build_contract_maps(progress)

    color_lookup: dict[str, str] = {}
    for rec in progress:
        en = str(rec.get("color", "") or "").strip().upper()
        cn = rec.get("cn_color", "") or ""
        if en and cn:
            color_lookup.setdefault(en, cn)
    return by_po, by_style, color_lookup


def build_giii_production_plan(selected: list[str], store, *, cprs=None,
                               manual: dict | None = None, translate=None):
    """Build the GIII 生产计划单 for *selected* PO numbers.

    Returns ``(xlsx_bytes, warnings, preview)``. This is the one buy-plan code
    path shared by the upload auto-download and the Reports button. *cprs* is a
    CPRS client (or None → requirement columns blank).
    """
    if not selected:
        return b"", [], []
    df_all = store.list_pos()
    meta_df = (df_all[df_all["po_number"].isin(selected)]
               if df_all is not None and not df_all.empty else pd.DataFrame())
    reqs, warns, preview = resolve_reqs(cprs, meta_df, manual, translate)
    by_po, by_style, color_en = progress_maps(store, meta_df)
    data = generate_giii_production_plan(
        selected, store, color_lookup_en=color_en,
        contract_by_po=by_po, contract_by_style=by_style, requirements=reqs)
    return data, warns, preview
