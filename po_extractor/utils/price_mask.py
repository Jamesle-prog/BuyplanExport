"""Mask prices in PDF and Excel files.

PDF: uses PyMuPDF redaction — scans every page for tokens that look like
prices (digits.digits) and covers them with white-filled redaction rectangles.

Excel: uses openpyxl — detects columns whose headers contain price-related
keywords and replaces numeric cell values with "***".

Output is saved to output_dir/masked/<original_filename>.
"""
import os
import re

# A PDF token counts as a price when it is a decimal amount with exactly two
# fraction digits, optionally led by a currency symbol and using comma
# thousands separators. The two-decimal requirement keeps this conservative —
# it won't grab bare integers (quantities, UPCs, PO numbers).
#   matches: 4.17 · 69.00 · 1,234.00 · 12,345.67 · $4.17 · €1,000.00 · 45.00%? (no)
_PRICE_RE = re.compile(r'^[$£€¥]?\d[\d,]*\.\d{2}$')

# Header keywords that identify "price" columns in Excel sheets. Any column
# whose header (first 25 rows) contains one of these has its NUMERIC cells
# masked — text cells (names, headers) are left intact, so broad keywords are
# safe. Covers the price/cost headers this system's own exports actually use
# (FOB, MSRP, unit/extended cost, line total, …) plus currency-symbol headers
# like "Line Total ($)".
_PRICE_KEYWORDS = (
    "fob", "cost", "price", "usd", "amount", "total cost", "unit price",
    "msrp", "srp", "rrp", "retail", "wholesale", "extended", "line total",
    "$", "€", "£", "¥",
)


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


def mask_prices_batch(pdf_paths: list[str], output_dir: str,
                      errors: list[str] | None = None) -> list[str]:
    """Mask prices in a list of PDFs; return output paths.

    Failures are appended to *errors* (if given) so UI callers can surface
    them — a console print is invisible in Streamlit and the file is just
    missing from the result.
    """
    results = []
    for path in pdf_paths:
        try:
            out = mask_prices(path, output_dir)
            results.append(out)
            print(f"masked: {out}")
        except Exception as e:
            msg = f"{os.path.basename(path)}: {e}"
            if errors is not None:
                errors.append(msg)
            print(f"  mask FAILED: {msg}")
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

    ext = os.path.splitext(xlsx_path)[1].lower()
    if ext == ".xls":
        # openpyxl cannot read the legacy binary format; failing loudly here
        # beats the old behavior (an exception swallowed into a console
        # print, with the file silently missing from the masked zip).
        raise ValueError(
            "legacy .xls files cannot be price-masked — re-save as .xlsx/.xlsm"
        )

    masked_dir = os.path.join(output_dir, "masked")
    os.makedirs(masked_dir, exist_ok=True)
    out_path = os.path.join(masked_dir, os.path.basename(xlsx_path))

    # keep_vba: without it a .xlsm is silently re-packaged as a plain xlsx
    # under the .xlsm name — Excel then refuses to open the output.
    wb = openpyxl.load_workbook(xlsx_path, keep_vba=(ext == ".xlsm"))
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
                    # String value in a price column: parse as a number after
                    # stripping currency symbols / thousands commas / spaces,
                    # so "$4.17", "1,234.00", "€1000" also mask. Header text and
                    # genuinely non-numeric strings fail the parse and stay.
                    cleaned = str(cell.value).translate(
                        {ord(ch): None for ch in "$£€¥, "}
                    ).strip()
                    try:
                        float(cleaned)
                        cell.value = "***"
                    except (ValueError, TypeError):
                        pass

    wb.save(out_path)
    wb.close()
    return out_path


def mask_prices_excel_batch(xlsx_paths: list[str], output_dir: str,
                            errors: list[str] | None = None) -> list[str]:
    """Mask prices in a list of Excel files; return output paths.

    Failures are appended to *errors* (if given) so UI callers can surface
    them — see mask_prices_batch.
    """
    results = []
    for path in xlsx_paths:
        try:
            out = mask_prices_excel(path, output_dir)
            results.append(out)
            print(f"masked: {out}")
        except Exception as e:
            msg = f"{os.path.basename(path)}: {e}"
            if errors is not None:
                errors.append(msg)
            print(f"  mask FAILED: {msg}")
    return results
