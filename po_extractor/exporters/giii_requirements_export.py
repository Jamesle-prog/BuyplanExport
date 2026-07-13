"""GIII PO requirements document — Excel export of CPRS requirement sets.

Generated automatically at upload time (when CPRS is configured): a Summary
sheet (one row per PO's order context, with per-status counts) plus one sheet
per PO listing every resolved requirement — domain, subtype, status, and the
requirement text extracted from the CPRS result.

Input is the ``contexts`` list from
:func:`po_extractor.ui_helpers.giii_requirements.resolve_po_requirements`.
"""
from __future__ import annotations

import io
import re

_NAVY = "FF1F3864"
_WHITE = "FFFFFFFF"
_GREY = "FFD9D9D9"
_YELLOW = "FFFFF2CC"
_RED = "FFFFC7CE"
_GREEN = "FFE2EFDA"

_STATUS_CN = {
    "confirmed": "必须 Required",
    "pending_input": "待定 Pending",
    "conflict": "冲突 Conflict",
    "not_applicable": "不适用 N/A",
    "missing_mandatory_context": "缺少信息 Missing context",
}

_STATUS_BG = {
    "confirmed": _GREEN,
    "pending_input": _YELLOW,
    "conflict": _RED,
}

_STATUS_RANK = {"confirmed": 0, "pending_input": 1, "conflict": 2,
                "missing_mandatory_context": 3, "not_applicable": 4}

# resultJson keys most likely to carry the human-readable spec, in order.
_TEXT_KEYS = ("current_wording", "standard", "description", "prompt",
              "applies_to", "reference", "change_summary")


def _req_text(result: dict) -> str:
    """Extract a readable requirement text from a CPRS result."""
    rj = result.get("resultJson") or {}
    parts = [str(rj[k]) for k in _TEXT_KEYS if rj.get(k)]
    if not parts:
        # compact leftover scalars (skip booleans/ids/nested structures)
        parts = [f"{k}: {v}" for k, v in rj.items()
                 if isinstance(v, (str, int, float)) and not isinstance(v, bool)
                 and k not in ("source", "scope_level", "updated")][:4]
    return " | ".join(parts)[:500]


def _sheet_name(base: str, used: set[str]) -> str:
    name = re.sub(r"[\\/*?:\[\]]", "_", base or "PO")[:28] or "PO"
    candidate, i = name, 2
    while candidate in used:
        candidate = f"{name}_{i}"
        i += 1
    used.add(candidate)
    return candidate


def _thumb(raw: bytes, max_h: int = 70):
    """Scale image bytes to a thumbnail; return (PNG BytesIO, w, h) or None on
    bad bytes (a broken image must never fail the document)."""
    try:
        from PIL import Image as PImage
        im = PImage.open(io.BytesIO(raw))
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        w, h = im.size
        if h > max_h:
            w = max(1, int(w * max_h / h))
            h = max_h
            im = im.resize((w, h))
        out = io.BytesIO()
        im.save(out, format="PNG")
        out.seek(0)
        return out, w, h
    except Exception:
        return None


def _embed_thumbs(ws, row: int, col: int, images) -> None:
    """Embed each image side-by-side starting at (row, col); size the row to
    fit and widen the columns used. No-op when there are no images."""
    if not images:
        return
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.utils import get_column_letter
    x, max_h = col, 0
    for raw in images:
        t = _thumb(raw)
        if not t:
            continue
        buf, w, h = t
        img = XLImage(buf)
        img.width, img.height = w, h
        letter = get_column_letter(x)
        ws.add_image(img, f"{letter}{row}")
        cur = ws.column_dimensions[letter].width or 0
        ws.column_dimensions[letter].width = max(cur, w / 7.0 + 2)
        x += 1
        max_h = max(max_h, h)
    if max_h:
        cur = ws.row_dimensions[row].height or 15
        ws.row_dimensions[row].height = max(cur, max_h * 0.78)


def export_giii_requirements(contexts: list[dict],
                             warnings: list[str] | None = None) -> bytes:
    """Build the requirements workbook; return .xlsx bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    thin = Side(style="thin", color="FF000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()

    def cell(ws, r, c, v, *, bold=False, bg=None, white=False, wrap=True,
             center=False):
        cl = ws.cell(r, c, v)
        cl.font = Font(name="Arial", size=10, bold=bold,
                       color=_WHITE if white else "FF000000")
        if bg:
            cl.fill = PatternFill("solid", fgColor=bg)
        cl.alignment = Alignment(horizontal="center" if center else "left",
                                 vertical="center", wrap_text=wrap)
        cl.border = border
        return cl

    # ── Summary sheet ────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Summary 汇总"
    headers = ["PO", "Style 款号", "Brand 品牌", "Warehouse 仓库",
               "Account 客户", "Channel 渠道",
               "必须 Required", "待定 Pending", "冲突 Conflict", "不适用 N/A"]
    for c, h in enumerate(headers, 1):
        cell(ws, 1, c, h, bold=True, bg=_NAVY, white=True, center=True)
    widths = [16, 14, 16, 11, 13, 12, 12, 12, 11, 11]
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + c)].width = w

    for r, ctx in enumerate(contexts, 2):
        counts = {"confirmed": 0, "pending_input": 0, "conflict": 0,
                  "not_applicable": 0, "missing_mandatory_context": 0}
        for res in ctx["results"]:
            s = res.get("status", "")
            if s in counts:
                counts[s] += 1
        # missing_mandatory_context needs operator attention just like
        # pending_input — fold it into the 待定 column so a PO whose results
        # all need context doesn't show 0/0/0/0 (indistinguishable from
        # "no requirements").
        pending = counts["pending_input"] + counts["missing_mandatory_context"]
        vals = [ctx["po_number"], ctx["style"], ctx["brand"], ctx["warehouse"],
                ctx["account"], ctx["channel"], counts["confirmed"],
                pending, counts["conflict"], counts["not_applicable"]]
        for c, v in enumerate(vals, 1):
            cell(ws, r, c, v, center=(c >= 7),
                 bg=_RED if (c == 9 and v) else (_YELLOW if (c == 8 and v) else None))
    ws.freeze_panes = "A2"

    if warnings:
        wr = len(contexts) + 3
        cell(ws, wr, 1, "⚠ Warnings", bold=True, bg=_YELLOW)
        for i, w in enumerate(warnings, 1):
            cell(ws, wr + i, 1, w, wrap=True)
            ws.merge_cells(start_row=wr + i, start_column=1,
                           end_row=wr + i, end_column=len(headers))

    # ── By-style comparison sheet ────────────────────────────────────────────
    # Combines identical requirements (one row, "全部 All") and breaks out the
    # ones that differ per style, so you see at a glance where styles diverge.
    _write_by_style_sheet(wb, contexts, cell)

    # ── One sheet per PO context ─────────────────────────────────────────────
    used: set[str] = {ws.title, "款号对比 By Style"}
    for ctx in contexts:
        s = wb.create_sheet(_sheet_name(ctx["po_number"], used))
        cell(s, 1, 1, f"PO {ctx['po_number']} · {ctx['style']} · {ctx['brand']} · "
                      f"{ctx['warehouse']} {ctx['account']} ({ctx['channel']})",
             bold=True, bg=_NAVY, white=True)
        s.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)

        hdrs = ["Domain 类别", "Item 项目", "Status 状态", "Requirement 要求",
                "Source 来源", "图示 Image"]
        for c, h in enumerate(hdrs, 1):
            cell(s, 2, c, h, bold=True, bg=_NAVY, white=True, center=True)
        for c, w in zip(range(1, 7), (14, 22, 20, 70, 34, 16)):
            s.column_dimensions[chr(64 + c)].width = w

        # applicable first, N/A last; stable by domain within each group
        results = sorted(ctx["results"],
                         key=lambda x: (x.get("status") == "not_applicable",
                                        x.get("domain", ""), x.get("subtype", "")))
        r = 3
        for res in results:
            status = res.get("status", "")
            rj = res.get("resultJson") or {}
            cell(s, r, 1, res.get("domain", ""))
            cell(s, r, 2, res.get("subtype", ""))
            cell(s, r, 3, _STATUS_CN.get(status, status),
                 bg=_STATUS_BG.get(status), center=True)
            cell(s, r, 4, _req_text(res))
            cell(s, r, 5, str(rj.get("source", "")))
            cell(s, r, 6, "")                       # image cell (border); art below
            _embed_thumbs(s, r, 6, res.get("_images"))
            r += 1
        s.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_by_style_sheet(wb, contexts: list[dict], cell) -> None:
    """Second tab: requirements pivoted by style. Identical requirements across
    every style collapse to ONE row ("全部 All"); requirements that differ show
    one row per distinct value with the styles that carry it, highlighted."""
    from collections import OrderedDict

    styles_order: list[str] = []
    for ctx in contexts:
        st = ctx.get("style") or "—"
        if st not in styles_order:
            styles_order.append(st)
    all_styles = set(styles_order)
    n = len(all_styles)

    # (domain, subtype) -> {(status, value): set(styles)}
    groups: "OrderedDict[tuple, OrderedDict]" = OrderedDict()
    for ctx in contexts:
        st = ctx.get("style") or "—"
        for res in ctx.get("results", []):
            key = (res.get("domain", ""), res.get("subtype", ""))
            vk = (res.get("status", ""), _req_text(res))
            groups.setdefault(key, OrderedDict()).setdefault(vk, set()).add(st)

    s = wb.create_sheet("款号对比 By Style", 1)
    cell(s, 1, 1, f"款号对比 By-Style Requirements · {n} 款 styles: "
                  + "、".join(styles_order), bold=True, bg=_NAVY, white=True)
    s.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)
    for c, h in enumerate(["类别 Domain", "项目 Item", "状态 Status",
                           "要求 Requirement", "适用款号 Styles"], 1):
        cell(s, 2, c, h, bold=True, bg=_NAVY, white=True, center=True)
    for c, w in zip(range(1, 6), (14, 24, 20, 64, 30)):
        s.column_dimensions[chr(64 + c)].width = w

    def _gkey(k):
        # groups that are N/A for every style sink to the bottom
        na_only = all(status == "not_applicable" for status, _ in groups[k])
        return (na_only, k[0], k[1])

    r = 3
    for key in sorted(groups, key=_gkey):
        domain, subtype = key
        items = sorted(groups[key].items(),
                       key=lambda kv: (_STATUS_RANK.get(kv[0][0], 9), kv[0][1]))
        for (status, value), styles in items:
            common = styles == all_styles
            styles_txt = f"全部 All ({n})" if common else "、".join(sorted(styles))
            hl = None if common else _YELLOW      # highlight style-specific rows
            cell(s, r, 1, domain)
            cell(s, r, 2, subtype, bg=hl)
            cell(s, r, 3, _STATUS_CN.get(status, status),
                 bg=_STATUS_BG.get(status), center=True)
            cell(s, r, 4, value, bg=hl)
            cell(s, r, 5, styles_txt, bg=hl, center=common)
            r += 1
    s.freeze_panes = "A3"
