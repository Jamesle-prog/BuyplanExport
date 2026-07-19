"""Factory progress request form — the Excel round-trip (工厂进度回报表).

``build_progress_request_xlsx``: generate a pre-filled form for one factory
listing their PO/styles with ordered qty and already-reported totals; the
factory fills in the 本次新增 (new since last report) columns + date and
sends the file back.

``parse_progress_report_xlsx``: read a returned form back into report-row
dicts ready for ``FactoryProgressStore.add_report`` — with validation
issues collected per row rather than raised, so the UI can show a preview
of exactly what will be imported and what was skipped.

The form is deliberately dumb-Excel: no macros, no validation lists that
break in WPS, fixed header row detected by cell text on re-import (so an
extra title row or renamed file doesn't matter).
"""
from __future__ import annotations

import io
from datetime import date

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from ..store._factory_progress_schema import REPORT_STAGES

# Column layout of the request form (1-based). The 本次新增 columns are what
# the factory fills in; everything else is context we pre-fill.
_FORM_HEADERS = [
    "PO号 PO No.",              # 1
    "款号 Style",                # 2
    "订单数 Order Qty",          # 3
    "已报裁剪 Cut so far",       # 4
    "已报车缝 Sewn so far",      # 5
    "已报包装 Packed so far",    # 6
    "本次新增裁剪 New Cut",      # 7  <- factory fills
    "本次新增车缝 New Sewn",     # 8  <- factory fills
    "本次新增包装 New Packed",   # 9  <- factory fills
    "报告日期 Report Date",      # 10 <- factory fills (YYYY-MM-DD)
    "备注 Notes",                # 11 <- factory fills (optional)
]

# Column index (1-based) -> stage key for the fill-in columns.
_STAGE_COLS = {7: "cutting", 8: "sewing", 9: "packing"}
_COL_PO, _COL_STYLE, _COL_QTY = 1, 2, 3
_COL_DATE, _COL_NOTES = 10, 11

_SHEET_TITLE = "进度回报 Progress"


def build_progress_request_xlsx(factory: str, rows: list[dict]) -> bytes:
    """Build the request form for one *factory*.

    Each row dict: ``{"po_number", "style", "order_qty", "cut", "sewn",
    "packed"}`` (the last four ints; already-reported totals may be 0).
    Returns the xlsx file as bytes (callers hand it to a download button).
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = _SHEET_TITLE

    ws.cell(1, 1, value=(
        f"工厂进度回报表 Factory Progress Report — {factory} — "
        f"生成日期 {date.today().isoformat()}"
    )).font = Font(bold=True, size=12)
    ws.cell(2, 1, value=(
        "请只填写右侧「本次新增」三列 + 报告日期（YYYY-MM-DD），"
        "数量为自上次回报以来新完成的件数（不是累计数）。"
        "Fill ONLY the three 'New' columns + Report Date; quantities are "
        "units completed SINCE the last report (not cumulative)."
    )).font = Font(size=9, italic=True, color="FF808080")

    header_row = 4
    for ci, h in enumerate(_FORM_HEADERS, 1):
        cell = ws.cell(header_row, ci, value=h)
        cell.fill = PatternFill(start_color="FF1F3864", end_color="FF1F3864",
                                fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFFFF", size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
    ws.row_dimensions[header_row].height = 30

    fill_hint = PatternFill(start_color="FFFFF2CC", end_color="FFFFF2CC",
                            fill_type="solid")   # light yellow = fill me in
    for ri, row in enumerate(rows, header_row + 1):
        ws.cell(ri, _COL_PO,    value=row.get("po_number", ""))
        ws.cell(ri, _COL_STYLE, value=row.get("style", ""))
        ws.cell(ri, _COL_QTY,   value=row.get("order_qty") or "")
        ws.cell(ri, 4, value=row.get("cut", 0))
        ws.cell(ri, 5, value=row.get("sewn", 0))
        ws.cell(ri, 6, value=row.get("packed", 0))
        for ci in (*_STAGE_COLS, _COL_DATE, _COL_NOTES):
            ws.cell(ri, ci).fill = fill_hint

    widths = {1: 16, 2: 14, 3: 11, 4: 11, 5: 11, 6: 11, 7: 13, 8: 13, 9: 13,
              10: 14, 11: 24}
    from openpyxl.utils import get_column_letter
    for ci, w in widths.items():
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = ws.cell(header_row + 1, 1).coordinate

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_progress_report_xlsx(content: bytes, factory: str = "") -> dict:
    """Parse a returned form. Returns::

        {"reports": [ {po_number, style, stage, units, report_date,
                       factory, notes}, ... ],
         "issues":  [ "row 6: ...", ... ],   # skipped/suspect rows
         "rows_seen": int}

    One report dict per non-empty New-column cell (a row reporting cut AND
    sewn yields two reports). Rows with no New quantities at all are simply
    unchanged rows of the form, not issues. Never raises on cell content —
    file-level problems (unreadable, header row not found) do raise
    ValueError so the UI can show a clear error.
    """
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    try:
        ws = wb[_SHEET_TITLE] if _SHEET_TITLE in wb.sheetnames else wb.active

        # Find the header row by its first cell text (tolerates added rows).
        header_row = None
        for r in range(1, min(ws.max_row, 20) + 1):
            if str(ws.cell(r, 1).value or "").strip().startswith("PO号"):
                header_row = r
                break
        if header_row is None:
            raise ValueError(
                "Header row not found — is this the progress request form? "
                "(expected a 'PO号 PO No.' header cell)"
            )

        reports: list[dict] = []
        issues: list[str] = []
        rows_seen = 0
        for r in range(header_row + 1, ws.max_row + 1):
            po = str(ws.cell(r, _COL_PO).value or "").strip()
            style = str(ws.cell(r, _COL_STYLE).value or "").strip()
            if not po:
                continue
            rows_seen += 1

            raw_date = ws.cell(r, _COL_DATE).value
            if hasattr(raw_date, "isoformat"):          # datetime/date cell
                report_date = raw_date.date().isoformat() if hasattr(raw_date, "date") \
                    else raw_date.isoformat()
            else:
                report_date = str(raw_date or "").strip()
            notes = str(ws.cell(r, _COL_NOTES).value or "").strip()

            row_units: dict[str, int] = {}
            for ci, stage in _STAGE_COLS.items():
                raw = ws.cell(r, ci).value
                if raw in (None, ""):
                    continue
                try:
                    units = int(float(raw))
                except (TypeError, ValueError):
                    issues.append(f"row {r}: {stage} value {raw!r} is not a number — skipped")
                    continue
                if units == 0:
                    continue
                if units < 0:
                    issues.append(f"row {r}: negative {stage} value {units} — skipped "
                                  "(delete the wrong earlier report instead)")
                    continue
                row_units[stage] = units

            if not row_units:
                continue
            if not report_date:
                issues.append(f"row {r} ({po} / {style}): quantities given but "
                              f"报告日期 Report Date is empty — skipped")
                continue

            for stage, units in row_units.items():
                reports.append({
                    "po_number": po, "style": style, "stage": stage,
                    "units": units, "report_date": report_date,
                    "factory": factory, "notes": notes,
                })
        return {"reports": reports, "issues": issues, "rows_seen": rows_seen}
    finally:
        wb.close()
