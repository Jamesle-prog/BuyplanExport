"""Fabric & washing-label composition lookup.

Source file:  AW26洗标成分确认-26.4.13确认.xlsx

Sheet 1  "AW26洗标确认"  — style-level mapping
  Col 1 : Supplier Article Number  (style_no)
  Col 2 : Sample picture           (DISPIMG formula → image_id)
  Col 3 : 面料号                   (HHN fabric nos, possibly multi-line)
  Col 4 : 面料成分（即洗标成分）   (washing label composition)

Sheet 2  "面料信息"  — fabric-level detail
  Col 1 : HHN fabric number  (may be alias/variant, use col 2 for normalised)
  Col 2 : Normalised HHN fabric number
  Col 4 : Fabric composition (as tested)
  Col 5 : Confirmed composition
  Col 6 : Weight (g/m²)
  Col 7 : Width  (cm)
  Col 8 : Composite string  "HHN-xxx|comp|weight|width"

Lookup keys:
  style_no          → {image_id, composition, fabric_parts[]}
  hhn_fabric_no     → {composition, weight_gsm, width_cm}
"""
from __future__ import annotations

import re
import openpyxl


def _norm_key(s) -> str:
    """Strip whitespace, remove non-alphanumeric chars, uppercase — for all key lookups."""
    return re.sub(r'[^A-Za-z0-9]', '', str(s).strip()).upper()

_DISPIMG_RE = re.compile(r'DISPIMG\("(ID_[0-9A-Fa-f]+)"', re.IGNORECASE)
# HHN codes are ASCII: HHN-<letters/digits, hyphen-separated> (HHN-001,
# HHN-JA-01715, HHN-2026-001, HHN-DB-YS240782). Restricting the class to
# [A-Za-z0-9-] stops the match at the first CJK char / comma / paren so
# trailing descriptions ("HHN-JA-01715，300克/平方米", "HHN-MS-01794(里布)")
# no longer get swallowed into the code — a bare \S+ captured all of it.
_HHN_RE     = re.compile(r'HHN-[A-Za-z0-9-]+', re.IGNORECASE)


def _v(val) -> str:
    return "" if val is None else str(val).strip()


def _int_or_zero(val) -> int:
    """Best-effort integer from a spreadsheet cell. Weight/width columns often
    carry free-text ("300g", "150cm", "TBC", "-") that would crash a bare
    ``int(float(...))`` and take the whole fabric lookup down with it. Pull the
    leading numeric run; anything non-numeric becomes 0."""
    s = _v(val)
    if not s or s.lower() == "nan":
        return 0
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return int(float(m.group())) if m else 0


def _dispimg_id(val) -> str:
    m = _DISPIMG_RE.search(_v(val))
    return m.group(1) if m else ""


def _extract_hhn_numbers(cell_val) -> list[tuple[str, str]]:
    """
    Parse potentially multi-line fabric cell into [(body_part, hhn_no), ...].

    Examples:
      "HHN-JA-01715"           → [("", "HHN-JA-01715")]
      "大身HHN-JA-01715\n网布HHN-MS-01794"
                               → [("大身", "HHN-JA-01715"), ("网布", "HHN-MS-01794")]
      "大身：HHN-JA-01715，300克..."
                               → [("大身", "HHN-JA-01715")]
    """
    raw = _v(cell_val)
    if not raw:
        return []

    results = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Find all HHN codes in this line
        hhn_matches = list(_HHN_RE.finditer(line))
        if not hhn_matches:
            continue
        for hm in hhn_matches:
            hhn_no  = hm.group(0).strip("，, ：:")
            # Extract body-part prefix (text before the HHN code)
            prefix = line[:hm.start()].strip()
            prefix = re.sub(r'[：:,，\s]+$', '', prefix)   # clean trailing delimiters
            results.append((prefix, hhn_no))
    return results


class FabricLookup:
    """
    Lazy-loading fabric and composition lookup.

    Parameters
    ----------
    path : str
        Full path to the 洗标成分确认 .xlsx file.
    """

    def __init__(self, path: str):
        self._path  = path
        # style_no → {"image_id": str, "composition": str,
        #              "fabric_parts": [(body_part, hhn_no), ...]}
        self._by_style: dict[str, dict] = {}
        # hhn_no → {"composition": str, "weight_gsm": int, "width_cm": int,
        #            "composite": str}
        self._by_fabric: dict[str, dict] = {}
        self._loaded = False

    # ── Lazy load ─────────────────────────────────────────────────────────────

    def _load(self):
        if self._loaded:
            return

        import pandas as pd

        # Read all sheets at once with pandas — faster than openpyxl streaming.
        # A corrupt / password-protected / missing file leaves the lookup
        # empty rather than crashing every buy-plan that consumes it.
        try:
            all_sheets = pd.read_excel(
                self._path, sheet_name=None,
                header=None, dtype=str, engine="openpyxl"
            )
        except Exception as exc:
            import warnings
            warnings.warn(f"[fabric_lookup] could not read {self._path}: {exc!r}")
            self._loaded = True
            return
        sheet_names = list(all_sheets.keys())

        # ── Sheet 1: style → fabric mapping ──────────────────────────────────
        # Pre-extract each needed column once (plain value arrays) — iterrows()
        # plus per-field .iloc is far slower on large files (same pattern as
        # config_sku_lookup._build_map).
        df1 = all_sheets[sheet_names[0]].fillna("")
        rows1 = df1.iloc[1:]
        cols1 = [rows1.iloc[:, ci].values if ci < df1.shape[1] else None
                 for ci in range(4)]

        def _cv1(i, ci):
            a = cols1[ci]
            return a[i] if a is not None else None

        for i in range(len(rows1)):
            style = _norm_key(_v(_cv1(i, 0)))
            if not style:
                continue
            img_id      = _dispimg_id(_cv1(i, 1))
            fabric_cell = _cv1(i, 2)
            comp        = _v(_cv1(i, 3))

            parts = _extract_hhn_numbers(fabric_cell)
            if style in self._by_style:
                existing_parts = self._by_style[style]["fabric_parts"]
                for p in parts:
                    if p not in existing_parts:
                        existing_parts.append(p)
                if not self._by_style[style]["composition"] and comp:
                    self._by_style[style]["composition"] = comp
            else:
                self._by_style[style] = {
                    "image_id":    img_id,
                    "composition": comp,
                    "fabric_parts": parts,
                }

        # ── Sheet 2: fabric detail ────────────────────────────────────────────
        if len(sheet_names) > 1:
            df2 = all_sheets[sheet_names[1]].fillna("")
            rows2 = df2.iloc[1:]
            cols2 = [rows2.iloc[:, ci].values if ci < df2.shape[1] else None
                     for ci in range(8)]

            def _cv2(i, ci):
                a = cols2[ci]
                return a[i] if a is not None else None

            for i in range(len(rows2)):
                hhn_raw  = _v(_cv2(i, 0))
                hhn_norm = _v(_cv2(i, 1)) or hhn_raw
                if not hhn_norm:
                    continue
                comp_tested    = _v(_cv2(i, 3))
                comp_confirmed = _v(_cv2(i, 4))
                weight    = _cv2(i, 5)
                width     = _cv2(i, 6)
                composite = _v(_cv2(i, 7))

                record = {
                    "composition":  comp_confirmed or comp_tested,
                    "weight_gsm":   _int_or_zero(weight),
                    "width_cm":     _int_or_zero(width),
                    "composite":    composite,
                }
                self._by_fabric[hhn_norm] = record
                if hhn_raw and hhn_raw != hhn_norm:
                    self._by_fabric[hhn_raw] = record

        self._loaded = True

    # ── Public API ────────────────────────────────────────────────────────────

    def _key(self, style_no: str) -> str:
        return _norm_key(style_no)

    def get_style_info(self, style_no: str) -> dict | None:
        """
        Return style-level info dict or None.

        Keys: image_id, composition, fabric_parts [(body_part, hhn_no), ...]
        """
        self._load()
        return self._by_style.get(self._key(style_no))

    def get_composition(self, style_no: str) -> str:
        """Return washing-label composition string for a style."""
        self._load()
        info = self._by_style.get(self._key(style_no))
        return info["composition"] if info else ""

    def get_image_id(self, style_no: str) -> str:
        """Return DISPIMG image ID for the style sample picture."""
        self._load()
        info = self._by_style.get(self._key(style_no))
        return info["image_id"] if info else ""

    def get_fabric_parts(self, style_no: str) -> list[tuple[str, str]]:
        """
        Return [(body_part, hhn_no), ...] for a style.
        e.g. [("大身", "HHN-JA-01715"), ("网布", "HHN-MS-01794")]
        """
        self._load()
        info = self._by_style.get(self._key(style_no))
        return info["fabric_parts"] if info else []

    def get_fabric_detail(self, hhn_no: str) -> dict | None:
        """
        Return fabric-level detail (composition, weight, width) for a HHN no.
        """
        self._load()
        return self._by_fabric.get(hhn_no.strip())

    def get_all_styles(self) -> list[str]:
        self._load()
        return list(self._by_style.keys())

    def __len__(self) -> int:
        self._load()
        return len(self._by_style)
