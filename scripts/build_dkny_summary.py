"""Build DKNY HOL 26 PO Summary Excel in KL-reference format.

Parses every PDF in SUITS-DKNY / PO / Hol 26 ROSS, refreshes the production
DB, then generates the two-sheet KL-format workbook via kl_format.py.

Output sheets:
  PO Detail  — one row per size (21 columns)
  Summary    — Part A: pivot per PO  /  Part B: style rollup
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from po_extractor.parsers import parse_pdf
from po_extractor.store.po_store import POStore
from po_extractor.config import DB_PATH
from po_extractor.ui_helpers.kl_format import generate_kl_format_excel
from po_extractor.ui_helpers.kl_consistency import check_kl_excel


# ── Locate the Mountain Duck business directory dynamically ───────────────────
def _find_biz_dir() -> str:
    """Return the '业务三部一组' path regardless of console encoding."""
    base = (
        r'C:\Users\Administrator\Mountain Duck'
        r'\873c48f1-d867-4501-87f7-c1b938827cf4'
    )
    for d in os.listdir(base):
        full = os.path.join(base, d)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, '4.SUITS')):
            return full
    raise RuntimeError(f"Cannot locate business directory under {base}")


PDF_DIR  = os.path.join(
    _find_biz_dir(), '4.SUITS', 'SUITS-DKNY', 'PO', 'Hol 26 ROSS'
)
OUT_PATH = r'C:\Users\Administrator\Desktop\DUKHHA_HOL26_PO_Summary.xlsx'

# ── Parse all PDFs and refresh DB ────────────────────────────────────────────
store = POStore(DB_PATH)

pdf_files = sorted(
    f for f in os.listdir(PDF_DIR)
    if f.lower().endswith('.pdf')
)
if not pdf_files:
    raise RuntimeError(f"No PDFs found in {PDF_DIR}")

print(f"Found {len(pdf_files)} PDF(s) in {PDF_DIR}")

po_numbers = []
for fname in pdf_files:
    po = parse_pdf(os.path.join(PDF_DIR, fname))
    pn = po.metadata.po_number or ''
    if not pn:
        print(f"  SKIP (no PO number): {fname}")
        continue
    store.force_save(po)
    po_numbers.append(pn)
    print(f"  {pn}: style={po.metadata.style}  fob={po.metadata.unit_cost}"
          f"  cpo={po.metadata.cpo}  sizes={len(po.size_rows)}"
          f"  conf={po.metadata.parse_confidence}")

if not po_numbers:
    raise RuntimeError("No valid POs parsed — aborting.")

# ── Load from DB and generate Excel ──────────────────────────────────────────
df_meta  = store.list_pos()
df_meta  = df_meta[df_meta['po_number'].isin(po_numbers)].copy()
df_sizes = store.load_size_rows(po_numbers)

kl_bytes = generate_kl_format_excel(df_meta, df_sizes)
if not kl_bytes:
    raise RuntimeError("Excel generator returned empty — check size rows in DB.")

# ── Consistency check before writing to disk ─────────────────────────────────
print()
issues = check_kl_excel(df_meta, df_sizes, kl_bytes)
if issues:
    raise RuntimeError("Consistency check failed — Excel not saved. Fix issues above.")

with open(OUT_PATH, 'wb') as fh:
    fh.write(kl_bytes)

sz          = os.path.getsize(OUT_PATH)
total_units = int(df_sizes['Units'].sum()) if not df_sizes.empty else 0
print(f"Saved {sz:,} bytes -> {OUT_PATH}")
print(f"POs: {len(po_numbers)}  |  Total units: {total_units:,}")
