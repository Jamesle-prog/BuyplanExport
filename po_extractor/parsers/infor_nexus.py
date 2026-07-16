"""Infor Nexus PO parser — pypdfium2 text layout.

pypdfium2 extracts text in reading order (left-to-right, top-to-bottom).
Key layout differences from PyMuPDF column-order extraction:
  - Table header labels appear on ONE line, not one label per line.
  - Vertical party labels (B/U/Y/E/R etc.) are preserved as single chars
    on consecutive lines — those patterns are unchanged.
  - Line-item columns appear space-separated on a single line.
  - Size grid (Size:/UOM:/UPC:/Qty:) remains one entry per line.
"""
import os
import re
from datetime import datetime

from ..config import FORMAT_INFOR_NEXUS
from ..models import POData, POMetadata, SizeRow

PARSER_VERSION = "2.0"


def _score_confidence(meta: POMetadata) -> int:
    key_fields = [
        meta.po_number, meta.factory, meta.country_of_origin,
        meta.xport_date, meta.division_code, meta.style,
    ]
    missing = sum(1 for f in key_fields if not f)
    return max(0, 100 - missing * 10)


def _normalize(text: str) -> str:
    return (text
            .replace('ﬁ', 'fi')
            .replace('ﬂ', 'fl')
            .replace('’', "'"))


def _search(pattern: str, text: str, group: int = 1, flags: int = 0):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


# ---------------------------------------------------------------------------
# Header / metadata extraction  (pypdfium2 single-line label format)
# ---------------------------------------------------------------------------

def _extract_po_number(text: str):
    # "Order Number Issue Date Version\r\nDWCCC013DS 2026-03-25 ..."
    return _search(r'Order Number Issue Date Version\s*[\r\n](\S+)', text)


def _extract_issue_date(text: str):
    return _search(r'Order Number Issue Date Version\s*[\r\n]\S+\s+(\d{4}-\d{2}-\d{2})', text)


def _extract_version(text: str):
    return _search(r'Order Number Issue Date Version\s*[\r\n]\S+\s+[\d-]+\s+(\S+)', text)


def _extract_buyer(text: str):
    # Vertical chars B/U/Y/E/R preserved by pypdfium2
    return _search(r'B\s*\nU\s*\nY\s*\nE\s*\nR\s*\n([^\r\n]+)', text)


def _extract_seller(text: str):
    return _search(r'S\s*\nE\s*\nL\s*\nL\s*\nE\s*\nR\s*\n([^\r\n]+)', text)


def _extract_factory(text: str) -> tuple:
    """Return (factory_name, factory_code)."""
    m = re.search(
        r'F\s*\nA\s*\nC\s*\nT\s*\nO\s*\nR\s*\nY\s*\n(.*?)\n(\d{5,6})',
        text, re.DOTALL,
    )
    if not m:
        return None, None
    name_lines = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r'NO\.|^\d', line) or any(
            kw in line for kw in ('ROAD', 'STREET', 'DISTRICT', 'CITY', 'TOWN')
        ):
            break
        name_lines.append(line)
    return ' '.join(name_lines) or None, m.group(2).strip()


def _extract_ship_to(text: str) -> tuple:
    """Return (ship_to_name, destination_code)."""
    ship = _search(r'S\s*\nH\s*\nI\s*\nP\s*\nT\s*\nO\s*\n([^\r\n]+)', text)
    # WRHDS appears as last token before the Incoterm header line
    dest = _search(r'(WRH\w{2,3})\s*[\r\n]', text)
    return ship, dest


def _extract_incoterm(text: str):
    # "Incoterm Payment Terms Division Code Division Name Approval Status\r\nFOB ORIGIN ..."
    return _search(
        r'Incoterm Payment Terms[^\r\n]+[\r\n]+((?:FOB|CIF|EXW|DAP|DDP|CFR|CPT|CIP|FCA|FAS)(?:\s+\w+)?)',
        text,
    )


def _extract_payment_terms(text: str):
    # Value line: "FOB ORIGIN Supplier Damage Allow 0075 \r\nN75\r\nDW ..."
    # The short payment code (e.g. N75, L30) follows on its own line
    m = re.search(r'Supplier[^\r\n]+\d{4}\s*[\r\n](\w+)', text)
    if m:
        return m.group(1).strip()
    # Fallback: "Open[^\n]+" style terms
    m = re.search(r'(Open[^\r\n]+)', text)
    return m.group(1).strip() if m else None


def _extract_division(text: str) -> tuple:
    """Return (division_code, division_name) from the values line."""
    # Values line 3: "DW DKNY W/SPRTSWR Y"  — code(2 chars) name(rest) status(1 char)
    m = re.search(r'\n([A-Z]{2}) ([A-Z][A-Z0-9/ ]+?) ([YN])\r?\n', text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None


def _extract_approval_status(text: str):
    m = re.search(r'\n[A-Z]{2} [A-Z][A-Z0-9/ ]+ ([YN])\r?\n', text)
    return m.group(1).strip() if m else None


def _extract_origin_port(text: str):
    # "Order Type Origin Port Issued By Season Price Type\r\nBTB Shanghai ana.cristian ..."
    # Issued By is a dotted username — anchoring on it keeps multi-word ports
    # intact ("Ho Chi Minh" used to truncate to "Ho" with a bare \S+ capture).
    port = _search(
        r'Order Type Origin Port Issued By Season Price Type\s*[\r\n]'
        r'\S+\s+(.+?)\s+[a-zA-Z][a-zA-Z0-9_]*\.[a-zA-Z0-9._]+(?:\s|$)',
        text,
    )
    if port:
        return port
    # Fallback (no dotted username on the line): original single-token capture.
    return _search(
        r'Order Type Origin Port Issued By Season Price Type\s*[\r\n]\S+\s+(\S+)',
        text,
    )


def _extract_issued_by(text: str):
    raw = _search(
        r'Order Type Origin Port Issued By Season Price Type\s*[\r\n]\S+\s+\S+\s+(\S+)',
        text,
    )
    if raw:
        m = re.match(r'([a-zA-Z][a-zA-Z0-9._]+)', raw)
        return m.group(1) if m else raw
    return None


def _extract_season(text: str):
    # "BTB Shanghai ana.cristian 331491 V FOB" — season is single letter before Price Type
    return _search(
        r'Order Type Origin Port Issued By Season Price Type\s*[\r\n]\S+\s+\S+\s+\S+(?:\s+\d+)?\s+([A-Z])\s+',
        text,
    )


def _extract_discount(text: str):
    return _search(r'(\d+\.\d+%)', text)


def _extract_country(text: str):
    # "PO Number Label Hanger Discount Country of Origin\r\nDWCCC013DS 0.75% China"
    # Country is the last field on the line — capture to end of line so
    # multi-word countries ("Sri Lanka") aren't truncated to their first word.
    return _search(r'PO Number[^\r\n]+[\r\n]+\S+\s+[\d.]+%\s+([^\r\n]+)', text)


def _extract_customer(text: str):
    # "Customer MODIVO.EU SP.ZO.O Packaging F"
    return _search(r'Customer\s+(.+?)\s+Packaging', text)


def _extract_style_description(text: str):
    # "Factory Ship by Date 2026-07-15 Style Description L/S STUDDED LIQUID J"
    return _search(r'Style Description\s+([^\r\n]+)', text)


def _extract_style_group(text: str):
    # "Original Factory Ship by Date 2026-07-15 Style Group KNIT TOPS"
    return _search(r'Style Group\s+([^\r\n]+)', text)


def _extract_unit_cost(text: str):
    # Line item: "... 2500 4.50 USD 11,250.00 USD S 2026-07-15 ..."
    # Unit cost is the decimal before "USD <total> USD"
    return _search(r'\s([\d.]+)\s+USD\s+[\d,]+\.\d{2}\s+USD\s+[A-Z]\s+\d{4}-\d{2}-\d{2}', text)


def _extract_extended_cost(text: str):
    # "Extended Cost: 11,250.00 USD"
    return _search(r'Extended Cost:\s*([\d,]+\.\d{2})\s+USD', text)


def _extract_xport_date(blocks: list) -> str | None:
    for block in blocks:
        dates = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', block)
        if len(dates) >= 2:
            return dates[-2]
        if len(dates) == 1:
            return dates[0]
    return None


def _extract_factory_ship_date(blocks: list) -> str | None:
    """Last Confirmed Date is the final date on the line item."""
    for block in blocks:
        dates = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', block)
        if len(dates) >= 1:
            return dates[-1]
    return None


# ---------------------------------------------------------------------------
# Page header stripping
# ---------------------------------------------------------------------------

_PAGE_HEADER_RE = re.compile(
    r'[^\n]+PURCHASE ORDER as of[^\n]+\n'
    r'(?:[^\n]+\n){3,6}'
    r'[^\n]*Powered by Infor Nexus[^\n]*\n',
    re.MULTILINE,
)


def _strip_repeated_headers(text: str) -> str:
    matches = list(_PAGE_HEADER_RE.finditer(text))
    if len(matches) <= 1:
        return text
    result = text
    for m in reversed(matches[1:]):
        result = result[:m.start()] + result[m.end():]
    return result


# ---------------------------------------------------------------------------
# Line item parsing  (pypdfium2: entire item on one line)
# ---------------------------------------------------------------------------

_LINE_HEADER_RE = re.compile(
    r'Line #\s+Style\s+Color Code\s+Color Name\s+DIM\s+Size\s+UOM\s+Units\s+'
    r'UPC #\s+Cost P/U\s+Extended Cost\s+Ship Via\s+GIII L/C\s+'
    r'Orig X-Port Date\s+Last Confirmed Date\s*[\r\n]'
)


def _parse_size_grid(block: str) -> list[tuple]:
    """Return [(size, upc, qty), ...] from a size grid.

    pypdfium2 linearises the grid two ways depending on the PDF's internal
    reading order — column-major (Size:/UOM:/UPC:/Qty: headers together, then
    one size's four values, repeat) or row-major (Size: then all sizes, UOM:
    then all UOMs, UPC: then all UPCs, Qty: then all qtys). Try column-major
    first, then fall back to row-major so the UPCs/qtys aren't silently
    dropped for the row-major PDFs."""
    results = _parse_size_grid_colmajor(block)
    if not results:
        results = _parse_size_grid_rowmajor(block)
    return results


def _parse_size_grid_colmajor(block: str) -> list[tuple]:
    """Column-major: headers stacked, then stride-4 (or 5 with Ratio) values."""
    results = []
    for gm in re.finditer(
        r'Size:\s*\nUOM:\s*\nUPC:\s*\n(?:Ratio:\s*\n)?Qty:\s*\n'
        r'(.*?)(?=Size:\s*\n|Total Qty|Detail Instructions|PO Summary|$)',
        block, re.DOTALL,
    ):
        has_ratio = bool(re.search(r'Ratio:\s*\n', gm.group(0)))
        stride = 5 if has_ratio else 4
        grid_lines = [l.strip() for l in gm.group(1).splitlines() if l.strip()]
        i = 0
        while i + stride - 1 < len(grid_lines):
            size = grid_lines[i]
            upc = grid_lines[i + 2]
            qty_str = grid_lines[i + stride - 1]
            # 12-digit UPC-A or 13-digit EAN — rejecting EANs silently
            # dropped that size's quantity.  Quantities may carry thousands
            # separators ("2,500").
            if size != '-' and re.fullmatch(r'\d{12,13}', upc):
                try:
                    results.append((size, upc, int(qty_str.replace(',', ''))))
                except ValueError:
                    pass
            i += stride
    return results


def _parse_size_grid_rowmajor(block: str) -> list[tuple]:
    """Row-major: 'Size:' then every size, 'UPC:' then every UPC, 'Qty:' then
    every qty — matched by position. Used when the column-major parse finds
    nothing (some PDFs linearise the table row-first)."""

    def _section(name: str, stops: list[str]) -> list[str]:
        # NOTE: several stop words already end in ":" (e.g. "Qty:") -- a
        # trailing \b right after a non-word colon character never matches
        # (colon -> whitespace/newline is not a word boundary), which used to
        # make the lookahead fail silently and let the non-greedy match run
        # past the intended stop label. No \b needed: the alternation text
        # itself (colon or not) is the boundary.
        stop_re = "|".join(stops)
        m = re.search(rf'{name}:\s*\n(.*?)(?=\n(?:{stop_re})|$)',
                      block, re.DOTALL)
        if not m:
            return []
        return [l.strip() for l in m.group(1).splitlines() if l.strip()]

    sizes = _section("Size", ["UOM:", "UPC:", "Ratio:", "Qty:"])
    upcs  = _section("UPC",  ["Ratio:", "Qty:", "Size:"])
    qtys  = _section("Qty",  ["Size:", "Total Qty", "Detail Instructions",
                              "PO Summary"])
    results = []
    for i in range(min(len(sizes), len(upcs), len(qtys))):
        size, upc, qty = sizes[i], upcs[i], qtys[i]
        if size != '-' and re.fullmatch(r'\d{12,13}', upc):
            try:
                results.append((size, upc, int(qty.replace(',', ''))))
            except ValueError:
                pass
    return results


def _parse_line_block(block: str, po_number: str) -> list[SizeRow]:
    if 'PO Summary' in block:
        block = block[:block.index('PO Summary')]

    # pypdfium2: first non-empty line is the full item line
    # "1 P6HHJETI BLK BLACK - EA EA 2500 4.50 USD ..."
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if not lines:
        return []

    style = ''
    color_code = ''
    m = re.match(r'\d+\s+(\S+)\s+(\S+)', lines[0])
    if m:
        style = m.group(1)
        color_code = m.group(2)

    size_entries = _parse_size_grid(block)
    # Per-line ex-factory date: the same SKU shipped in two windows lands in
    # two blocks with different dates — carry it so the store keeps both rows
    # instead of the second overwriting the first.
    xfty = _extract_factory_ship_date([block]) or ""
    return [
        SizeRow(po_number=po_number, style=style, color=color_code,
                size=size, units=qty, upc=upc, xfty_date=xfty)
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
        version=_extract_version(text),
        buyer=_extract_buyer(text),
        seller=_extract_seller(text),
        factory=factory,
        ship_to=ship_to,
        destination_code=dest_code,
        country_of_origin=_extract_country(text),
        incoterm=_extract_incoterm(text),
        origin_port=_extract_origin_port(text),
        issued_by=_extract_issued_by(text),
        discount=_extract_discount(text),
        payment_terms=_extract_payment_terms(text),
        approval_status=_extract_approval_status(text),
        season=_extract_season(text),
        division_code=div_code,
        division_name=div_name,
        customer=_extract_customer(text),
        style_description=_extract_style_description(text),
        style_group=_extract_style_group(text),
        unit_cost=_extract_unit_cost(text),
        line_extended_cost=_extract_extended_cost(text),
        xport_date=_extract_xport_date(line_blocks),
        factory_ship_date=_extract_factory_ship_date(line_blocks),
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
