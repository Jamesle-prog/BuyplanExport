"""Tests for the GIII buy-plan exporter (generated workbook)."""
from __future__ import annotations

import io

import openpyxl

from po_extractor.exporters.giii_buyplan_export import (
    BuyPlanHeader, BuyPlanRow, export_giii_buyplan,
)


def _rows():
    return [
        BuyPlanRow(contract_no="26502-DS3012", style="P6KH8FXB", po_number="DW867662UC",
                   cpo="", warehouse_code="UC", buyer="MY MACY'S",
                   color_en="NVY/NAVY", color_cn="藏青",
                   sizes={"S": 34, "M": 79, "L": 108}, ex_fty="46218",
                   packing_method="平装+衣架", is_prepack=False),
        BuyPlanRow(contract_no="26502-DS3012", style="P6KH8FXB", po_number="DW867662UC",
                   warehouse_code="UC", buyer="MY MACY'S",
                   color_en="QJC/CITY CLAY", color_cn="泥粉",
                   sizes={"S": 67, "M": 89, "L": 80}, ex_fty="46218",
                   packing_method="平装+衣架", is_prepack=False),
    ]


def _load(xlsx_bytes):
    return openpyxl.load_workbook(io.BytesIO(xlsx_bytes)).active


def _grid(ws):
    return [[c.value for c in row] for row in ws.iter_rows()]


def test_export_without_cprs_leaves_kb_columns_blank():
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear",
               supplier="新庄源", fabric="HB-XD6786", description="针织女套头衫"),
               _rows(), cprs=None))
    grid = _grid(ws)
    # Banner + title
    assert grid[0][0] == "江苏新万新服饰有限公司"
    assert "buy plan" in grid[1][0]
    # Header rows: row 8 (index 7) has 合同号; row 9 (index 8) has size letters
    assert grid[7][0] == "合同号"
    assert "S" in grid[8] and "M" in grid[8] and "L" in grid[8]
    # First data row (index 9): contract + style + PO
    assert grid[9][0] == "26502-DS3012"
    assert grid[9][1] == "P6KH8FXB"
    assert grid[9][4] == "UC"        # warehouse (already known)
    # CPRS columns (red sticker / carton mark / prepack ratio / pcs / msrp / rfid) blank
    # They are the last 8 columns; with no CPRS they must be blank/""
    last8 = grid[9][-8:]
    # red_sticker, carton_mark, packing, prepack(Y/N from PO), ratio, pcs, msrp, rfid
    assert last8[0] in ("", None)     # red sticker blank (no CPRS)
    assert last8[2] == "平装+衣架"    # packing method (PO)
    assert last8[3] == "N"            # prepack flag from PO (is_prepack=False)
    assert last8[4] in ("", None)     # prepack ratio blank
    assert last8[6] in ("", None)     # MSRP blank
    assert last8[7] in ("", None)     # RFID blank


def test_totals_and_color_subtotals():
    ws = _load(export_giii_buyplan(BuyPlanHeader(), _rows(), cprs=None))
    grid = _grid(ws)
    flat = [c for row in grid for c in row]
    assert "TTL" in flat
    # grand total 34+79+108 + 67+89+80 = 457
    assert 457 in flat
    # per-color subtotals present
    assert "藏青" in flat and "泥粉" in flat
    assert 221 in flat   # navy S+M+L = 34+79+108
    assert 236 in flat   # clay S+M+L = 67+89+80


class _MockCprs:
    def resolve_client(self, brand): return "a1" if brand else None
    def resolve_warehouse(self, ship_to, cid): return "UC"
    def resolve_account(self, buyer, cid): return "MACYS"
    def warehouse_flags(self, cid, wh):
        return {"rfid": True, "msrp": True} if wh == "UC" else {"rfid": None, "msrp": None}
    def carton_results(self, order):
        return {
            "red_carton_sticker": {"status": "confirmed",
                                   "resultJson": {"code": "MY"}},
            "carton_marking": {"status": "confirmed",
                               "resultJson": {"value": "CTN# + net wt"}},
        }
    def evaluate(self, order):
        return [{"domain": "packaging", "subtype": "pre_pack_ratio",
                 "status": "confirmed",
                 "resultJson": {"ratio": "1-2-2-1", "pcs_per_carton": 36}}]
    def manual_image(self, image_id): return None


def test_export_with_cprs_fills_kb_columns():
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _rows(), cprs=_MockCprs()))
    grid = _grid(ws)
    last10 = grid[9][-10:]  # 总数量 .. RFID  (right block)
    # right block order: total, ex_fty, red, mark, packing, prepack, ratio, pcs, msrp, rfid
    assert last10[2] == "MY"            # red sticker code
    assert last10[3] == "CTN# + net wt"  # carton mark
    assert last10[6] == "1-2-2-1"       # prepack ratio (CPRS)
    assert last10[7] == "36"            # pcs/box (CPRS)
    assert last10[8] == "Y"             # MSRP (warehouse UC = yes)
    assert last10[9] == "Y"             # RFID


def test_red_sticker_not_applicable_becomes_wuxu():
    class C(_MockCprs):
        def carton_results(self, order):
            return {"red_carton_sticker": {"status": "not_applicable"}}
        def warehouse_flags(self, cid, wh): return {"rfid": False, "msrp": False}
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _rows(), cprs=C()))
    grid = _grid(ws)
    assert grid[9][-10:][2] == "无需"   # red sticker not_applicable → 无需


def test_assemble_rows_from_frames():
    import pandas as pd
    from po_extractor.exporters.giii_buyplan_export import assemble_buyplan_rows

    df_size = pd.DataFrame([
        {"po_number": "PO1", "style": "ST1", "color": "NAVY", "size": "S", "units": 10},
        {"po_number": "PO1", "style": "ST1", "color": "NAVY", "size": "M", "units": 20},
        {"po_number": "PO1", "style": "ST1", "color": "CLAY", "size": "S", "units": 5},
    ])
    df_meta = pd.DataFrame([
        {"po_number": "PO1", "style": "ST1", "cpo": "C9", "buyer": "MY MACY'S",
         "ship_to": "NJ DC", "xport_date": "2026-07-01", "packaging": "PPK flat pack"},
    ])
    rows = assemble_buyplan_rows(
        df_size, df_meta,
        contract_by_po={"PO1": "HHN-001"},
        color_lookup={"NAVY": "藏青", "CLAY": "泥粉"},
    )
    assert len(rows) == 2                       # NAVY + CLAY
    navy = next(r for r in rows if r.color_en == "NAVY")
    assert navy.contract_no == "HHN-001"
    assert navy.color_cn == "藏青"
    assert navy.sizes == {"S": 10, "M": 20}
    assert navy.cpo == "C9" and navy.buyer == "MY MACY'S"
    assert navy.ex_fty == "2026-07-01"
    assert navy.is_prepack is True             # "PPK" in packaging


def test_assemble_rows_empty():
    import pandas as pd
    from po_extractor.exporters.giii_buyplan_export import assemble_buyplan_rows
    assert assemble_buyplan_rows(pd.DataFrame(), pd.DataFrame()) == []


def test_red_sticker_pending_input_shows_marker():
    """Live CPRS returns pending_input (waiting on dim_code) for the red sticker."""
    class C(_MockCprs):
        def carton_results(self, order):
            return {"red_carton_sticker": {"status": "pending_input",
                    "resultJson": {"waiting_for": "dim_code"}}}
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _rows(), cprs=C()))
    grid = _grid(ws)
    assert grid[9][-10:][2] == "待定:dim_code"


def test_dynamic_sizes_only_present_ones():
    rows = [BuyPlanRow(style="X", color_en="RED", sizes={"M": 5, "XL": 3})]
    ws = _load(export_giii_buyplan(BuyPlanHeader(), rows, cprs=None))
    grid = _grid(ws)
    sizes_row = grid[8]
    assert "M" in sizes_row and "XL" in sizes_row
    assert "S" not in sizes_row and "L" not in sizes_row
