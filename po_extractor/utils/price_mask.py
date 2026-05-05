"""Mask prices in PDF and Excel files.

PDF: uses PyMuPDF redaction — scans every page for tokens that look like
prices (digits.digits) and covers them with white-filled redaction rectangles.

Excel: uses openpyxl — detects columns whose headers contain price-related
keywords and replaces numeric cell values with "***".

Output is saved to output_dir/masked/<original_filename>.
"""
import os
import re

_PRICE_RE = re.compile(r'^\d+\.\d{2}$')

# Header keywords that identify "price" columns in Excel sheets
_PRICE_KEYWORDS = ("fob", "cost", "price", "usd", "amount", "total cost", "unit price")


# ---------------------------------------------------------------------------
# PDF masking
# ---------------------------------------------------------------------------

def mask_prices(pdf_path: str, output_dir: str) -> str:
    """Write a price-redacted copy of a PDF; return the output path."""
    import fitz  # PyMuPDF — loaded lazily so Excel-only callers don't need it

    masked_dir = os.path.join(output_dir, "masked")
    os.makedirs(masked_dir, exist_ok=True)
    out_path = os.path.join(masked_dir, os.path.basename(pdf_path))

    doc = fitz.open(pdf_path)
    try:
        for page in doc:
            for word in page.get_text("words"):
                token = word[4]
                if _PRICE_RE.match(token):
                    rect = fitz.Rect(word[:4])
                    page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
        doc.save(out_path)
    finally:
        doc.close()

    return out_path


def mask_prices_batch(pdf_paths: list[str], output_dir: str) -> list[str]:
    """Mask prices in a list of PDFs; return output paths."""
    results = []
    for path in pdf_paths:
        try:
            out = mask_prices(path, output_dir)
            results.append(out)
            print(f"masked: {out}")
        except Exception as e:
            print(f"  mask FAILED: {path} ({e})")
    return results


# ---------------------------------------------------------------------------
# Excel masking
# ---------------------------------------------------------------------------

def mask_prices_excel(xlsx_path: str, output_dir: str,
                      price_keywords: tuple = _PRICE_KEYWORDS) -> str:
    """Write a price-redacted copy of an xlsx; return the output path.

    Detection strategy
    ------------------
    * Scans the first 25 rows of each sheet for cells whose text contains
      any of *price_keywords* (case-insensitive).
    * All columns that matched are treated as price columns.
    * In those columns, every numeric cell value (int / float) is replaced
      with the literal string ``"***"``.  String cells (headers) are left
      untouched so column headers remain readable.
    """
    import openpyxl

    masked_dir = os.path.join(output_dir, "masked")
    os.makedirs(masked_dir, exist_ok=True)
    out_path = os.path.join(masked_dir, os.path.basename(xlsx_path))

    wb = openpyxl.load_workbook(xlsx_path)
    for ws in wb.worksheets:
        if ws.max_row is None or ws.max_column is None:
            continue

        # ── Detect price columns from first 25 rows ───────────────────────────
        price_cols: set[int] = set()
        scan_rows = min(25, ws.max_row)
        for r in range(1, scan_rows + 1):
            for c in range(1, ws.max_column + 1):
                val = ws.cell(row=r, column=c).value
                if val is None:
                    continue
                val_lower = str(val).lower().replace("\n", " ")
                if any(kw in val_lower for kw in price_keywords):
                    price_cols.add(c)

        if not price_cols:
            continue

        # ── Redact numeric values in price columns ────────────────────────────
        for r in range(1, ws.max_row + 1):
            for c in price_cols:
                cell = ws.cell(row=r, column=c)
                if cell.value is None:
                    continue
                if isinstance(cell.value, (int, float)):
                    cell.value = "***"
                else:
                    # String: try to parse as number (e.g. "12.50")
                    try:
                        float(str(cell.value).replace(",", "").strip())
                        cell.value = "***"
                    except (ValueError, TypeError):
                        pass   # leave header text and non-numeric strings

    wb.save(out_path)
    wb.close()
    return out_path


def mask_prices_excel_batch(xlsx_paths: list[str], output_dir: str) -> list[str]:
    """Mask prices in a list of Excel files; return output paths."""
    results = []
    for path in xlsx_paths:
        try:
            out = mask_prices_excel(path, output_dir)
            results.append(out)
            print(f"masked: {out}")
        except Exception as e:
            print(f"  mask FAILED: {path} ({e})")
    return results
