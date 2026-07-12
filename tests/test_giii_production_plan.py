"""Tests for the enriched GIII production plan (生产计划单) — the buy plan.

Covers the v2.40.0 enrichment: 面料 rows from the 款式面料表格, 合同号 from
the 大货进度表, 进度表 CN colours, CPRS 红色箱贴纸/主箱唛 (text + artwork),
NaN cleanup, and the all-zero-row filter in export_buyplan.
"""
from __future__ import annotations

import io

import numpy as np
import openpyxl
import pandas as pd
import pytest

from po_extractor.exporters.giii_production_plan import generate_giii_production_plan
from po_extractor.lookups.progress_lookup import _norm_key
from po_extractor.models.fabric_part import FabricPart


# ── stub store ────────────────────────────────────────────────────────────────

class _Store:
    def __init__(self, df_pos, df_sizes, fabric_parts=None):
        self._pos = df_pos
        self._sizes = df_sizes
        self._parts = fabric_parts or {}

    def list_pos(self, companies=None):
        return self._pos

    def load_size_rows(self, selected):
        return self._sizes[self._sizes["PO Number"].isin(selected)]

    def load_fabric_parts_for_styles(self, styles, source=None):
        return {s: self._parts.get(s, []) for s in styles}


def _pos_df(**overrides):
    base = {
        "po_number": ["PO1", "PO2"],
        "style": ["ST1", "ST1"],
        "seller": ["FACTORY CO", "FACTORY CO"],
        "fabric": ["", ""],
        "description_code": ["DESC", "DESC"],
        "style_description": ["", ""],
        "cpo": ["CPO1", np.nan],
        "destination_code": ["UC", np.nan],
        "customer": ["ROSS STORES", "ROSS STORES"],
        "buyer": ["", ""],
        "factory_ship_date": ["7/30/2026", np.nan],
        "xport_date": ["", "8/15/2026"],
        "ship_to": ["ROSS DC, CARLISLE PA", np.nan],
        "packaging": ["PPK", np.nan],
        "hanger": ["HANGER (1-2-2-1)", np.nan],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _sizes_df():
    return pd.DataFrame({
        "PO Number": ["PO1", "PO1", "PO2"],
        "Style": ["ST1", "ST1", "ST1"],
        "Color": ["JET BLACK", "JET BLACK", "PINE"],
        "Size": ["S", "M", "S"],
        "Units": [100, 200, 50],
    })


def _sheet(data: bytes, name="ST1"):
    return openpyxl.load_workbook(io.BytesIO(data))[name]


def _all_values(ws):
    return [c.value for row in ws.iter_rows() for c in row if c.value is not None]


# ── fabric block ──────────────────────────────────────────────────────────────

def test_fabric_rows_from_style_fabric_table():
    parts = [FabricPart(seq=1, body_part="大身", hhn_no="HHN-DB-1",
                        composition="86%Polyester 14%Spandex",
                        weight_gsm=200, width_cm=170),
             FabricPart(seq=2, body_part="口袋布", hhn_no="HHN-CJS-2",
                        composition="100%Cotton")]
    store = _Store(_pos_df(), _sizes_df(), {"ST1": parts})
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {}))

    assert ws.cell(5, 1).value == "面料/FIBER:"
    assert "HHN-DB-1" in ws.cell(5, 2).value
    assert "86%Polyester 14%Spandex" in ws.cell(5, 2).value
    assert "200gsm" in ws.cell(5, 2).value and "有效170cm" in ws.cell(5, 2).value
    assert ws.cell(6, 1).value == "面料_其他1:"
    assert "HHN-CJS-2" in ws.cell(6, 2).value
    # one extra fabric row shifts everything below down by one
    assert ws.cell(7, 1).value == "品名/Description:"
    assert ws.cell(9, 1).value == "合同号"


def test_no_fabric_parts_keeps_classic_layout():
    store = _Store(_pos_df(), _sizes_df())
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {}))
    assert ws.cell(5, 1).value == "面料/FIBER:"
    assert ws.cell(6, 1).value == "品名/Description:"
    assert ws.cell(8, 1).value == "合同号"


# ── CPRS requirements ─────────────────────────────────────────────────────────

class _Req:
    def __init__(self, warehouse="", red_sticker="", carton_mark="",
                 red_img=None, mark_img=None, prepack_ratio="", pcs_box="",
                 msrp="", rfid=""):
        self.warehouse = warehouse
        self.red_sticker = red_sticker
        self.carton_mark = carton_mark
        self.red_img = red_img
        self.mark_img = mark_img
        self.prepack_ratio = prepack_ratio
        self.pcs_box = pcs_box
        self.msrp = msrp
        self.rfid = rfid


def _png_bytes() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (40, 20), "red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_requirements_fill_red_sticker_and_carton_mark():
    reqs = {"PO1": _Req(red_sticker="MY", carton_mark="见箱唛要求"),
            "PO2": _Req(warehouse="DN", red_sticker="无需")}
    store = _Store(_pos_df(), _sizes_df())
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {},
                                              requirements=reqs))
    vals = _all_values(ws)
    assert "MY" in vals and "无需" in vals and "见箱唛要求" in vals
    # PO2 had no destination_code — CPRS-resolved warehouse fills 仓库代码
    assert "DN" in vals


def test_requirement_artwork_embeds_without_error():
    reqs = {"PO1": _Req(red_sticker="MY", red_img=_png_bytes(),
                        mark_img=_png_bytes())}
    store = _Store(_pos_df(), _sizes_df())
    data = generate_giii_production_plan(["PO1", "PO2"], store, {},
                                         requirements=reqs)
    ws = _sheet(data)
    assert len(ws._images) == 2


def test_bad_image_bytes_do_not_break_export():
    reqs = {"PO1": _Req(red_sticker="MY", red_img=b"not-an-image")}
    store = _Store(_pos_df(), _sizes_df())
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {},
                                              requirements=reqs))
    assert "MY" in _all_values(ws)


def test_no_requirements_defaults_red_sticker_to_wu():
    store = _Store(_pos_df(), _sizes_df())
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {}))
    assert "无" in _all_values(ws)


# ── style-sheet 目的地 / 包装方式 / 离厂时间 ──────────────────────────────────

def test_style_sheet_has_destination_and_packing_columns():
    store = _Store(_pos_df(), _sizes_df())
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {}))
    hdr_row = 8    # no fabric parts → classic layout
    headers = [ws.cell(hdr_row, c).value for c in range(1, 25)]
    assert "目的地" in headers and "包装方式" in headers and "备注" in headers
    vals = [str(v) for v in _all_values(ws)]
    assert any("CARLISLE" in v for v in vals)     # ship-to in 目的地
    assert any(v == "PPK" for v in vals)          # packaging in 包装方式


def test_ex_factory_date_is_etd_minus_10_days():
    store = _Store(_pos_df(), _sizes_df())
    data = generate_giii_production_plan(["PO1", "PO2"], store, {})
    ws = _sheet(data)
    vals = [str(v) for v in _all_values(ws)]
    # PO1 ETD 7/30/2026 → 07/20/2026; PO2 ETD 8/15/2026 → 08/05/2026
    assert any("07/20/2026" in v for v in vals)
    assert any("08/05/2026" in v for v in vals)
    assert not any("7/30/2026" in v for v in vals)
    # summary inherits the adjusted date
    wb = openpyxl.load_workbook(io.BytesIO(data))
    svals = [str(v) for v in _all_values(wb["Summary 汇总"])]
    assert any("07/20/2026" in v for v in svals)


def test_unparseable_etd_passes_through():
    store = _Store(_pos_df(factory_ship_date=["TBD", np.nan]), _sizes_df())
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {}))
    assert any(str(v) == "TBD" for v in _all_values(ws))


# ── 合同号 / CN colours / NaN cleanup ─────────────────────────────────────────

def test_contract_from_progress_maps():
    store = _Store(_pos_df(), _sizes_df())
    ws = _sheet(generate_giii_production_plan(
        ["PO1", "PO2"], store, {},
        contract_by_po={_norm_key("PO1"): "26302-ZA1"},
        contract_by_style={_norm_key("ST1"): "26302-ZA9"}))
    vals = _all_values(ws)
    assert "26302-ZA1" in vals          # by-PO hit
    assert "26302-ZA9" in vals          # PO2 falls back to by-style


def test_cn_color_from_progress_lookup():
    store = _Store(_pos_df(), _sizes_df())
    data = generate_giii_production_plan(
        ["PO1", "PO2"], store, {},
        color_lookup_en={"JET BLACK": "煤黑色"})
    assert "煤黑色" in _all_values(_sheet(data))
    # CN colour reaches BOTH summary sheets too
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert "煤黑色" in [str(v) for v in _all_values(wb["Summary 汇总"])]
    sp = wb["简明汇总"]
    assert any(sp.cell(r, 4).value == "煤黑色" for r in range(3, sp.max_row + 1))


def test_style_sheet_packing_broken_into_columns():
    """包装方式 splits into 包装方式/衣架/是否预包/每箱件数/MSRP/RFID columns."""
    reqs = {"PO1": _Req(prepack_ratio="1-2-2-1", pcs_box="36", msrp="Y", rfid="N")}
    store = _Store(_pos_df(), _sizes_df())
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {},
                                              requirements=reqs))
    headers = [ws.cell(8, c).value for c in range(1, 25)]
    for h in ("包装方式", "衣架", "是否预包", "每箱件数", "MSRP", "RFID", "备注"):
        assert h in headers, f"missing style-sheet column {h}"
    vals = [str(v) for v in _all_values(ws)]
    assert any(v == "PPK" for v in vals)                  # packing only
    assert any("HANGER (1-2-2-1)" in v for v in vals)     # hanger own column
    assert any(v == "Y 1-2-2-1" for v in vals)            # prepack + ratio
    assert "36" in vals and "Y" in vals and "N" in vals   # pcs / MSRP / RFID


def test_nan_metadata_never_renders_as_nan():
    store = _Store(_pos_df(), _sizes_df())
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {}))
    for v in _all_values(ws):
        assert "nan" not in str(v).lower().split(), f"NaN leaked into cell: {v!r}"


# ── Summary 汇总 sheet ────────────────────────────────────────────────────────

def test_summary_sheet_first_with_one_row_per_style_and_ttl():
    df_pos = _pos_df(style=["ST1", "ST2"])
    sizes = pd.DataFrame({
        "PO Number": ["PO1", "PO1", "PO2"],
        "Style": ["ST1", "ST1", "ST2"],
        "Color": ["JET BLACK", "JET BLACK", "PINE"],
        "Size": ["S", "M", "S"],
        "Units": [100, 200, 50],
    })
    store = _Store(df_pos, sizes)
    wb = openpyxl.load_workbook(io.BytesIO(
        generate_giii_production_plan(["PO1", "PO2"], store, {})))

    assert wb.sheetnames[0] == "Summary 汇总"
    assert "ST1" in wb.sheetnames and "ST2" in wb.sheetnames

    ws = wb["Summary 汇总"]
    assert ws.cell(2, 1).value == "No." and ws.cell(2, 2).value == "款号"
    # row 3 = ST1 (hyperlink formula to its sheet), row 4 = ST2, row 5 = TTL
    assert ws.cell(3, 1).value == 1
    assert "ST1" in str(ws.cell(3, 2).value) and "HYPERLINK" in str(ws.cell(3, 2).value)
    assert ws.cell(3, 10).value == 300         # ST1 total (总数量)
    assert "PO1" in str(ws.cell(3, 6).value)
    assert "JET BLACK" in str(ws.cell(3, 7).value)
    assert ws.cell(4, 1).value == 2
    assert ws.cell(4, 10).value == 50          # ST2 total
    assert ws.cell(5, 1).value == "TTL"
    assert ws.cell(5, 10).value == 350         # grand total


def test_summary_has_size_breakdown_packing_destination():
    store = _Store(_pos_df(), _sizes_df())
    wb = openpyxl.load_workbook(io.BytesIO(
        generate_giii_production_plan(["PO1", "PO2"], store, {})))
    ws = wb["Summary 汇总"]
    headers = [ws.cell(2, c).value for c in range(1, 24)]
    for h in ("尺码明细", "包装方式", "目的地", "衣架", "是否预包",
              "每箱件数", "MSRP", "RFID", "颜色(中文)"):
        assert h in headers, f"missing summary column {h}"
    vals = [str(v) for v in _all_values(ws)]
    assert any("S 150" in v and "M 200" in v for v in vals)   # size breakdown w/ qty
    assert any("PPK" in v for v in vals)                      # packing
    assert any("HANGER (1-2-2-1)" in v for v in vals)         # hanger
    assert any(v == "Y" for v in vals)                        # prepack flag
    assert any("CARLISLE" in v for v in vals)                 # destination


def test_simple_summary_sheet_style_color_fabric_sizes():
    parts = [FabricPart(seq=1, body_part="大身", hhn_no="HHN-DB-1",
                        composition="86%Polyester 14%Spandex")]
    store = _Store(_pos_df(), _sizes_df(), {"ST1": parts})
    wb = openpyxl.load_workbook(io.BytesIO(
        generate_giii_production_plan(["PO1", "PO2"], store, {})))

    assert wb.sheetnames[1] == "简明汇总"
    ws = wb["简明汇总"]
    headers = [ws.cell(2, c).value for c in range(1, 9)]
    assert headers == ["No.", "款号", "颜色", "颜色(中文)", "面料", "S", "M", "总数量"]
    # row 3: JET BLACK  S=100 M=200 total=300; row 4: PINE S=50 total=50
    assert ws.cell(3, 1).value == 1
    assert ws.cell(3, 2).value == "ST1"
    assert "HHN-DB-1" in ws.cell(3, 5).value
    assert ws.cell(3, 3).value == "JET BLACK"
    assert ws.cell(3, 6).value == 100 and ws.cell(3, 7).value == 200
    assert ws.cell(3, 8).value == 300
    assert ws.cell(4, 3).value == "PINE" and ws.cell(4, 8).value == 50
    # TTL row: per-size sums + grand total
    assert ws.cell(5, 1).value == "TTL"
    assert ws.cell(5, 6).value == 150 and ws.cell(5, 7).value == 200
    assert ws.cell(5, 8).value == 350


def test_summary_carries_requirement_texts():
    reqs = {"PO1": _Req(red_sticker="MY", carton_mark="见箱唛要求"),
            "PO2": _Req(red_sticker="无需")}
    store = _Store(_pos_df(), _sizes_df())
    wb = openpyxl.load_workbook(io.BytesIO(
        generate_giii_production_plan(["PO1", "PO2"], store, {},
                                      requirements=reqs)))
    ws = wb["Summary 汇总"]
    vals = _all_values(ws)
    assert any("MY" in str(v) for v in vals)
    assert any("无需" in str(v) for v in vals)
    assert any("见箱唛要求" in str(v) for v in vals)


# ── export_buyplan zero-row filter ────────────────────────────────────────────

def test_export_buyplan_drops_all_zero_color_rows(tmp_path):
    from po_extractor.exporters.buyplan_export import export_buyplan

    data = pd.DataFrame({
        "PO Number": ["PO1"] * 4,
        "Style": ["ST1"] * 4,
        "Color": ["JVS/JET BLACK", "JVS/JET BLACK", "GHOST/UNORDERED", "GHOST/UNORDERED"],
        "Size": ["S", "M", "S", "M"],
        "Units": [100, 200, 0, 0],
    })
    path = export_buyplan(data, pd.DataFrame(), str(tmp_path))
    wb = openpyxl.load_workbook(path)
    vals = [str(c.value) for ws in wb.worksheets
            for row in ws.iter_rows() for c in row if c.value is not None]
    assert any("JVS" in v for v in vals)
    assert not any("GHOST" in v for v in vals), "all-zero colour row leaked"
