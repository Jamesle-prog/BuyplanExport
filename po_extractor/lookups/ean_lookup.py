"""EAN/barcode lookup built from the Zalando EAN export file.

File structure
--------------
Row 1  : report title ("Purchase Order Report_Sky East(1)")
Row 2  : empty
Row 3  : column headers
Row 4+ : data rows

Key columns (auto-detected by name, with positional fallback):
  Purchase Order Number   → zalando_po
  Main Supplier Config SKU → style_no  (join key)
  EU size                 → size
  EAN                     → ean_code
  Qty Ordered …           → qty
  Delivery Date From      → delivery_date

Primary lookup key: (style_no, size) → EAN
Secondary key:      (zalando_po, style_no, size) → EAN  (for cross-check)
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

import openpyxl


def _norm_key(s) -> str:
    """Strip whitespace, remove non-alphanumeric chars, uppercase — for all key lookups."""
    return re.sub(r'[^A-Za-z0-9]', '', str(s).strip()).upper()


class EANLookup:
    """
    Lazy-loading EAN lookup table.

    Parameters
    ----------
    path : str
        Path to the EAN xlsx file.  The filename may contain a non-breaking
        space (U+00A0) — pass the exact OS path from os.listdir().
    """

    def __init__(self, path: str):
        self._path = path
        self._by_style_size: dict[tuple[str, str], str]  = {}   # (style, size) → ean
        self._by_po_style_size: dict[tuple[str, str, str], str] = {}  # (po, style, size) → ean
        self._qty: dict[tuple[str, str, str], int] = {}          # (po, style, size) → qty
        self._loaded = False

    # ── Lazy load ─────────────────────────────────────────────────────────────

    def _load(self):
        if self._loaded:
            return

        import pandas as pd

        # Read entire file with pandas — single-pass, C-backed. A corrupt /
        # password-protected / missing reference file must leave the lookup
        # empty (harmless misses), never crash every caller that uses it.
        try:
            df = pd.read_excel(self._path, header=None, dtype=str,
                               engine="openpyxl")
        except Exception as exc:
            import warnings
            warnings.warn(f"[ean_lookup] could not read {self._path}: {exc!r}")
            self._loaded = True
            return
        df = df.fillna("")

        hrow_idx = 2  # default (0-based)
        col_po = col_style = col_size = col_ean = col_qty = col_date = None

        for ri in range(min(10, len(df))):
            row = df.iloc[ri]
            found = False
            for ci, val in enumerate(row):
                v = str(val).strip()
                vl = v.lower()
                if vl == "ean":                              col_ean   = ci; found = True
                elif vl == "main supplier config sku":       col_style = ci; found = True
                elif vl == "eu size":                        col_size  = ci; found = True
                elif vl == "purchase order number":          col_po    = ci
                elif "qty ordered" in vl:                    col_qty   = ci
                elif vl == "delivery date from":             col_date  = ci
            if found:
                hrow_idx = ri
                break

        # Positional fallbacks (convert to 0-based).  Falling back means NO
        # recognised header was found in the first 10 rows — on a
        # differently-shaped export this silently ingests whatever sits in
        # these columns as EAN barcodes, so make it loud.
        if col_ean is None:
            import warnings
            warnings.warn(
                f"[ean_lookup] no 'EAN' header found in the first 10 rows of "
                f"{self._path!r} — falling back to fixed column positions; "
                f"verify the file layout if lookups return wrong barcodes"
            )
        col_po    = col_po    if col_po    is not None else 8
        col_style = col_style if col_style is not None else 11
        col_size  = col_size  if col_size  is not None else 12
        col_ean   = col_ean   if col_ean   is not None else 16
        col_qty   = col_qty   if col_qty   is not None else 18

        # Pre-extract each needed column once (plain value arrays) — iterrows()
        # plus per-field .iloc is far slower on large files (same pattern as
        # config_sku_lookup._build_map).
        data   = df.iloc[hrow_idx + 1:]
        n_cols = df.shape[1]

        def _col_arr(ci):
            return data.iloc[:, ci].values if ci < n_cols else None

        ean_arr   = _col_arr(col_ean)
        po_arr    = _col_arr(col_po)
        style_arr = _col_arr(col_style)
        size_arr  = _col_arr(col_size)
        qty_arr   = _col_arr(col_qty)

        def _cv(arr, i):
            return str(arr[i]).strip() if arr is not None else ""

        for i in range(len(data)):
            ean = _cv(ean_arr, i)
            if not ean or ean in ("nan", "None", "EAN"):
                continue

            po    = _norm_key(_cv(po_arr, i))
            style = _norm_key(_cv(style_arr, i))
            size  = _cv(size_arr, i).strip().upper()
            qty_s = _cv(qty_arr, i)
            try:
                qty = int(float(qty_s)) if qty_s and qty_s != "nan" else 0
            except (ValueError, TypeError):
                qty = 0

            if style and size:
                self._by_style_size.setdefault((style, size), ean)
            if po and style and size:
                key3 = (po, style, size)
                self._by_po_style_size.setdefault(key3, ean)
                self._qty[key3] = qty

        self._loaded = True

    # ── Public API ────────────────────────────────────────────────────────────

    def get_ean(self, style_no: str, size: str,
                po_number: str | None = None) -> str:
        """
        Return EAN for a style+size combination.

        If po_number is given, tries the exact (po, style, size) key first,
        then falls back to (style, size) across all POs.
        """
        self._load()
        style_no = _norm_key(style_no)
        size = size.strip().upper()
        if po_number:
            ean = self._by_po_style_size.get((_norm_key(po_number), style_no, size))
            if ean:
                return ean
        return self._by_style_size.get((style_no, size), "")

    def get_qty(self, po_number: str, style_no: str, size: str) -> int:
        """Return ordered quantity for (po, style, size)."""
        self._load()
        return self._qty.get((_norm_key(po_number), _norm_key(style_no), size.strip().upper()), 0)

    def enrich_item(self, item) -> dict[str, str]:
        """
        Return a dict  {size: ean, …}  for all sizes of this item.

        item  must have .zalando_po, .style, and .sizes (dict).
        """
        self._load()
        result = {}
        for sz in (item.sizes or {}).keys():
            ean = self.get_ean(item.style, sz, item.zalando_po)
            if ean:
                result[sz] = ean
        return result

    def get_all_for_style(self, style_no: str) -> dict[str, str]:
        """Return {size: ean} for all known sizes of a style."""
        self._load()
        nk = _norm_key(style_no)
        return {
            sz: ean
            for (s, sz), ean in self._by_style_size.items()
            if s == nk
        }

    def __len__(self) -> int:
        self._load()
        return len(self._by_style_size)
