"""Standalone warehouse web scanner for PO Automation GIII.

A lightweight browser scan page (keyboard-wedge, mobile-first) + a small JSON
API over the existing ``po_history.db``, served by Starlette + uvicorn as its
OWN process — separate from the Streamlit app. Meant for handheld PDAs on the
warehouse LAN.

Run with:  python -m web_scan   (honours PO_SCAN_PORT, PO_SCAN_PASSWORD,
                                  PO_SCAN_COMPANIES)
"""
