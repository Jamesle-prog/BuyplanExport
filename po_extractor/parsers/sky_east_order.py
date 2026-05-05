"""Parser for Sky East Purchase Contract Excel files.

File structure (Sheet1):
  Row 1       : "Sky East International Trading Limited"
  Row 3       : PC NO.      (col 5)  → e.g. HHPPC038
  Row 4       : Date        (col 5)
  Row 5       : Party A     (col 5)  – Buyer = Sky East
  Row 7       : Party B     (col 5)  – Seller = HHN / Newest
  Row 9       : Currency    (col 5)
  Row 10      : Payment     (col 5)
  Row 13      : Trade term  (col 5)
  Row 16      : Column header row
  Row 17+     : Data rows
  Brand divider: col-1 = non-integer string with no Style / PO (e.g. "ABOUT YOU")
  Footer row  : col-1 starts with "SAY " or col contains "Total"

Returns SkyEastContract (with SkyEastItem list) matching models/sky_east_data.py.

Same PC No., same (style + color + zalando_po) across files → quantities are
aggregated by the store.  Amendment detection (size breakdown change) is also
handled in the store.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
import openpyxl

from ..models.sky_east_data import SkyEastContract, SkyEastItem
from ..models.fabric_part import FabricPart
from ..utils.image_extractor import extract_dispimg_positions

PARSER_VERSION = "1.1"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DISPIMG_RE = re.compile(r'DISPIMG\("(ID_[0-9A-Fa-f]+)"', re.IGNORECASE)

SIZE_KEYS  = ("XS", "S", "M", "L", "XL", "2XL")
_SIZE_COLS = ("xs",  "s", "m", "l", "xl", "xxl")   # DB column names


def _v(cell_value) -> str:
    if cell_value is None:
        return ""
    if isinstance(cell_value, datetime):
        return cell_value.strftime("%Y-%m-%d")
    return str(cell_value).strip()


def _int(v) -> int:
    try:
        return int(float(str(v))) if v not in (None, "") else 0
    except (ValueError, TypeError):
        return 0


def _float(v) -> float:
    try:
        return float(str(v)) if v not in (None, "") else 0.0
    except (ValueError, TypeError):
        return 0.0


def _dispimg_id(val) -> str:
    if not val:
        return ""
    m = _DISPIMG_RE.search(str(val))
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Contract header detection (label → value scan)
# ---------------------------------------------------------------------------

# Each entry: (field_name, set_of_label_aliases)
# Labels appear somewhere in the header block (rows 1-20), values are read
# from the same row — either the rightmost non-empty cell in cols A-H or the
# first cell in cols C-H after the label column.
_HEADER_LABEL_ALIASES: list[tuple[str, set[str]]] = [
    ("pc_no",         {"pc no.", "pc no", "p.c. no.", "pc number", "合同编号", "contract no"}),
    ("pc_date",       {"date", "日期", "合同日期"}),
    ("party_a",       {"party a", "buyer", "甲方", "party a (buyer)"}),
    ("party_b",       {"party b", "seller", "乙方", "party b (seller)"}),
    ("currency",      {"currency", "货币", "currency:"}),
    ("payment_terms", {"payment", "payment method", "payment terms", "付款方式"}),
    ("trade_term",    {"trade term", "trade terms", "贸易条款", "incoterm"}),
]


def _norm_label(s: str) -> str:
    """Lower-case, strip, remove trailing punctuation for label matching."""
    return str(s).strip().lower().rstrip(".: ：")


def _parse_contract_header(ws) -> dict[str, str]:
    """Scan rows 1-20 searching for label text; return {field: value_str}.

    Strategy per row:
      1. Scan cols A-D for a cell whose normalised text matches a known label.
      2. Once found, read the value from col E (the standard value column in
         Sky East contracts).  If col E is blank, walk cols F-H for the first
         non-empty cell.
      3. Fall back to the hardcoded row/col positions if nothing is found
         (keeps backward-compatibility with files that have no label text).
    """
    # Build normalised alias → field lookup
    alias_to_field: dict[str, str] = {}
    for field, aliases in _HEADER_LABEL_ALIASES:
        for alias in aliases:
            alias_to_field[_norm_label(alias)] = field

    found: dict[str, str] = {}

    for r in range(1, 21):
        for c in range(1, 5):   # cols A-D are label columns
            cell_val = ws.cell(row=r, column=c).value
            if cell_val is None:
                continue
            norm = _norm_label(str(cell_val))
            field = alias_to_field.get(norm)
            if field and field not in found:
                # Value is in col E; fall back to first non-empty in cols F-H
                val = _v(ws.cell(row=r, column=5).value)
                if not val:
                    for vc in range(6, 9):
                        val = _v(ws.cell(row=r, column=vc).value)
                        if val:
                            break
                found[field] = val
                break   # move to next row once a field is found on this row

    # Hard-coded fallbacks for any field not found by label search
    _FALLBACK_ROWS = {
        "pc_no": (3, 5), "pc_date": (4, 5), "party_a": (5, 5),
        "party_b": (7, 5), "currency": (9, 5),
        "payment_terms": (10, 5), "trade_term": (13, 5),
    }
    for field, (row, col) in _FALLBACK_ROWS.items():
        if field not in found:
            found[field] = _v(ws.cell(row=row, column=col).value)

    return found


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

_COL_ALIASES: dict[str, set[str]] = {
    "item":         {"item", "item no", "item no.", "no", "no."},
    "return_label": {"需要挂 return label", "return label", "return label "},
    "style_no":     {"style no.", "style no", "style"},
    "po_number":    {"po number", "po no.", "po#", "po_number"},
    "config_sku":   {"config_sku", "config sku"},
    "article_name": {"supplier article name", "article name"},
    "picture":      {"piicture", "picture", "image"},
    "fabric_no":    {"fabric item number", "fabric item no", "fabric item number"},
    "fabrication":  {"fabrication", "fabrication "},
    "brand":        {"brand"},
    "color_name":   {"color name", "colour name"},
    "color_code":   {"colour code", "color code"},
    "launch_date":  {"launch date"},
    "xs":  {"xs"}, "s": {"s"}, "m": {"m"}, "l": {"l"}, "xl": {"xl"},
    "xxl": {"2xl", "xxl"},
    "total_qty":    {"total quantity", "qty", "total qty"},
    "fob_usd":      {"fob\nusd", "fob usd", " fob \nusd", "fob"},
    "total_cost":   {"total cost\nusd", "total cost usd", "total cost"},
    "ex_fty":       {"ex-fty", "ex fty", "exfty"},
}

_DEFAULTS: dict[str, int] = {   # 1-based column fallbacks
    "item": 1, "return_label": 3, "style_no": 4, "po_number": 5,
    "config_sku": 6, "article_name": 7, "picture": 8, "fabric_no": 9,
    "fabrication": 10, "brand": 11, "color_name": 12, "color_code": 13,
    "launch_date": 14,
    "xs": 15, "s": 16, "m": 17, "l": 18, "xl": 19, "xxl": 20,
    "total_qty": 21, "fob_usd": 22, "total_cost": 23, "ex_fty": 24,
}


def _find_header_row(ws) -> int:
    for r in range(1, 30):
        for c in range(1, 15):
            v = _v(ws.cell(row=r, column=c).value).lower()
            if v in ("style no.", "style no", "po number"):
                return r
    return 16


def _map_columns(ws, hrow: int) -> dict[str, int]:
    col_map: dict[str, int] = {}
    for c in range(1, min(ws.max_column + 1, 35)):
        raw = _v(ws.cell(row=hrow, column=c).value).lower().strip()
        for key, aliases in _COL_ALIASES.items():
            if raw and raw in aliases and key not in col_map:
                col_map[key] = c
                break
    for k, v in _DEFAULTS.items():
        col_map.setdefault(k, v)
    return col_map


# ---------------------------------------------------------------------------
# Row classification
# ---------------------------------------------------------------------------

def _is_brand_divider(item_val, style_val) -> tuple[bool, str]:
    """Return (True, brand_name) for brand section header rows."""
    if item_val is None or item_val == "":
        return False, ""
    if isinstance(item_val, (int, float)):
        return False, ""
    s = str(item_val).strip()
    if re.match(r'^\d+$', s):
        return False, ""
    if re.match(r'^(SAY |TOTAL)', s, re.IGNORECASE):
        return False, ""
    if style_val and str(style_val).strip():
        return False, ""        # has a style number → it's a data row
    return True, s


def _is_footer(item_val) -> bool:
    if item_val is None:
        return False
    s = str(item_val).strip()
    return bool(re.match(r'^(SAY |TOTAL)', s, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Multi-fabric extraction
# ---------------------------------------------------------------------------

def _extract_fabric_parts(fabric_cell) -> list[FabricPart]:
    """
    Parse a (possibly multi-line) fabric-number cell into an ordered list
    of FabricPart objects.

    Examples
    --------
    "HHN-JA-01715"
        → [FabricPart(seq=1, body_part="", hhn_no="HHN-JA-01715")]

    "大身HHN-JA-01715\\n网布HHN-MS-01794"
        → [FabricPart(seq=1, body_part="大身", hhn_no="HHN-JA-01715"),
           FabricPart(seq=2, body_part="网布", hhn_no="HHN-MS-01794")]

    "大身：HHN-JA-01715，300克\\n口袋：HHN-MS-01794"
        → same as above (tolerates Chinese punctuation)
    """
    raw = _v(fabric_cell)
    if not raw:
        return []

    parts: list[FabricPart] = []
    seq = 1
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        matches = list(re.finditer(r'(HHN-\S+)', line))
        if not matches:
            continue
        for m in matches:
            hhn = m.group(1).strip("，,：: ")
            prefix = line[:m.start()].strip()
            prefix = re.sub(r'[：:,，\s]+$', '', prefix)
            parts.append(FabricPart(seq=seq, body_part=prefix, hhn_no=hhn))
            seq += 1
    return parts


def _fabric_item_no(parts: list[FabricPart]) -> str:
    """Primary HHN number for backward-compat fabric_item_no field."""
    return parts[0].hhn_no if parts else ""


def _fabrication_display(parts: list[FabricPart], fabrication_cell) -> str:
    """Human-readable multi-fabric string for the fabrication display field."""
    fab_raw = _v(fabrication_cell)
    if not parts:
        return fab_raw
    segments = []
    for p in parts:
        seg = p.hhn_no
        if p.body_part:
            seg = f"{p.body_part}: {seg}"
        segments.append(seg)
    result = " | ".join(segments)
    if fab_raw:
        result += f" — {fab_raw}"
    return result


# ---------------------------------------------------------------------------
# Public parse function
# ---------------------------------------------------------------------------

def parse(path: str, processed_by: str = "") -> SkyEastContract:
    """
    Parse a Sky East Excel file (Sheet1) and return a SkyEastContract.

    Each SkyEastItem has:
      • fabric_item_no  — primary HHN (backward compat)
      • fabrication     — human-readable display string
      • fabric_parts    — list[FabricPart] with full structured data

    processed_by  : username of the person who triggered the upload (optional)
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fname   = os.path.basename(path)

    # ── Source file hash ──────────────────────────────────────────────────────
    with open(path, "rb") as fh:
        file_hash = hashlib.md5(fh.read()).hexdigest()

    # ── Contract header — dynamic label search with position fallbacks ────────
    hdr      = _parse_contract_header(ws)
    pc_no    = hdr["pc_no"]
    pc_date  = hdr["pc_date"]
    party_a  = hdr["party_a"]
    party_b  = hdr["party_b"]
    currency = hdr["currency"]
    payment  = hdr["payment_terms"]
    trade    = hdr["trade_term"]

    # ── Column mapping ────────────────────────────────────────────────────────
    hrow = _find_header_row(ws)
    col  = _map_columns(ws, hrow)

    # Pre-extract DISPIMG positions directly from XML (reliable even with data_only=True)
    dispimg_pos = extract_dispimg_positions(path, sheet_index=0)

    def cv(row, key):
        c = col.get(key)
        return ws.cell(row=row, column=c).value if c else None

    # ── Parse data rows ───────────────────────────────────────────────────────
    items: list[SkyEastItem] = []
    current_brand = ""

    for r in range(hrow + 1, ws.max_row + 1):
        item_raw  = cv(r, "item")
        style_raw = cv(r, "style_no")

        if _is_footer(item_raw):
            break

        is_div, brand_name = _is_brand_divider(item_raw, style_raw)
        if is_div:
            current_brand = brand_name
            continue

        # Accept rows that either have an integer item number OR a valid style number.
        style_no = _v(style_raw).strip("\n ")
        if item_raw is None or item_raw == "":
            if not style_no:
                continue
        else:
            try:
                int(float(str(item_raw)))
            except (ValueError, TypeError):
                if not style_no:
                    continue

        if not style_no:
            continue

        # Brand: prefer per-row brand col, fall back to last seen divider
        brand = _v(cv(r, "brand")) or current_brand

        # Sizes dict
        xs  = _int(cv(r, "xs"))
        s   = _int(cv(r, "s"))
        m   = _int(cv(r, "m"))
        l   = _int(cv(r, "l"))
        xl  = _int(cv(r, "xl"))
        xxl = _int(cv(r, "xxl"))
        sizes = {"XS": xs, "S": s, "M": m, "L": l, "XL": xl, "2XL": xxl}

        total_qty = _int(cv(r, "total_qty"))
        if total_qty == 0:
            total_qty = xs + s + m + l + xl + xxl

        # ── Multi-fabric extraction ───────────────────────────────────────────
        fabric_parts = _extract_fabric_parts(cv(r, "fabric_no"))

        item = SkyEastItem(
            pc_no          = pc_no,
            zalando_po     = _v(cv(r, "po_number")),
            style          = style_no,
            config_sku     = _v(cv(r, "config_sku")),
            article_name   = _v(cv(r, "article_name")),
            brand          = brand,
            color_name     = _v(cv(r, "color_name")).replace("\n", " ").strip(),
            colour_code    = _v(cv(r, "color_code")),
            launch_date    = _v(cv(r, "launch_date")),
            fabric_item_no = _fabric_item_no(fabric_parts),
            fabrication    = _fabrication_display(fabric_parts, cv(r, "fabrication")),
            contract_no    = "",
            sizes          = sizes,
            total_qty      = total_qty,
            fob_usd        = _float(cv(r, "fob_usd")),
            total_cost_usd = _float(cv(r, "total_cost")),
            ex_fty_date    = _v(cv(r, "ex_fty")) or None,
            picture_id     = (dispimg_pos.get((r, col.get("picture", 8)))
                              or _dispimg_id(cv(r, "picture"))),
            fabric_parts   = fabric_parts,
        )
        items.append(item)

    wb.close()

    return SkyEastContract(
        pc_no            = pc_no,
        pc_date          = pc_date,
        buyer            = party_a,
        seller           = party_b,
        currency         = currency,
        payment_terms    = payment,
        trade_term       = trade,
        items            = items,
        source_file      = fname,
        file_path        = path,
        extracted_at     = now_str,
        parser_version   = PARSER_VERSION,
        parse_confidence = 100 if (pc_no and items) else 50,
        source_file_hash = file_hash,
        processed_by     = processed_by,
    )
