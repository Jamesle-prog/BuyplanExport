"""Legacy G-III PO parser (ported from PO_Scan_Output_GIII_Combined.py)."""
import os
import re

from ..config import (
    CNTRY_OF_ORIGIN_PATTERN, FACTORY_PATTERN, FORMAT_LEGACY, FULL_PATTERN,
    HANGER_PATTERN, ISSUED_BY_PATTERN, LN_START, PO_DATE_PATTERN,
    PO_NUMBER_PATTERN, SIZE_PATTERN, STYLE_PATTERN, UNITS_PATTERN,
    VEND_CNTRY_PATTERN, VENDOR_PATTERN,
)
from ..models import POData, POMetadata, SizeRow

PARSER_VERSION = "1.0"


def _score_confidence(meta: POMetadata) -> int:
    """Return confidence 0–100. Deduct 10 for each missing key field."""
    key_fields = [
        meta.po_number,
        meta.factory,
        meta.country_of_origin,
        meta.xport_date,
        meta.division_code,
        meta.style,
    ]
    missing = sum(1 for f in key_fields if not f)
    return max(0, 100 - missing * 10)


def _search(pattern, text, group=1):
    m = re.search(pattern, text)
    return m.group(group).strip() if m else None


def _extract_metadata(text: str, file_path: str) -> POMetadata:
    factory_num = _search(FACTORY_PATTERN, text, 1)
    factory_name = _search(FACTORY_PATTERN, text, 2)
    factory = f"{factory_num} - {factory_name}" if factory_num and factory_name else None

    hanger = None
    hm = re.search(HANGER_PATTERN, text)
    if hm:
        hanger = text[hm.end():].strip().split('\n')[0].strip()

    return POMetadata(
        po_number=_search(PO_NUMBER_PATTERN, text),
        style=_search(STYLE_PATTERN, text),
        vendor=_search(VENDOR_PATTERN, text),
        issued_by=_search(ISSUED_BY_PATTERN, text),
        po_date=_search(PO_DATE_PATTERN, text),
        vendor_country=_search(VEND_CNTRY_PATTERN, text),
        factory=factory,
        country_of_origin=_search(CNTRY_OF_ORIGIN_PATTERN, text),
        hanger=hanger,
        source_format=FORMAT_LEGACY,
        file_name=os.path.basename(file_path),
        file_path=file_path,
    )


def _extract_size_rows(text: str, meta: POMetadata) -> tuple[list[SizeRow], list[list]]:
    size_rows: list[SizeRow] = []
    summary: list[list] = []
    start = False
    current_color = None

    for line in text.splitlines():
        if line.startswith(LN_START):
            start = True
            continue
        if not start:
            continue

        m = re.search(FULL_PATTERN, line)
        if m:
            color, size, units, upc = m.group(1), m.group(2), int(m.group(3)), m.group(4)
            size_rows.append(SizeRow(meta.po_number, meta.style, color, size, units, upc))
            current_color = color
            continue

        if "TTL" in line:
            hanger = line.split("TTL")[0].strip()
            summary.append([meta.po_number, meta.style, current_color, hanger])

        sm = re.search(SIZE_PATTERN, line)
        if sm:
            um = re.search(UNITS_PATTERN, line)
            if um:
                size_rows.append(SizeRow(
                    meta.po_number, meta.style,
                    current_color or "",  # BUG-13: current_color can be None before first FULL_PATTERN match
                    sm.group(1), int(um.group(1)), um.group(2),
                ))

    return size_rows, summary


def parse(text: str, file_path: str) -> POData:
    meta = _extract_metadata(text, file_path)
    size_rows, summary = _extract_size_rows(text, meta)

    meta.parser_version = PARSER_VERSION
    meta.parse_confidence = _score_confidence(meta)
    meta.validation_status = (
        "valid" if (meta.parse_confidence or 0) >= 70 and size_rows
        else ("exception" if not size_rows else "warning")
    )

    return POData(metadata=meta, size_rows=size_rows, summary_rows=summary)
