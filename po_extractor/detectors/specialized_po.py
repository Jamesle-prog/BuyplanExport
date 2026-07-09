"""Content-based classifier for the GIII specialized PO types.

Given the text of a PO document (from a bare PDF or a PDF extracted out of
an Outlook .msg), decide which extractor it belongs to. The file extension
deliberately plays no role — the same fax documents arrive both inside
.msg emails and as bare PDFs, so only the content is trustworthy.

Classes returned by :func:`classify_giii_po_text`:

* ``"infor_nexus"`` — InforNexus portal PDFs (same keywords the main
  pipeline's ``detect_format`` locks onto).
* ``"tk_eu"``       — Kostroma / TJX UK fax POs ("KOSTROMA",
  "TJX UK", "APL LOGISTICS" markers; brand header is letter-spaced
  "K O S T R O M A", ship-to lines are fax-doubled — both normalized).
* ``"kl"``          — KL fax POs: the only fax layout with an MSRP price
  block and/or a "CUST PO:" field.
* ``"vendor_fax"``  — AS400 vendor fax copies (fax-doubled markers like
  FFOOBB / EETTDD / HHAANNGGEERR) that are neither TK EU nor KL.
* ``"unknown"``     — none of the above.
"""
from __future__ import annotations

import re

from .format_detector import detect_format
from ..config import FORMAT_INFOR_NEXUS

# Human labels for UI display, keyed by class id.
SPECIALIZED_PO_LABELS = {
    "infor_nexus": "InforNexus PO",
    "tk_eu":       "TK EU PO (Kostroma / TJX UK)",
    "kl":          "KL PO",
    "vendor_fax":  "MSG / Vendor Fax PO",
    "unknown":     "Unknown",
}

_TK_EU_MARKERS = ("KOSTROMA", "TJX UK", "APL LOGISTICS")

# Fax-doubled tokens that identify the AS400 fax-copy rendering.
_FAX_DOUBLED_MARKERS = ("FFOOBB", "EETTDD", "HHAANNGGEERR", "PPRRIICCEE")


def _variants(text: str) -> tuple[str, str, str]:
    """(upper, upper-without-spaces, upper-undoubled) views of the text."""
    up = text.upper()
    nospace = re.sub(r"[ \t]+", "", up)
    undoubled = re.sub(r"(.)\1", r"\1", up)
    return up, nospace, undoubled


def classify_giii_po_text(text: str) -> str:
    """Classify PO document text into one of the specialized-extractor types."""
    if not text or not text.strip():
        return "unknown"

    up, nospace, undoubled = _variants(text)

    # InforNexus first — portal PDFs are never fax-doubled and carry their
    # own unambiguous keywords.
    if detect_format(text) == FORMAT_INFOR_NEXUS:
        return "infor_nexus"

    # TK EU — check all views: letter-spaced brand header, doubled ship-to.
    for marker in _TK_EU_MARKERS:
        squeezed = marker.replace(" ", "")
        if marker in up or squeezed in nospace or marker in undoubled:
            return "tk_eu"

    is_fax = any(m in up for m in _FAX_DOUBLED_MARKERS)

    # KL — the fax layout with an MSRP block / "CUST PO:" field.
    if is_fax and (
        re.search(r"MSRP\s*\$", up)
        or re.search(r"MSRP\s*\$", undoubled)
        or "MMSSRRPP" in up
        or "CCUUSSTT PPOO" in up
        or "CUST PO:" in undoubled
    ):
        return "kl"

    if is_fax:
        return "vendor_fax"

    return "unknown"
