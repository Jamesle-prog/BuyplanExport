"""GIII Production Plan (生产计划单 / buy plan) exporter.

Generates one Excel workbook with one sheet per style.  Each sheet follows
the format used in the GIII/HHP production plan template:

  Row 1  : Factory / manufacturer name (from seller field)
  Row 2  : 生产计划单（buy plan）
  Row 4  : 供应商名称 | 日期
  Row 5  : 面料/FIBER | 更新日期
  Row 6  : 品名/Description | 2ND更新日期
  Row 8-9: Two-row merged header (合同号 款号 PO号 CPO# 仓库代码 买家
            颜色英 颜色中 [sizes…] 总数量 离厂时间 红色箱贴纸 主箱唛 备注)
  Row 10+: Data rows, one per (PO, color), with repeated-value columns merged
  Footer : 订单要求 TTL / 溢短装要求 / 包装 / 样衣 / 主箱唛
"""
from __future__ import annotations

import datetime
import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
_THIN   = Side(style="thin")
_MEDIUM = Side(style="medium")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_HDR_FILL    = PatternFill("solid", fgColor="BDD7EE")   # light blue header
_YELLOW_FILL = PatternFill("solid", fgColor="FFFF00")   # yellow highlights
_NO_FILL     = PatternFill("none")

_CENTER   = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT     = Alignment(horizontal="left",   vertical="center", wrap_text=True)

_FONT_TITLE    = Font(name="微软雅黑", bold=True, size=14)
_FONT_SUBTITLE = Font(name="微软雅黑", bold=True, size=12)
_FONT_BOLD     = Font(name="微软雅黑", bold=True, size=10)
_FONT_NORMAL   = Font(name="微软雅黑", size=10)
_FONT_HDR      = Font(name="微软雅黑", size=10)

# Standard size ordering for GIII (add / reorder as needed)
_SIZE_ORDER = [
    "XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL",
    "1X",  "2X",  "3X",  "4X",  "5X",
    "0",  "2",  "4",  "6",  "8",  "10", "12", "14", "16", "18", "20",
    "00", "24", "25", "26", "27", "28", "29", "30", "31",
    "32", "33", "34", "36", "38", "40",
    "ONE SIZE", "OS",
]
_SIZE_RANK = {s.upper(): i for i, s in enumerate(_SIZE_ORDER)}


def _sort_sizes(sizes: list[str]) -> list[str]:
    return sorted(sizes, key=lambda s: (_SIZE_RANK.get(s.strip().upper(), 999), s))


# ---------------------------------------------------------------------------
# Low-level cell helpers
# ---------------------------------------------------------------------------

def _cell(ws, row: int, col: int, value=None,
          font=None, fill=None, border=None, align=None, num_fmt=None):
    c = ws.cell(row, col)
    if value is not None:
        c.value = value
    if font   is not None: c.font      = font
    if fill   is not None: c.fill      = fill
    if border is not None: c.border    = border
    if align  is not None: c.alignment = align
    if num_fmt:             c.number_format = num_fmt
    return c


def _merge(ws, r1: int, c1: int, r2: int, c2: int,
           value=None, font=None, fill=None, border=None, align=None):
    ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
    top = ws.cell(r1, c1)
    if value  is not None: top.value     = value
    if font   is not None: top.font      = font
    if fill   is not None: top.fill      = fill
    if align  is not None: top.alignment = align
    # Apply border to every cell in the merged region
    if border is not None:
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                ws.cell(r, c).border = border
    return top


def _merge_or_set(ws, r1: int, c1: int, r2: int, c2: int, **kw):
    """Merge if r1 != r2 (or c1 != c2), else set single cell."""
    if r1 == r2 and c1 == c2:
        _cell(ws, r1, c1, **kw)
    else:
        _merge(ws, r1, c1, r2, c2, **kw)


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def generate_giii_production_plan(
    selected_pos: list[str],
    store,
    cn_color_lookup: dict | None = None,
) -> bytes:
    """Return an .xlsx workbook (bytes) with one sheet per style.

    Parameters
    ----------
    selected_pos:
        PO numbers to include (must all exist in *store*).
    store:
        A ``POStore`` instance.
    cn_color_lookup:
        Optional mapping ``{(client, brand, norm_en_color): cn_color}``
        from the colour-translation DB.  Pass ``None`` to skip CN colour.
    """
    if not selected_pos:
        return b""

    df_all   = store.list_pos()
    df_pos   = df_all[df_all["po_number"].isin(selected_pos)].copy()
    if df_pos.empty:
        return b""

    df_sizes = store.load_size_rows(selected_pos)
    if df_sizes.empty:
        return b""

    # Normalise size-row column names (load_size_rows uses title case)
    df_sizes = df_sizes.rename(columns={
        "PO Number": "po_number",
        "Style":     "style",
        "Color":     "color",
        "Size":      "size",
        "Units":     "units",
    })

    # Attempt to build CN colour lookup if not supplied
    if cn_color_lookup is None:
        try:
            from po_extractor.store.color_translation_store import ColorTranslationStore
            from po_extractor.config import DB_PATH
            cts = ColorTranslationStore(DB_PATH)
            cn_color_lookup = cts.build_lookup_dict()
        except Exception:
            cn_color_lookup = {}

    wb = Workbook()
    wb.remove(wb.active)

    # Group selected POs by style — preserves multi-style buy plans
    styles_order = df_pos["style"].dropna().unique().tolist()
    for style in styles_order:
        style_pos = df_pos[df_pos["style"] == style]
        style_sizes = df_sizes[df_sizes["po_number"].isin(style_pos["po_number"])]
        if style_sizes.empty:
            continue
        _write_style_sheet(wb, str(style), style_pos, style_sizes, cn_color_lookup)

    if not wb.sheetnames:
        return b""

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Per-style sheet writer
# ---------------------------------------------------------------------------

def _write_style_sheet(
    wb: Workbook,
    style: str,
    style_df: pd.DataFrame,
    sizes_df: pd.DataFrame,
    cn_color_lookup: dict,
) -> None:
    """Append one sheet for *style* to *wb*."""

    # ── Layout constants ──────────────────────────────────────────────────────
    all_sizes = _sort_sizes(
        [str(s).strip() for s in sizes_df["size"].dropna().unique() if str(s).strip()]
    )
    if not all_sizes:
        return
    n_sizes = len(all_sizes)

    # Column index map
    C_CONTRACT  = 1          # A  合同号
    C_STYLE     = 2          # B  款号
    C_PO        = 3          # C  PO号
    C_CPO       = 4          # D  CPO#
    C_WH        = 5          # E  仓库代码
    C_BUYER     = 6          # F  买家
    C_COLOR_EN  = 7          # G  颜色(英文)
    C_COLOR_CN  = 8          # H  颜色(中文)
    C_SZ_START  = 9          # I  first size
    C_SZ_END    = 8 + n_sizes
    C_QTY       = C_SZ_END + 1
    C_SHIP      = C_SZ_END + 2
    C_RED       = C_SZ_END + 3
    C_MARK      = C_SZ_END + 4
    C_NOTE      = C_SZ_END + 5
    N_COLS      = C_NOTE

    # Safe sheet title (max 31 chars, unique)
    sheet_title = style[:31]
    suffix = 2
    while sheet_title in wb.sheetnames:
        sheet_title = f"{style[:28]}_{suffix}"
        suffix += 1
    ws = wb.create_sheet(title=sheet_title)

    # ── Column widths ──────────────────────────────────────────────────────────
    widths = {
        C_CONTRACT: 14, C_STYLE: 12, C_PO: 16, C_CPO: 10,
        C_WH: 10, C_BUYER: 14, C_COLOR_EN: 16, C_COLOR_CN: 14,
        C_QTY: 8, C_SHIP: 12, C_RED: 12, C_MARK: 16, C_NOTE: 16,
    }
    for i in range(C_SZ_START, C_SZ_END + 1):
        widths[i] = 7
    for col_idx, w in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = w

    # ── Representative row for header info ─────────────────────────────────────
    import math as _math

    def _safe(val) -> str:
        """Return clean string; treat NaN / None / 'nan' / 'None' as empty."""
        if val is None:
            return ""
        try:
            if _math.isnan(float(val)):
                return ""
        except (TypeError, ValueError):
            pass
        s = str(val).strip()
        return "" if s.lower() in ("nan", "none", "nat") else s

    rep       = style_df.iloc[0]
    seller    = _safe(rep.get("seller"))
    fabric    = _safe(rep.get("fabric"))
    desc      = _safe(rep.get("description_code")) or _safe(rep.get("style_description"))
    today_str = datetime.date.today().strftime("%Y/%m/%d")

    # ── Row heights ────────────────────────────────────────────────────────────
    for r_h, height in [(1, 26), (2, 22), (4, 18), (5, 18), (6, 18), (8, 22), (9, 18)]:
        ws.row_dimensions[r_h].height = height

    # ─────────────────────────────────────────────────────────────────────────
    # Row 1 — company/factory name
    # ─────────────────────────────────────────────────────────────────────────
    factory_name = seller if seller else "江苏新万新服饰有限公司"
    _merge(ws, 1, 1, 1, N_COLS, factory_name,
           font=_FONT_TITLE, align=Alignment(horizontal="center", vertical="center"))

    # ─────────────────────────────────────────────────────────────────────────
    # Row 2 — title
    # ─────────────────────────────────────────────────────────────────────────
    _merge(ws, 2, 1, 2, N_COLS, "生产计划单（buy plan）",
           font=_FONT_SUBTITLE, align=Alignment(horizontal="center", vertical="center"))

    # Row 3 — blank spacer

    # ─────────────────────────────────────────────────────────────────────────
    # Row 4 — 供应商名称 / 日期
    # ─────────────────────────────────────────────────────────────────────────
    _cell(ws, 4, C_CONTRACT, "供应商名称：", font=_FONT_BOLD, align=_LEFT)
    label_end = min(C_BUYER + 2, N_COLS - 3)
    _merge_or_set(ws, 4, C_STYLE, 4, label_end, value=seller,
                  font=_FONT_NORMAL, align=_LEFT)
    _cell(ws, 4, N_COLS - 2, "日期：",   font=_FONT_BOLD,   align=_LEFT)
    _cell(ws, 4, N_COLS - 1, today_str,  font=_FONT_NORMAL, align=_LEFT)

    # ─────────────────────────────────────────────────────────────────────────
    # Row 5 — 面料/FIBER / 更新日期
    # ─────────────────────────────────────────────────────────────────────────
    _cell(ws, 5, C_CONTRACT, "面料/FIBER:", font=_FONT_BOLD, align=_LEFT)
    _merge_or_set(ws, 5, C_STYLE, 5, label_end, value=fabric,
                  font=_FONT_NORMAL, align=_LEFT)
    _cell(ws, 5, N_COLS - 2, "更新日期：", font=_FONT_BOLD, align=_LEFT)

    # ─────────────────────────────────────────────────────────────────────────
    # Row 6 — 品名/Description / 2ND更新日期
    # ─────────────────────────────────────────────────────────────────────────
    _cell(ws, 6, C_CONTRACT, "品名/Description:", font=_FONT_BOLD, align=_LEFT)
    _merge_or_set(ws, 6, C_PO, 6, label_end, value=desc,
                  font=_FONT_NORMAL, align=_LEFT)
    _cell(ws, 6, N_COLS - 2, "2ND更新日期：", font=_FONT_BOLD, align=_LEFT)

    # ─────────────────────────────────────────────────────────────────────────
    # Rows 8-9 — two-row header
    # ─────────────────────────────────────────────────────────────────────────
    fixed_headers = [
        (C_CONTRACT, "合同号",     _HDR_FILL),
        (C_STYLE,    "款号",       _HDR_FILL),
        (C_PO,       "PO号",       _HDR_FILL),
        (C_CPO,      "CPO#",       _HDR_FILL),
        (C_WH,       "仓库代码",   _YELLOW_FILL),
        (C_BUYER,    "买家",       _HDR_FILL),
        (C_COLOR_EN, "颜色(英文)", _HDR_FILL),
        (C_COLOR_CN, "颜色(中文)", _HDR_FILL),
        (C_QTY,      "总数量",     _HDR_FILL),
        (C_SHIP,     "离厂时间",   _HDR_FILL),
        (C_RED,      "红色箱贴纸", _YELLOW_FILL),
        (C_MARK,     "主箱唛",     _YELLOW_FILL),
        (C_NOTE,     "备注",       _HDR_FILL),
    ]
    for col_idx, label, fill in fixed_headers:
        _merge(ws, 8, col_idx, 9, col_idx, label,
               font=_FONT_HDR, fill=fill, border=_BORDER, align=_CENTER)

    # Size group header (row 8) + individual sizes (row 9)
    _merge(ws, 8, C_SZ_START, 8, C_SZ_END, "尺码搭配",
           font=_FONT_HDR, fill=_HDR_FILL, border=_BORDER, align=_CENTER)
    for i, sz in enumerate(all_sizes):
        _cell(ws, 9, C_SZ_START + i, sz,
              font=_FONT_HDR, fill=_HDR_FILL, border=_BORDER, align=_CENTER)

    # ─────────────────────────────────────────────────────────────────────────
    # Data rows
    # ─────────────────────────────────────────────────────────────────────────
    DATA_START = 10
    current_row = DATA_START
    grand_total = 0

    # Build a flat list of row records first so we know merge ranges
    records: list[dict] = []

    for _, po_row in style_df.iterrows():
        po_num    = po_row["po_number"]
        cpo       = str(po_row.get("cpo")          or "").strip()
        wh_code   = str(po_row.get("destination_code") or "").strip()
        buyer     = str(po_row.get("customer")     or po_row.get("buyer") or "").strip()
        ship_date = str(po_row.get("factory_ship_date") or po_row.get("xport_date") or "").strip()
        packaging = str(po_row.get("packaging")    or "").strip()
        hanger    = str(po_row.get("hanger")       or "").strip()
        note      = " + ".join(filter(None, [packaging, hanger]))

        po_sizes = sizes_df[sizes_df["po_number"] == po_num]
        if po_sizes.empty:
            continue

        colors = po_sizes["color"].dropna().unique().tolist()
        po_start_row = current_row

        for color_en in colors:
            color_str = str(color_en or "").strip()
            cs = po_sizes[po_sizes["color"] == color_en]

            # CN colour lookup — try (GIII, brand, norm), then (GIII, "", norm)
            color_cn = ""
            if cn_color_lookup and color_str:
                try:
                    from po_extractor.store.color_translation_store import _normalize_color_name
                    norm = _normalize_color_name(color_str)
                    color_cn = (cn_color_lookup.get(("GIII", "", norm)) or
                                cn_color_lookup.get(("GIII", "GIII", norm)) or "")
                    if not color_cn:
                        # Scan all brands for this client as fallback
                        for (cli, _br, nc), val in cn_color_lookup.items():
                            if cli == "GIII" and nc == norm and val:
                                color_cn = val
                                break
                except Exception:
                    pass

            # Pivot size quantities
            size_qty: dict[str, int] = {}
            for _, sr in cs.iterrows():
                sz  = str(sr["size"]).strip()
                qty = int(sr["units"]) if pd.notna(sr["units"]) else 0
                size_qty[sz] = size_qty.get(sz, 0) + qty
            total_qty = sum(size_qty.values())
            grand_total += total_qty

            records.append({
                "row":          current_row,
                "po_start":     po_start_row,
                "po_num":       po_num,
                "cpo":          cpo,
                "wh_code":      wh_code,
                "buyer":        buyer,
                "ship_date":    ship_date,
                "note":         note,
                "color_en":     color_str,
                "color_cn":     color_cn,
                "size_qty":     size_qty,
                "total_qty":    total_qty,
            })
            current_row += 1

        # Tag PO end row on all records for this PO
        for rec in records:
            if rec["po_start"] == po_start_row and "po_end" not in rec:
                rec["po_end"] = current_row - 1

    style_end_row = current_row - 1

    # ── Write cell values ──────────────────────────────────────────────────────
    for rec in records:
        r = rec["row"]
        ws.row_dimensions[r].height = 18

        _cell(ws, r, C_COLOR_EN, rec["color_en"],  font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _cell(ws, r, C_COLOR_CN, rec["color_cn"],  font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _cell(ws, r, C_QTY,      rec["total_qty"], font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _cell(ws, r, C_NOTE,     rec["note"],       font=_FONT_NORMAL, border=_BORDER, align=_CENTER)

        for j, sz in enumerate(all_sizes):
            qty = rec["size_qty"].get(sz)
            _cell(ws, r, C_SZ_START + j, qty,
                  font=_FONT_NORMAL, border=_BORDER, align=_CENTER)

        # Cells that will be covered by merges below still need border set
        for col in (C_CONTRACT, C_STYLE, C_PO, C_CPO, C_WH, C_BUYER, C_SHIP, C_RED, C_MARK):
            ws.cell(r, col).border = _BORDER

    # ── PO-level merges (PO号 / CPO# / 仓库代码 / 买家 / 离厂时间) ────────────────
    po_groups: dict[str, list[dict]] = {}
    for rec in records:
        po_groups.setdefault(rec["po_num"], []).append(rec)

    for po_num, grp in po_groups.items():
        r0, r1 = grp[0]["row"], grp[-1]["row"]
        rep    = grp[0]
        _merge_or_set(ws, r0, C_PO,    r1, C_PO,    value=rep["po_num"],   font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _merge_or_set(ws, r0, C_CPO,   r1, C_CPO,   value=rep["cpo"],      font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _merge_or_set(ws, r0, C_WH,    r1, C_WH,    value=rep["wh_code"],  font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _merge_or_set(ws, r0, C_BUYER, r1, C_BUYER, value=rep["buyer"],    font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _merge_or_set(ws, r0, C_SHIP,  r1, C_SHIP,  value=rep["ship_date"],font=_FONT_NORMAL, border=_BORDER, align=_CENTER)

    # ── Style-level merges (合同号 / 款号 / 红色箱贴纸 / 主箱唛) ─────────────────
    if records:
        r0, r1 = DATA_START, style_end_row
        _merge_or_set(ws, r0, C_CONTRACT, r1, C_CONTRACT, value="",     font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _merge_or_set(ws, r0, C_STYLE,    r1, C_STYLE,    value=style,  font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _merge_or_set(ws, r0, C_RED,      r1, C_RED,      value="无",   font=_FONT_NORMAL, border=_BORDER, align=_CENTER)
        _merge_or_set(ws, r0, C_MARK,     r1, C_MARK,     value="",     font=_FONT_NORMAL, border=_BORDER, align=_CENTER)

    # ─────────────────────────────────────────────────────────────────────────
    # Footer rows
    # ─────────────────────────────────────────────────────────────────────────
    fr = current_row  # first footer row

    # TTL total
    _merge(ws, fr, C_CONTRACT, fr, C_SZ_END - 1, "订单要求：",
           font=_FONT_BOLD, align=_LEFT)
    _cell(ws, fr, C_SZ_END, "TTL", font=_FONT_BOLD, border=_BORDER, align=_CENTER)
    _cell(ws, fr, C_QTY, grand_total,  font=_FONT_BOLD, border=_BORDER, align=_CENTER)
    fr += 1

    for text in [
        "溢短装要求：",
        "包装：见如上说明",
        "样衣：上线后提供照片样S码1件  船样S码2件",
        "主箱唛：",
    ]:
        _merge(ws, fr, 1, fr, N_COLS, text, font=_FONT_NORMAL, align=_LEFT)
        ws.row_dimensions[fr].height = 16
        fr += 1

    # ── Print settings ─────────────────────────────────────────────────────────
    ws.print_area = f"A1:{get_column_letter(N_COLS)}{fr - 1}"
    ws.page_setup.orientation   = "landscape"
    ws.page_setup.fitToWidth    = 1
    ws.page_setup.fitToHeight   = 0
    ws.page_setup.paperSize     = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left   = 0.25
    ws.page_margins.right  = 0.25
    ws.page_margins.top    = 0.5
    ws.page_margins.bottom = 0.5
