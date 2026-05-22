"""Build KL FALL 26 PO Summary Excel in KL-reference format.

Parses every PDF in SUITS -KL / PO / FALL 26 ROSS, refreshes the production
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


ROOT_DIR = os.path.join(
    _find_biz_dir(), '4.SUITS', 'SUITS -KL', 'PO', 'FALL 26 ROSS'
)
OUT_PATH = r'C:\Users\Administrator\Desktop\LSKHHN_FALL26_PO_Summary.xlsx'

_VENDOR_PREFIX = 'lskhhn'


def _find_vendor_pdfs(root: str, prefix: str) -> list[str]:
    """Return sorted absolute paths of vendor PDFs matching *prefix*.

    Strategy — root-first, recursive-fallback:
      1. Look in *root* directly.  If any matching PDFs exist there, return
         only those (avoids pulling in InforNexus / archive subfolders).
      2. If *root* has none, recurse into every subdirectory so files that
         were moved into a subfolder (e.g. a Chinese-named archive folder)
         are still found.
    """
    root_hits = [
        os.path.join(root, f) for f in os.listdir(root)
        if f.lower().endswith('.pdf') and f.lower().startswith(prefix)
    ]
    if root_hits:
        return sorted(root_hits)
    # Fallback: recursive search
    found = []
    for dirpath, _dirs, files in os.walk(root):
        if dirpath == root:
            continue  # already checked root above
        for f in files:
            if f.lower().endswith('.pdf') and f.lower().startswith(prefix):
                found.append(os.path.join(dirpath, f))
    return sorted(found)


# ── Parse all PDFs and refresh DB ────────────────────────────────────────────
store = POStore(DB_PATH)

pdf_paths = _find_vendor_pdfs(ROOT_DIR, _VENDOR_PREFIX)
if not pdf_paths:
    raise RuntimeError(f"No {_VENDOR_PREFIX.upper()}*.pdf found under {ROOT_DIR}")

print(f"Found {len(pdf_paths)} {_VENDOR_PREFIX.upper()}*.pdf under {ROOT_DIR}")

po_numbers = []
for fpath in pdf_paths:
    po = parse_pdf(fpath)
    pn = po.metadata.po_number or ''
    if not pn:
        print(f"  SKIP (no PO number): {os.path.basename(fpath)}")
        continue
    store.force_save(po)
    po_numbers.append(pn)
    print(f"  {pn}: style={po.metadata.style}  fob={po.metadata.unit_cost}"
          f"  sizes={len(po.size_rows)}  conf={po.metadata.parse_confidence}")

if not po_numbers:
    raise RuntimeError("No valid POs parsed — aborting.")

# ── Load from DB and generate Excel ──────────────────────────────────────────
df_meta  = store.list_pos()
df_meta  = df_meta[df_meta['po_number'].isin(po_numbers)].copy()
df_sizes = store.load_size_rows(po_numbers)

kl_bytes = generate_kl_format_excel(df_meta, df_sizes)
if not kl_bytes:
    raise RuntimeError("Excel generator returned empty — check size rows in DB.")

print()
issues = check_kl_excel(df_meta, df_sizes, kl_bytes)
if issues:
    raise RuntimeError("Consistency check failed — Excel not saved. Fix issues above.")

def _safe_write(path: str, data: bytes) -> str:
    """Write *data* to *path*; if locked, write to a versioned path instead."""
    try:
        with open(path, 'wb') as fh:
            fh.write(data)
        return path
    except PermissionError:
        base, ext = os.path.splitext(path)
        alt = f"{base}_new{ext}"
        print(f"  WARNING: {os.path.basename(path)} is locked — saving to {os.path.basename(alt)}")
        print(f"  (Close the original in Excel / Explorer, then rename manually.)")
        with open(alt, 'wb') as fh:
            fh.write(data)
        return alt


saved_path  = _safe_write(OUT_PATH, kl_bytes)
sz          = os.path.getsize(saved_path)
total_units = int(df_sizes['Units'].sum()) if not df_sizes.empty else 0
print(f"Saved {sz:,} bytes -> {saved_path}")
print(f"POs: {len(set(po_numbers))}  |  Total units: {total_units:,}")
