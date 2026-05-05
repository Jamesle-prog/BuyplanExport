"""Production progress lookup from 大货进度表--Angel 2026.xlsx.

Sheet  "2026 Zalando"  — the master production tracker
  Col 1  : 序号        item number
  Col 2  : 合同号      HHN contract number   ← what we need
  Col 3  : 所在PO      Sky East PC No.
  Col 4  : IMAGE       DISPIMG formula → style photo
  Col 5  : 款式        Style No.              (join key)
  Col 7  : 颜色        Color description (e.g. "52# NAVY")
  Col 10 : PO离厂日期  Ex-factory date
  Col 11 : 数量        Quantity
  Col 12 : PO#         Zalando PO number
  Col 13 : BRAND
  Col 14 : FABRICDETAIL

Lookup keys:
  (style_no, color_rough)  → HHN contract no., image_id, ex_fty, zalando_po
  style_no                 → list of all colour rows
"""
from __future__ import annotations

import re
from datetime import datetime
import openpyxl


def _norm_key(s) -> str:
    """Strip whitespace, remove non-alphanumeric chars, uppercase — for all key lookups."""
    return re.sub(r'[^A-Za-z0-9]', '', str(s).strip()).upper()

_DISPIMG_RE = re.compile(r'DISPIMG\("(ID_[0-9A-Fa-f]+)"', re.IGNORECASE)


def _v(val) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    return str(val).strip()


def _dispimg_id(val) -> str:
    m = _DISPIMG_RE.search(_v(val))
    return m.group(1) if m else ""


def _normalise_color(color: str) -> str:
    """
    Strip numeric colour code prefix so "52# NAVY" → "NAVY",
    "2# BLACK" → "BLACK",  "BLACK" → "BLACK".
    """
    c = color.strip().upper()
    c = re.sub(r'^\d+#\s*', '', c)   # remove leading "52# "
    return c.strip()


class ProgressLookup:
    """
    Lazy-loading production progress lookup.

    Parameters
    ----------
    path : str
        Full path to 大货进度表 xlsx file.
    sheet_name : str
        Sheet to read (default "2026 Zalando ").
    """

    def __init__(self, path: str, sheet_name: str | None = None):
        self._path        = path
        self._sheet_name  = sheet_name   # None = auto-detect first matching sheet
        # (style, normalised_color) → record dict
        self._by_style_color: dict[tuple[str, str], dict] = {}
        # style → [record, ...]   (all colours)
        self._by_style: dict[str, list[dict]] = {}
        self._loaded = False

    # ── Column map helpers ─────────────────────────────────────────────────────

    _COL_NAMES = {
        "seq":        {"序号"},
        "contract_no":{"合同号"},
        "pc_no":      {"所在po", "所在po"},
        "image":      {"image"},
        "style":      {"款式"},
        "color":      {"颜色"},
        "label_color":{"主标颜色"},
        "ex_fty":     {"po离厂日期"},
        "qty":        {"数量"},
        "zalando_po": {"po#"},
        "brand":      {"brand"},
        "fabric":     {"fabricdetail"},
    }
    _COL_DEFAULTS = {
        "seq": 1, "contract_no": 2, "pc_no": 3, "image": 4,
        "style": 5, "color": 7, "label_color": 8, "ex_fty": 10,
        "qty": 11, "zalando_po": 12, "brand": 13, "fabric": 14,
    }

    def _map_cols(self, ws) -> dict[str, int]:
        col_map = {}
        # Read only header row via iter_rows (safe in read_only mode)
        for row_vals in ws.iter_rows(min_row=1, max_row=1, values_only=True):
            for ci, val in enumerate(row_vals, start=1):
                raw = _v(val).lower().strip()
                for key, names in self._COL_NAMES.items():
                    if raw in names and key not in col_map:
                        col_map[key] = ci
                        break
        for k, v in self._COL_DEFAULTS.items():
            col_map.setdefault(k, v)
        return col_map

    # ── Lazy load ─────────────────────────────────────────────────────────────

    def _load(self):
        if self._loaded:
            return

        import pandas as pd
        import openpyxl as _opxl

        # Identify the target sheet name first (openpyxl just for sheet list)
        wb_meta = _opxl.load_workbook(self._path, read_only=True, data_only=True)
        sheet_name = None
        if self._sheet_name and self._sheet_name in wb_meta.sheetnames:
            sheet_name = self._sheet_name
        else:
            for name in wb_meta.sheetnames:
                if "zalando" in name.lower() or "2026" in name.lower():
                    sheet_name = name
                    break
            if sheet_name is None:
                sheet_name = wb_meta.sheetnames[0]
        wb_meta.close()

        # Read with pandas — single-pass, C-backed, much faster for large files
        df = pd.read_excel(
            self._path, sheet_name=sheet_name,
            header=None, dtype=str, engine="openpyxl"
        )
        df = df.fillna("")

        # Map column names from header row (row 0)
        col: dict[str, int] = {}
        for ci, val in enumerate(df.iloc[0]):
            raw = _v(val).lower().strip()
            for key, names in self._COL_NAMES.items():
                if raw in names and key not in col:
                    col[key] = ci
                    break
        for k, v in self._COL_DEFAULTS.items():
            col.setdefault(k, v - 1)  # convert 1-based default to 0-based

        def _cv(row, key):
            c = col.get(key)
            if c is not None and c < len(row):
                return row.iloc[c]
            return None

        # Iterate data rows (skip header)
        for _, row in df.iloc[1:].iterrows():
            style = _norm_key(_v(_cv(row, "style")))
            if not style:
                continue
            seq_raw = _cv(row, "seq")
            try:
                int(float(str(seq_raw)))
            except (ValueError, TypeError):
                continue

            color_raw = _v(_cv(row, "color"))
            record = {
                "contract_no": _v(_cv(row, "contract_no")),
                "pc_no":       _v(_cv(row, "pc_no")),
                "image_id":    _dispimg_id(_cv(row, "image")),
                "style":       style,
                "color":       color_raw,
                "color_norm":  _normalise_color(color_raw),
                "label_color": _v(_cv(row, "label_color")),
                "ex_fty":      _v(_cv(row, "ex_fty")),
                "qty":         _cv(row, "qty"),
                "zalando_po":  _v(_cv(row, "zalando_po")),
                "brand":       _v(_cv(row, "brand")),
                "fabric":      _v(_cv(row, "fabric")),
            }

            key = (style, record["color_norm"])
            self._by_style_color.setdefault(key, record)
            self._by_style.setdefault(style, []).append(record)

        self._loaded = True

    # ── Public API ────────────────────────────────────────────────────────────

    @staticmethod
    def _skey(style_no: str) -> str:
        return _norm_key(style_no)

    def get_contract_no(self, style_no: str, color: str = "") -> str:
        """
        Return HHN 合同号 for a style+colour.

        color can be raw ("52# NAVY") or normalised ("NAVY").
        If colour is blank or not found, falls back to first colour for style.
        """
        self._load()
        s = self._skey(style_no)
        if color:
            rec = self._by_style_color.get((s, _normalise_color(color)))
            if rec:
                return rec["contract_no"]
        rows = self._by_style.get(s, [])
        return rows[0]["contract_no"] if rows else ""

    def get_image_id(self, style_no: str, color: str = "") -> str:
        """Return DISPIMG image ID from the progress table."""
        self._load()
        s = self._skey(style_no)
        if color:
            rec = self._by_style_color.get((s, _normalise_color(color)))
            if rec and rec["image_id"]:
                return rec["image_id"]
        rows = self._by_style.get(s, [])
        for r in rows:
            if r["image_id"]:
                return r["image_id"]
        return ""

    def get_record(self, style_no: str, color: str = "") -> dict | None:
        """Return the full record dict or None."""
        self._load()
        s = self._skey(style_no)
        if color:
            rec = self._by_style_color.get((s, _normalise_color(color)))
            if rec:
                return rec
        rows = self._by_style.get(s, [])
        return rows[0] if rows else None

    def get_all_for_style(self, style_no: str) -> list[dict]:
        """Return all colour rows for a style."""
        self._load()
        return self._by_style.get(self._skey(style_no), [])

    def all_styles(self) -> list[str]:
        self._load()
        return list(self._by_style.keys())

    def __len__(self) -> int:
        self._load()
        return len(self._by_style_color)
