"""Infor Nexus size-grid parsing — both column-major and row-major layouts.

pypdfium2 linearises the Size:/UOM:/UPC:/Qty: table either way depending on the
PDF's internal reading order; the parser must capture size/UPC/qty from both.
"""
from __future__ import annotations

from po_extractor.parsers.infor_nexus import _parse_size_grid


def test_column_major_grid():
    block = ("Size:\nUOM:\nUPC:\nQty:\n"
             "XS\nEA\n700948471565\n11\n"
             "S\nEA\n700948471558\n28\n"
             "-\n-\n-\n-\nTotal Qty Unit Cost")
    assert _parse_size_grid(block) == [
        ("XS", "700948471565", 11), ("S", "700948471558", 28)]


def test_row_major_grid_captures_upcs():
    # the screenshot's shape: every size, then every UPC, then every qty
    block = ("Size:\nXXS\nXS\nS\nM\nL\nXL\n"
             "UOM:\nEA\nEA\nEA\nEA\nEA\nEA\n"
             "UPC:\n700948939589\n700948487158\n700948487141\n"
             "700948487134\n700948487127\n700948487110\n"
             "Qty:\n4\n11\n17\n15\n10\n6\nTotal Qty Unit Cost")
    got = _parse_size_grid(block)
    assert got == [
        ("XXS", "700948939589", 4), ("XS", "700948487158", 11),
        ("S", "700948487141", 17), ("M", "700948487134", 15),
        ("L", "700948487127", 10), ("XL", "700948487110", 6)]
    # every size carries its UPC (the reported bug)
    assert all(len(upc) == 12 for _, upc, _ in got)


def test_row_major_skips_padding_dashes():
    block = ("Size:\nS\nM\n-\n-\n"
             "UOM:\nEA\nEA\n-\n-\n"
             "UPC:\n700948471558\n700948471541\n-\n-\n"
             "Qty:\n28\n31\n-\n-\nTotal Qty")
    assert _parse_size_grid(block) == [
        ("S", "700948471558", 28), ("M", "700948471541", 31)]


def test_thousands_separator_qty_row_major():
    block = ("Size:\nM\nUOM:\nEA\nUPC:\n700948471541\nQty:\n2,500\nTotal Qty")
    assert _parse_size_grid(block) == [("M", "700948471541", 2500)]
