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

    # ── One sheet per PO context ─────────────────────────────────────────────
    used: set[str] = {ws.title}
    for ctx in contexts:
        s = wb.create_sheet(_sheet_name(ctx["po_number"], used))
        cell(s, 1, 1, f"PO {ctx['po_number']} · {ctx['style']} · {ctx['brand']} · "
                      f"{ctx['warehouse']} {ctx['account']} ({ctx['channel']})",
             bold=True, bg=_NAVY, white=True)
        s.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)

        hdrs = ["Domain 类别", "Item 项目", "Status 状态", "Requirement 要求",
                "Source 来源"]
        for c, h in enumerate(hdrs, 1):
            cell(s, 2, c, h, bold=True, bg=_NAVY, white=True, center=True)
        for c, w in zip(range(1, 6), (14, 22, 20, 70, 34)):
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
            r += 1
        s.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
