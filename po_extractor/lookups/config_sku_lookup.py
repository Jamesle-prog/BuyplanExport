"""Config SKU lookup built from the Zalando Purchase Order report.

Uses pandas for fast reading of large xlsx files (single-pass, C-backed).

Matches a combination of:
    Purchase Order Number        → item.zalando_po
    Main Supplier Color Description (shown as "Color name") → item.color_name
    Brand                        → item.brand
    Main Supplier Config SKU     (shown as "Style No.")     → item.style

to extract the "Config SKU" value for each row, then populates item.config_sku.
"""
from __future__ import annotations

import re
def _norm_key(s) -> str:
    """Strip whitespace, remove non-alphanumeric chars, uppercase — for all key lookups."""
    return re.sub(r'[^A-Za-z0-9]', '', str(s).strip()).upper()


def _v(val) -> str:
    return "" if (val is None or str(val).strip().lower() in ("nan", "none")) else str(val).strip()


def _is_nontrivial(val: str) -> bool:
    return bool(val) and val.lower() not in ("none", "n/a", "-", "0")


_COL_ALIASES = {
    "po":     {"purchase order number"},
    "color":  {"main supplier color description", "color name", "colour name",
               "color description"},
    "brand":  {"brand"},
    "style":  {"main supplier config sku", "style no.", "style no", "style number",
               "config sku number"},
    "csku":   {"config sku"},
}


class ConfigSKULookup:
    """Fast Config SKU lookup using pandas for large Zalando PO report files."""

    def __init__(self, path: str):
        self._path = path
        self._map: dict[tuple[str, str, str, str], str] = {}
        self.conflicts: list[dict] = []
        self._loaded = False

    def _load(self):
        if self._loaded:
            return

        import pandas as pd

        # Read entire file in one pass — pandas is dramatically faster than
        # openpyxl for large files (single C-backed decompression + parse).
        df = pd.read_excel(self._path, header=None, dtype=str, engine="openpyxl")
        df = df.fillna("")

        # Find header row in first 10 rows
        col_po = col_color = col_brand = col_style = col_csku = None
        hrow_idx = None

        for ri in range(min(10, len(df))):
            row = df.iloc[ri]
            found_any = False
            for ci, val in enumerate(row):
                raw = _v(val).lower()
                if raw in _COL_ALIASES["po"]:
                    col_po = ci; found_any = True
                elif raw in _COL_ALIASES["color"]:
                    col_color = ci; found_any = True
                elif raw in _COL_ALIASES["brand"]:
                    col_brand = ci; found_any = True
                elif raw in _COL_ALIASES["style"]:
                    col_style = ci; found_any = True
                elif raw in _COL_ALIASES["csku"]:
                    col_csku = ci; found_any = True
            if found_any and col_csku is not None:
                hrow_idx = ri
                break

        if hrow_idx is None or col_csku is None:
            raise ValueError(
                "Could not find required columns in the Config SKU file. "
                "Expected: 'Purchase Order Number', 'Main Supplier Color Description', "
                "'Brand', 'Main Supplier Config SKU', 'Config SKU'."
            )

        data = df.iloc[hrow_idx + 1:].reset_index(drop=True)

        # Extract columns as numpy arrays — vectorized, no Python row loop overhead
        def _col_arr(idx):
            if idx is not None and idx < len(data.columns):
                return data.iloc[:, idx].values
            return [""] * len(data)

        csku_arr  = _col_arr(col_csku)
        po_arr    = _col_arr(col_po)
        color_arr = _col_arr(col_color)
        brand_arr = _col_arr(col_brand)
        style_arr = _col_arr(col_style)

        raw_map: dict[tuple, list[str]] = {}

        for i in range(len(data)):
            csku = _v(csku_arr[i])
            if not csku:
                continue
            po    = _v(po_arr[i])
            color = _v(color_arr[i])
            brand = _v(brand_arr[i])
            style = _v(style_arr[i])
            if not (po or style):
                continue
            key = (_norm_key(po), _norm_key(color), _norm_key(brand), _norm_key(style))
            raw_map.setdefault(key, []).append(csku)

        # Build final map; flag conflicts
        for key, skus in raw_map.items():
            nontrivial = [s for s in skus if _is_nontrivial(s)]
            unique = list(dict.fromkeys(nontrivial))
            if len(unique) > 1:
                po, color, brand, style = key
                self.conflicts.append({
                    "po": po, "color": color,
                    "brand": brand, "style": style,
                    "values": unique,
                })
            self._map[key] = unique[0] if unique else (skus[0] if skus else "")

        self._loaded = True

    def get_config_sku(self, po: str, color: str, brand: str, style: str) -> str:
        self._load()
        key = (_norm_key(po), _norm_key(color), _norm_key(brand), _norm_key(style))
        return self._map.get(key, "")

    def enrich_item(self, item) -> str:
        return self.get_config_sku(
            item.zalando_po or "",
            item.color_name or "",
            item.brand or "",
            item.style or "",
        )

    def __len__(self) -> int:
        self._load()
        return len(self._map)
