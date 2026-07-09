"""Tests for the content-based GIII specialized-PO classifier."""
from __future__ import annotations

from po_extractor.detectors.specialized_po import (
    SPECIALIZED_PO_LABELS, classify_giii_po_text,
)


def test_infor_nexus_by_portal_keyword():
    assert classify_giii_po_text("Powered by Infor Nexus\nOrder 123") == "infor_nexus"


def test_tk_eu_by_plain_marker():
    text = "PO NUMBER DU123U\nTJX UK PROCESSING CENTRE\nFFOOBB:: NOT CONFIRMED"
    assert classify_giii_po_text(text) == "tk_eu"


def test_tk_eu_by_letter_spaced_brand_header():
    # Brand header renders letter-spaced: "K O S T R O M A , LTD"
    text = "K O S T R O M A , LTD\nPO NUMBER DU9U\nEETTDD 1/1/26"
    assert classify_giii_po_text(text) == "tk_eu"


def test_tk_eu_by_fax_doubled_shipto():
    # Ship-to line arrives fax-doubled: "CC//OO AAPPLL LLOOGGIISSTTIICCSS"
    text = "PO NUMBER DU5U\nCC//OO  AAPPLL  LLOOGGIISSTTIICCSS\nFFOOBB $$1.00"
    assert classify_giii_po_text(text) == "tk_eu"


def test_kl_by_msrp_block():
    text = "PO NUMBER LSK1R\nFFOOBB::$$4.17\n001 G5DTN93C JVS MSRP $69.00"
    assert classify_giii_po_text(text) == "kl"


def test_kl_by_doubled_cust_po():
    text = "PO NUMBER LSK2R\nEETTDD 1/1/26\nCCUUSSTT PPOO:: TBD"
    assert classify_giii_po_text(text) == "kl"


def test_vendor_fax_when_doubled_but_not_kl_or_tkeu():
    text = "PO NUMBER CSKHHA001R\nFFOOBB $$3.50\nHHAANNGGEERR (1-2-2-1)"
    assert classify_giii_po_text(text) == "vendor_fax"


def test_unknown_for_plain_text_and_empty():
    assert classify_giii_po_text("just a random document") == "unknown"
    assert classify_giii_po_text("") == "unknown"


def test_every_class_has_a_label():
    for cls in ("infor_nexus", "tk_eu", "kl", "vendor_fax", "unknown"):
        assert cls in SPECIALIZED_PO_LABELS
