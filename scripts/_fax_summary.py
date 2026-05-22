"""Extract all CSKHHN vendor-fax-copy .msg files and produce KL-format summary Excel."""
import sys, os, re, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import extract_msg
import pdfplumber
import pandas as pd
from po_extractor.ui_helpers.kl_format import generate_kl_format_excel
from po_extractor.ui_helpers.kl_consistency import check_kl_excel

MSG_DIR  = r'D:\GIII_PO\CK_Suits'
OUT_PATH = r'C:\Users\Administrator\Desktop\CSKHHN_VendFaxCopy_Summary.xlsx'

# ── Helpers ───────────────────────────────────────────────────────────────────

SIZE_RE = re.compile(
    r'^(?P<size>PXS|P1X|P2X|P3X|PS|PM|PL|PXL|0X|1X|2X|3X|4X|'
    r'XXS|XS|S|M|L|XL|XXL|XXXL)\s+(?P<qty>\d+)',
    re.MULTILINE,
)

def _dedouble(s: str) -> str:
    """Remove character-doubling from fax rendering (take every other char)."""
    return s[::2]


def _parse_fax_pdf(pdf_data: bytes) -> dict:
    with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
        p1 = pdf.pages[0].extract_text() or ''
        p2 = pdf.pages[1].extract_text() if len(pdf.pages) > 1 else ''
        p3 = pdf.pages[2].extract_text() if len(pdf.pages) > 2 else ''

    # ── PO number (doubled) ───────────────────────────────────────────────────
    po_m = re.search(r'PO NUMBER\s+([A-Z0-9]+)', p1)
    po_number = _dedouble(po_m.group(1)) if po_m else '?'

    # ── PO date (doubled: "55//1188//2266" → "5/18/26") ──────────────────────
    date_m = re.search(r'PO DATE\s+([\d/]+)', p1)
    po_date_raw = _dedouble(date_m.group(1)) if date_m else ''
    # normalise "5/18/26" → "5/18/2026"
    parts = po_date_raw.split('/')
    if len(parts) == 3 and len(parts[2]) == 2:
        parts[2] = '20' + parts[2]
    po_date = '/'.join(parts)

    # ── ETD / ship date (line-item table – not doubled) ───────────────────────
    etd_m = re.search(
        r'\b(\d{1,2}/\d{1,2})\s+(\d{1,2}/\d{1,2}/\d{2,4})',
        p1
    )
    etd_display = etd_m.group(1) if etd_m else ''   # "7/30"
    xport_date  = etd_m.group(2) if etd_m else ''   # "7/30/26"

    # ── First line-item row (NOT doubled) ─────────────────────────────────────
    #  001 S5DTN67A ESP/ESPRESSO S 1400 199684849439 3.24 SEA DSH 7/30 7/30/26 5/18
    li_m = re.search(
        r'^001\s+([A-Z0-9]+)\s+([A-Z0-9]+)/(\S+(?:\s+\S+)*?)\s+'
        r'(PXS|P1X|P2X|P3X|PS|PM|PL|PXL|0X|1X|2X|3X|4X|XXS|XS|S|M|L|XL|XXL|XXXL)\s+'
        r'(\d+)\s+(\d+)\s+([\d.]+)',
        p1, re.MULTILINE,
    )
    style      = li_m.group(1).strip() if li_m else '?'
    color_code = li_m.group(2).strip() if li_m else '?'
    color_name = li_m.group(3).strip() if li_m else '?'
    cost_pu    = float(li_m.group(7))  if li_m else None

    # ── All size rows (first row + continuations) — capture UPC too ──────────
    sizes: list[tuple[str, int, str]] = []   # (size, qty, upc)
    if li_m:
        sizes.append((li_m.group(4), int(li_m.group(5)), li_m.group(6)))

    # Continuation rows: "M 2800 199684849422 5/18" — start at column 0
    if li_m:
        flat_m = re.search(r'FLAT PACK TTL', p1[li_m.end():])
        end_pos = li_m.end() + flat_m.start() if flat_m else len(p1)
        rest = p1[li_m.end():end_pos]
        for m in re.finditer(
            r'^(PXS|P1X|P2X|P3X|PS|PM|PL|PXL|0X|1X|2X|3X|4X|XXS|XS|S|M|L|XL|XXL|XXXL)'
            r'\s+(\d+)\s+(\d{10,14})',
            rest, re.MULTILINE,
        ):
            sizes.append((m.group(1), int(m.group(2)), m.group(3)))

    total_qty = sum(q for _, q, _ in sizes)

    # ── Description (doubled, e.g. "DDEESSCCRRIIPPTTIIOONN PPYYSSPP WWOOMMEENN''SS BBLLOOUU RROOSSSS 2255") ──
    desc_m = re.search(r'DESCRIPTION\s+([^\n]+)', p1)
    # Description value is doubled but inter-word spaces are single, so use
    # pair-collapse instead of s[::2] to preserve word boundaries correctly.
    description = re.sub(r'(.)\1', r'\1', desc_m.group(1).strip()) if desc_m else ''

    # ── Hanger / PPK line (doubled, e.g. "SSBBDD FFIINNAALLIIZZEEDD PPPPKK FFLLAATT NNOO HHAANNGGEERR") ──
    hanger = ''
    ppk_m = re.search(r'([^\n]*PPPPKK[^\n]+)', p1)
    if ppk_m:
        hanger = _dedouble(ppk_m.group(1).strip())

    # ── FOB (doubled in Special Instructions, e.g. "FFOOBB:: $$33..6600") ─────
    fob = None
    fob_m = re.search(r'FFOOBB::\s+\$\$([\d.]+)', p1)
    if fob_m:
        fob = float(_dedouble(fob_m.group(1)))
    else:
        # Sometimes single-spaced: "FOB: $3.60"
        fob_m2 = re.search(r'\bFOB:\s*\$([\d.]+)', p1)
        if fob_m2:
            fob = float(fob_m2.group(1))

    # ── HTS (page 2, not doubled) ─────────────────────────────────────────────
    hts_m = re.search(r'\b(\d{4}\.\d{2}\.\d{4})\b', p2)
    hts = hts_m.group(1) if hts_m else ''

    # ── MSRP (page 3, not doubled) ────────────────────────────────────────────
    msrp_m = re.search(r'MSRP\s+\$([\d.]+)', p3)
    msrp = float(msrp_m.group(1)) if msrp_m else None

    # ── Factory (de-double) ───────────────────────────────────────────────────
    fac_m = re.search(r'F A C T O R Y\s+([\w\s\-]+?)INCO', p1)
    factory = _dedouble(fac_m.group(1).replace('  ', ' ').strip()) if fac_m else ''

    return {
        'po_number':   po_number,
        'po_date':     po_date,
        'xport_date':  xport_date,
        'etd_display': etd_display,
        'style':       style,
        'color_code':  color_code,
        'color_name':  color_name,
        'cost_pu':     cost_pu,
        'fob':         fob,
        'hts':         hts,
        'msrp':        str(msrp) if msrp else '',
        'factory':     factory,
        'hanger':      hanger,
        'description': description,
        'total_qty':   total_qty,
        'sizes':       sizes,   # list of (size, qty)
    }


# ── Process all .msg files ────────────────────────────────────────────────────
msg_files = sorted(
    f for f in os.listdir(MSG_DIR)
    if f.startswith('CS-HHN') and f.endswith('.msg')
)

if not msg_files:
    raise RuntimeError(f'No CS-HHN *.msg files found in {MSG_DIR}')

print(f'Processing {len(msg_files)} .msg files …')

parsed: list[dict] = []
for fname in msg_files:
    fpath = os.path.join(MSG_DIR, fname)
    try:
        msg = extract_msg.openMsg(fpath)
        pdf_data = msg.attachments[0].data
        r = _parse_fax_pdf(pdf_data)
        r['file'] = fname
        parsed.append(r)
        print(f'  OK {r["po_number"]:14s}  style={r["style"]}  '
              f'color={r["color_code"]}  qty={r["total_qty"]:,}  '
              f'cost={r["cost_pu"]}  fob={r["fob"]}')
    except Exception as e:
        print(f'  ERR {fname}: {e}')


# ── Build meta + sizes DataFrames (matching kl_format expectations) ───────────
meta_rows, size_rows = [], []

for r in parsed:
    meta_rows.append({
        'po_number':        r['po_number'],
        'style':            r['style'],
        'unit_cost':        r['cost_pu'],
        'xport_date':       r['xport_date'],
        'issue_date':       r['po_date'],
        'factory':          r['factory'],
        'seller':           'HIGH HOPE NEWES',
        'style_group':      r['hts'],
        'hanger':           r['hanger'],
        'description_code': r['description'],
        'customer':         'ROSS STORES',
        'ship_to':          'ROSS STORES / 3404 INDIAN AVE / DISTRIBUTION CENTER / PERRIS,CA 92571',
        'cpo':              'TBD',
        'msrp':             r['msrp'],
        'packaging':        '',
    })
    for size, qty, upc in r['sizes']:
        size_rows.append({
            'PO Number': r['po_number'],
            'Style':     r['style'],
            'Color':     f"{r['color_code']}/{r['color_name']}",
            'Size':      size,
            'Units':     qty,
            'UPC':       upc,
        })

df_meta  = pd.DataFrame(meta_rows)
df_sizes = pd.DataFrame(size_rows)

# ── Generate Excel ────────────────────────────────────────────────────────────
print()
print(f'Building KL-format Excel ({len(df_meta)} POs, {int(df_sizes["Units"].sum()):,} units) …')

kl_bytes = generate_kl_format_excel(df_meta, df_sizes)
if not kl_bytes:
    raise RuntimeError('Excel generator returned empty — check size rows.')

issues = check_kl_excel(df_meta, df_sizes, kl_bytes)
if issues:
    raise RuntimeError('Consistency check failed — Excel not saved.')

def _safe_write(path: str, data: bytes) -> str:
    try:
        with open(path, 'wb') as fh:
            fh.write(data)
        return path
    except PermissionError:
        base, ext = os.path.splitext(path)
        alt = f'{base}_new{ext}'
        with open(alt, 'wb') as fh:
            fh.write(data)
        print(f'  (File locked — saved to {os.path.basename(alt)})')
        return alt

saved = _safe_write(OUT_PATH, kl_bytes)
sz    = os.path.getsize(saved)
print(f'Saved {sz:,} bytes → {saved}')
print(f'POs: {len(df_meta)}  |  Total units: {int(df_sizes["Units"].sum()):,}')
