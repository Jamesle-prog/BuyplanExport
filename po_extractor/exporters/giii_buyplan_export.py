"""GIII buy-plan exporter — the real GIII 生产计划单 (buy plan) format.

Generates the A–W bilingual layout of the canonical GIII buy plan (see
docs/GIII_BuyPlan_Field_Mapping.md) from scratch, rather than filling a static
template — the reference file is a produced document, and generating it makes
every cell testable and the layout robust to size-count changes.

Sources per the spec:
* PO / 进度表 / color-translation → the caller assembles these into ``rows``.
* CPRS knowledge base → this exporter resolves the requirement-driven columns
  (red sticker P, carton mark Q, prepack ratio T, pcs/box U, MSRP V, RFID W)
  and the warehouse code E, via an optional :class:`CprsClient`. When no client
  is supplied (or a lookup fails) those cells are left blank — the buy plan
  still generates.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

# Fixed left columns (before the dynamic size block).
_LEFT = [
    ("合同号", "Contract No."),   # A
    ("款号", "Style"),            # B
    ("PO号", "PO No."),           # C
    ("CPO#", "CPO#"),             # D
    ("仓库代码", "Warehouse"),    # E
    ("买家", "Buyer"),            # F
    ("颜色(英文)", "Color EN"),   # G
    ("颜色(中文)", "Color CN"),   # H
]

# Fixed right columns (after the dynamic size block).
_RIGHT = [
    ("总数量", "Total"),          # N-ish
    ("离厂时间", "X-FTY"),        # O
    ("红色箱贴纸", "Red Sticker"),  # P
    ("主箱唛", "Carton Mark"),    # Q
    ("包装方式", "Packing"),      # R
    ("是否预包", "Prepack"),      # S
    ("预包比例", "Prepack Ratio"),  # T
    ("每箱件数", "PCs/Box"),      # U
    ("MSRP", "MSRP"),             # V
    ("RFID", "RFID"),             # W
]

_NAVY = "FF1F3864"
_WHITE = "FFFFFFFF"
_GREY = "FFD9D9D9"
_YELLOW = "FFFFF2CC"


@dataclass
class BuyPlanRow:
    contract_no: str = ""
    style: str = ""
    po_number: str = ""
    cpo: str = ""
    ship_to: str = ""          # resolved to warehouse code via CPRS
    warehouse_code: str = ""   # if already known, skips CPRS resolution
    buyer: str = ""
    color_en: str = ""
    color_cn: str = ""
    sizes: dict = field(default_factory=dict)   # {"XS": 9, "S": 12, ...}
    ex_fty: str = ""
    packing_method: str = ""   # R — PO-sourced
    is_prepack: bool | None = None  # S — PO-sourced (PPK marker)

    @property
    def total(self) -> int:
        return sum(int(v or 0) for v in self.sizes.values())


@dataclass
class BuyPlanHeader:
    manufacturer: str = "江苏新万新服饰有限公司"
    supplier: str = ""
    fabric: str = ""
    description: str = ""
    brand: str = ""            # drives CPRS clientId
    date: str = ""
    updated: str = ""
    updated_2nd: str = ""


def _present_sizes(rows: list[BuyPlanRow]) -> list[str]:
    """Union of size keys across rows, in a stable garment order."""
    order = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "1X", "2X", "3X",
             "OSFM", "OS"]
    seen = {s for r in rows for s in r.sizes}
    ordered = [s for s in order if s in seen]
    return ordered + [s for s in sorted(seen) if s not in order]


def _resolve_cprs_fields(rows: list[BuyPlanRow], header: BuyPlanHeader, cprs):
    """Return {id(row): {warehouse, red_sticker, carton_mark, prepack_ratio,
    pcs_box, msrp, rfid, red_img, mark_img}} using the CPRS client. Blank
    dict entries when *cprs* is None or a lookup fails (graceful)."""
    out: dict[int, dict] = {}
    if cprs is None:
        return out
    client_id = cprs.resolve_client(header.brand) if header.brand else None
    if not client_id:
        return out

    for r in rows:
        wh = r.warehouse_code or (cprs.resolve_warehouse(r.ship_to, client_id) or "")
        account = cprs.resolve_account(r.buyer, client_id) if r.buyer else None
        order = {"clientId": client_id, "channel": "WHOLESALE"}
        if wh:
            order["warehouseCode"] = wh
        if account:
            order["accountCode"] = account

        carton = cprs.carton_results(order)
        flags = cprs.warehouse_flags(client_id, wh) if wh else {"rfid": None, "msrp": None}

        red = carton.get("red_carton_sticker")
        mark = carton.get("carton_marking") or carton.get("warehouse_diamond")
        pack = _packaging_results(cprs, order)

        out[id(r)] = {
            "warehouse": wh,
            "red_sticker": _sticker_text(red),
            "carton_mark": _result_text(mark),
            "prepack_ratio": pack.get("ratio", ""),
            "pcs_box": pack.get("pcs_box", ""),
            "msrp": _yn(flags.get("msrp")),
            "rfid": _yn(flags.get("rfid")),
            "red_img": _image_bytes(cprs, red),
            "mark_img": _image_bytes(cprs, mark),
        }
    return out


def _packaging_results(cprs, order: dict) -> dict:
    out = {}
    for res in cprs.evaluate(order):
        if res.get("domain") != "packaging":
            continue
        rj = res.get("resultJson", {}) or {}
        if "ratio" in rj and "ratio" not in out:
            out["ratio"] = str(rj.get("ratio", ""))
        for k in ("pcs_per_carton", "units_per_carton", "pack_out"):
            if k in rj and "pcs_box" not in out:
                out["pcs_box"] = str(rj.get(k, ""))
    return out


def _sticker_text(res) -> str:
    if not res:
        return ""
    if res.get("status") == "not_applicable":
        return "无需"
    rj = res.get("resultJson", {}) or {}
    return str(rj.get("code") or rj.get("value") or rj.get("standard") or "")


def _result_text(res) -> str:
    if not res or res.get("status") == "not_applicable":
        return ""
    rj = res.get("resultJson", {}) or {}
    return str(rj.get("value") or rj.get("standard") or rj.get("code") or "")


def _image_bytes(cprs, res):
    if not res:
        return None
    rj = res.get("resultJson", {}) or {}
    img_id = rj.get("image_id") or rj.get("imageId")
    return cprs.manual_image(img_id) if img_id else None


def _yn(v) -> str:
    return "" if v is None else ("Y" if v else "N")


def export_giii_buyplan(header: BuyPlanHeader, rows: list[BuyPlanRow],
                        cprs=None) -> bytes:
    """Build the GIII buy-plan workbook and return the .xlsx bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    sizes = _present_sizes(rows)
    n_left, n_size, n_right = len(_LEFT), len(sizes), len(_RIGHT)
    n_cols = n_left + n_size + n_right
    cprs_fields = _resolve_cprs_fields(rows, header, cprs)

    wb = Workbook()
    ws = wb.active
    ws.title = (rows[0].style if rows else "BuyPlan")[:31] or "BuyPlan"

    thin = Side(style="thin", color="FF000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def cell(r, c, v, *, bold=False, bg=None, white=False, center=True, num=None):
        cl = ws.cell(r, c, v)
        cl.font = Font(name="Arial", size=10, bold=bold,
                       color=_WHITE if white else "FF000000")
        if bg:
            cl.fill = PatternFill("solid", fgColor=bg)
        cl.alignment = Alignment(horizontal="center" if center else "left",
                                 vertical="center", wrap_text=True)
        cl.border = border
        if num:
            cl.number_format = num
        return cl

    last_col = get_column_letter(n_cols)

    # ── Banner + title ───────────────────────────────────────────────────────
    ws.merge_cells(f"A1:{last_col}1")
    cell(1, 1, header.manufacturer, bold=True, bg=_NAVY, white=True)
    ws.merge_cells(f"A2:{last_col}2")
    cell(2, 1, "生产计划单（buy plan）", bold=True, bg=_GREY)

    # ── Header meta (rows 4–6) ───────────────────────────────────────────────
    meta = [("供应商名称：", header.supplier, "日期：", header.date),
            ("面料/FIBER:", header.fabric, "更新日期：", header.updated),
            ("品名/Description:", header.description, "2ND更新日期：", header.updated_2nd)]
    for i, (la, va, lb, vb) in enumerate(meta):
        r = 4 + i
        cell(r, 1, la, bold=True, center=False)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=max(2, n_cols - 3))
        cell(r, 2, va, center=False)
        cell(r, n_cols - 1, lb, bold=True)
        cell(r, n_cols, vb)

    # ── Column headers (rows 8–9) ────────────────────────────────────────────
    hr1, hr2 = 8, 9
    ci = 1
    for zh, en in _LEFT:
        cell(hr1, ci, zh, bold=True, bg=_NAVY, white=True)
        cell(hr2, ci, en, bold=True, bg=_NAVY, white=True)
        ci += 1
    # size block: merged "尺码搭配" over row 8, size letters on row 9
    if n_size:
        ws.merge_cells(start_row=hr1, start_column=ci, end_row=hr1, end_column=ci + n_size - 1)
        cell(hr1, ci, "尺码搭配 / SIZE BREAK DOWN", bold=True, bg=_NAVY, white=True)
        for s in sizes:
            cell(hr2, ci, s, bold=True, bg=_NAVY, white=True)
            ci += 1
    for zh, en in _RIGHT:
        cell(hr1, ci, zh, bold=True, bg=_NAVY, white=True)
        cell(hr2, ci, en, bold=True, bg=_NAVY, white=True)
        ci += 1

    # ── Data rows ────────────────────────────────────────────────────────────
    r = hr2 + 1
    for row in rows:
        cf = cprs_fields.get(id(row), {})
        left_vals = [row.contract_no, row.style, row.po_number, row.cpo,
                     cf.get("warehouse", row.warehouse_code), row.buyer,
                     row.color_en, row.color_cn]
        right_vals = [
            row.total, row.ex_fty,
            cf.get("red_sticker", ""), cf.get("carton_mark", ""),
            row.packing_method,
            _yn(row.is_prepack), cf.get("prepack_ratio", ""),
            cf.get("pcs_box", ""), cf.get("msrp", ""), cf.get("rfid", ""),
        ]
        ci = 1
        for v in left_vals:
            cell(r, ci, v, center=False); ci += 1
        for s in sizes:
            cell(r, ci, int(row.sizes.get(s, 0) or 0)); ci += 1
        for v in right_vals:
            cell(r, ci, v); ci += 1
        r += 1

    # ── TTL + per-color subtotals ────────────────────────────────────────────
    total_col = n_left + n_size + 1   # 总数量 column index
    grand = sum(row.total for row in rows)
    cell(r, 1, "TTL", bold=True, bg=_YELLOW, center=False)
    cell(r, total_col, grand, bold=True, bg=_YELLOW)
    r += 1

    by_color: dict[str, dict] = {}
    for row in rows:
        key = row.color_cn or row.color_en or "—"
        acc = by_color.setdefault(key, {s: 0 for s in sizes})
        for s in sizes:
            acc[s] += int(row.sizes.get(s, 0) or 0)
    for color, acc in by_color.items():
        cell(r, n_left, color, bold=True, bg=_GREY, center=False)
        ci = n_left + 1
        for s in sizes:
            cell(r, ci, acc[s], bold=True, bg=_GREY); ci += 1
        cell(r, total_col, sum(acc.values()), bold=True, bg=_GREY)
        r += 1

    # ── Column widths + freeze ───────────────────────────────────────────────
    for c in range(1, n_cols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 11
    ws.column_dimensions["A"].width = 15
    ws.freeze_panes = "A10"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
