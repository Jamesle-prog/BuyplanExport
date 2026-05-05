"""Infor Nexus PO parser.

Text layout notes (from PyMuPDF linearized output):
- Vertical block labels (B/U/Y/E/R etc.) come as single chars on consecutive lines.
- Header key-value pairs: labels appear as a column block, then values as another
  column block — linearized they come out label-block then value-block.
- The line-item column header (15 columns) is a reliable split delimiter.
- Repeated page headers appear mid-text when a line item spans pages.
- Size grids use Size:/UOM:/UPC:/Qty: headers, then groups of 4 lines per size.
"""
import os
import re
from datetime import datetime

from ..config import FORMAT_INFOR_NEXUS
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

# fi/fl ligatures from PDF rendering
def _normalize(text: str) -> str:
    return (text
            .replace('\ufb01', 'fi')
            .replace('\ufb02', 'fl')
            .replace('\u2019', "'"))


def _search(pattern: str, text: str, group: int = 1, flags: int = 0):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


# ---------------------------------------------------------------------------
# Header / metadata extraction
# ---------------------------------------------------------------------------

def _extract_po_number(text: str):
    # Labels: Contract ID / Contract Ref / Order Number / Issue Date / Version
    # then values: (blank) / (blank) / DW843126UC / 2026-01-14 / ...
    return _search(r'Order Number\s*\nIssue Date\s*\nVersion\s*\n(\w+)', text)


def _extract_issue_date(text: str):
    return _search(r'Order Number\s*\nIssue Date\s*\nVersion\s*\n\w+\s*\n(\d{4}-\d{2}-\d{2})', text)


def _extract_version(text: str):
    return _search(r'Order Number\s*\nIssue Date\s*\nVersion\s*\n\w+\s*\n\d{4}-\d{2}-\d{2}\s*\n([^\n]+)', text)


def _extract_buyer(text: str):
    # BUYER block has vertical chars B\nU\nY\nE\nR\n then company name
    return _search(r'B\s*\nU\s*\nY\s*\nE\s*\nR\s*\n([^\n]+)', text)


def _extract_seller(text: str):
    return _search(r'S\s*\nE\s*\nL\s*\nL\s*\nE\s*\nR\s*\n([^\n]+)', text)


def _extract_factory(text: str) -> tuple:
    """Return (factory_name, factory_code)."""
    m = re.search(
        r'F\s*\nA\s*\nC\s*\nT\s*\nO\s*\nR\s*\nY\s*\n(.*?)\n(\d{5})\s*\n',
        text, re.DOTALL,
    )
    if not m:
        return None, None
    # Name lines come before the street address (which starts with NO. or a digit)
    name_lines = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r'NO\.|^\d', line) or any(kw in line for kw in ('ROAD', 'STREET', 'DISTRICT', 'CITY', 'TOWN')):
            break
        name_lines.append(line)
    return ' '.join(name_lines), m.group(2).strip()


def _extract_ship_to(text: str) -> tuple:
    """Return (ship_to_line1, destination_code)."""
    ship = _search(r'S\s*\nH\s*\nI\s*\nP\s*\nT\s*\nO\s*\n([^\n]+)', text)
    # Destination code: WRH__ pattern that appears just before Incoterm section
    dest = _search(r'(WRH\w{2,3})\s*\n(?:Incoterm|FOB)', text)
    return ship, dest


def _extract_incoterm(text: str):
    # Label block: Incoterm / Payment Terms / Division Code / Division Name / Approval Status
    # Then value block starts with Incoterm value on the next line
    return _search(
        r'Incoterm\s*\nPayment Terms\s*\nDivision Code\s*\nDivision Name\s*\nApproval Status\s*\n([^\n]+)',
        text,
    )


def _extract_division(text: str) -> tuple:
    """Return (division_code, division_name)."""
    m = re.search(
        r'Incoterm\s*\nPayment Terms\s*\nDivision Code\s*\nDivision Name\s*\nApproval Status\s*\n'
        r'([^\n]+)\s*\n([^\n]+)\s*\n([^\n]+)\s*\n([^\n]+)',
        text,
    )
    if m:
        return m.group(3).strip(), m.group(4).strip()
    return None, None


def _extract_xport_date(blocks: list) -> str | None:
    """Extract Orig X-Port Date from the first line item block.

    In a line item block the last two YYYY-MM-DD dates are
    Orig X-Port Date and Last Confirmed Date (in that order).
    """
    for block in blocks:
        dates = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', block)
        if len(dates) >= 2:
            return dates[-2]
        if len(dates) == 1:
            return dates[0]
    return None


def _extract_origin_port(text: str):
    # Label block: Order Type / Origin Port / Issued By / Season / Price Type
    # Values: STD / Shanghai / helen.cho ... / V / FOB
    return _search(
        r'Order Type\s*\nOrigin Port\s*\nIssued By\s*\nSeason\s*\nPrice Type\s*\n\S+\s*\n([^\n]+)',
        text,
    )


def _extract_issued_by(text: str):
    raw = _search(
        r'Order Type\s*\nOrigin Port\s*\nIssued By\s*\nSeason\s*\nPrice Type\s*\n\S+\s*\n[^\n]+\s*\n([^\n]+)',
        text,
    )
    if raw:
        # "helen.cho 251532 274183" — Issued By is the first token before digits
        m = re.match(r'([a-zA-Z][a-zA-Z0-9._]+)', raw)
        return m.group(1) if m else raw
    return None


def _extract_discount(text: str):
    return _search(r'(\d+\.\d+%)', text)


def _extract_country(text: str):
    # Label block has 5 labels, Country of Origin is last; its value comes after
    # PO Number (DW...) and Discount (0.75%) values, so look after the discount
    m = re.search(r'\d+\.\d+%\s*\n([A-Z][a-z]+)', text)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Page header stripping
# ---------------------------------------------------------------------------

_PAGE_HEADER_RE = re.compile(
    r'(?:G-III[^\n]+\n)PURCHASE ORDER as of[^\n]+\n'
    r'(?:[^\n]+\n){5,8}'
    r'Powered by Infor Nexus\n',
    re.MULTILINE,
)


def _strip_repeated_headers(text: str) -> str:
    """Keep first page header, strip subsequent ones."""
    matches = list(_PAGE_HEADER_RE.finditer(text))
    if len(matches) <= 1:
        return text
    result = text
    for m in reversed(matches[1:]):
        result = result[:m.start()] + result[m.end():]
    return result


# ---------------------------------------------------------------------------
# Line item parsing
# ---------------------------------------------------------------------------

_LINE_HEADER_RE = re.compile(
    r'Line #\s*\nStyle\s*\nColor Code\s*\nColor Name\s*\nDIM\s*\nSize\s*\nUOM\s*\nUnits\s*\n'
    r'UPC #\s*\nCost P/U\s*\nExtended Cost\s*\nShip Via\s*\nGIII L/C\s*\n'
    r'Orig X-Port Date\s*\nLast Confirmed Date\s*\n'
)


def _parse_size_grid(block: str) -> list[tuple]:
    """Return [(size, upc, qty), ...] from all size grids in block.

    Handles both standard (Size/UOM/UPC/Qty = 4-line) and assortment
    (Size/UOM/UPC/Ratio/Qty = 5-line) grid formats.
    """
    results = []
    for gm in re.finditer(
        r'Size:\s*\nUOM:\s*\nUPC:\s*\n(?:Ratio:\s*\n)?Qty:\s*\n'
        r'(.*?)(?=Size:\s*\n|Total Qty|Detail Instructions|PO Summary|$)',
        block, re.DOTALL,
    ):
        # Detect ratio per-segment (gm.group(0) includes the matched header)
        # so mixed grids get the correct stride independently of other segments.
        has_ratio = bool(re.search(r'Ratio:\s*\n', gm.group(0)))
        stride = 5 if has_ratio else 4
        grid_lines = [l.strip() for l in gm.group(1).splitlines() if l.strip()]
        i = 0
        while i + stride - 1 < len(grid_lines):
            size = grid_lines[i]
            upc = grid_lines[i + 2]
            qty_str = grid_lines[i + stride - 1]
            if size != '-' and re.fullmatch(r'\d{12}', upc):
                try:
                    results.append((size, upc, int(qty_str)))
                except ValueError:
                    pass
            i += stride
    return results


def _parse_line_block(block: str, po_number: str) -> list[SizeRow]:
    # Stop at PO Summary (last page summary table)
    if 'PO Summary' in block:
        block = block[:block.index('PO Summary')]

    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if len(lines) < 4:
        return []

    style = lines[1] if len(lines) > 1 else ''
    color_code = lines[2] if len(lines) > 2 else ''

    size_entries = _parse_size_grid(block)
    return [
        SizeRow(po_number=po_number, style=style, color=color_code,
                size=size, units=qty, upc=upc)
        for size, upc, qty in size_entries
    ]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse(text: str, file_path: str) -> POData:
    text = _normalize(text)

    po_number = _extract_po_number(text) or ''
    factory_name, factory_code = _extract_factory(text)
    factory = f"{factory_code} - {factory_name}" if factory_code else factory_name
    ship_to, dest_code = _extract_ship_to(text)
    div_code, div_name = _extract_division(text)

    clean = _strip_repeated_headers(text)
    parts = _LINE_HEADER_RE.split(clean)
    line_blocks = parts[1:]

    meta = POMetadata(
        po_number=po_number,
        po_date=_extract_issue_date(text),
        buyer=_extract_buyer(text),
        factory=factory,
        ship_to=ship_to,
        destination_code=dest_code,
        country_of_origin=_extract_country(text),
        incoterm=_extract_incoterm(text),
        origin_port=_extract_origin_port(text),
        issued_by=_extract_issued_by(text),
        discount=_extract_discount(text),
        division_code=div_code,
        division_name=div_name,
        xport_date=_extract_xport_date(line_blocks),
        version=_extract_version(text),
        extracted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source_format=FORMAT_INFOR_NEXUS,
        file_name=os.path.basename(file_path),
        file_path=file_path,
    )

    size_rows: list[SizeRow] = []
    for block in line_blocks:
        size_rows.extend(_parse_line_block(block, po_number))

    if size_rows:
        meta.style = size_rows[0].style

    meta.parser_version = PARSER_VERSION
    meta.parse_confidence = _score_confidence(meta)
    meta.validation_status = (
        "valid" if (meta.parse_confidence or 0) >= 70 and size_rows
        else ("exception" if not size_rows else "warning")
    )

    return POData(metadata=meta, size_rows=size_rows)
