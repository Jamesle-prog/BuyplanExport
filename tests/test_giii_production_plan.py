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
        "packaging": ["PPK", np.nan],
        "hanger": [np.nan, np.nan],
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
                 red_img=None, mark_img=None):
        self.warehouse = warehouse
        self.red_sticker = red_sticker
        self.carton_mark = carton_mark
        self.red_img = red_img
        self.mark_img = mark_img


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
    ws = _sheet(generate_giii_production_plan(
        ["PO1", "PO2"], store, {},
        color_lookup_en={"JET BLACK": "煤黑色"}))
    assert "煤黑色" in _all_values(ws)


def test_nan_metadata_never_renders_as_nan():
    store = _Store(_pos_df(), _sizes_df())
    ws = _sheet(generate_giii_production_plan(["PO1", "PO2"], store, {}))
    for v in _all_values(ws):
        assert "nan" not in str(v).lower().split(), f"NaN leaked into cell: {v!r}"


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
