"""House cleanup for cut-plan output — the post-process the cutting room expects.

This replaces the Excel macro that was run by hand on every cut plan
(``cleanCuttingPlanOutput`` = ``translate`` + ``RemovePathAndExtension``):

* English labels become the Chinese the cutting room reads.
* Marker cells arrive as full Windows paths from the marker software
  (``D:\\Markers\\SS26\\ABC-1234.mrk``); only the marker name is wanted.

Both passes run over **every** cell, exactly as the macro did — the labels are
not the only thing that needs it, since marker paths live in data cells.

Faithfulness notes (the macro's behaviour is deliberately preserved):

* Replacements are **case-insensitive substring** matches (``LookAt:=xlPart``),
  so ``"Marker Length,cm"`` becomes ``"版长,cm"`` and ``"N Markers"`` becomes
  ``"N 版s"``. That is what the macro produced and what the cutting room is
  used to reading.
* Order matters and is preserved: ``Marker Length`` and ``Marker Ratio`` must
  be replaced **before** the bare ``Marker`` rule, or the short rule would
  consume the prefix and the specific labels would never match.
* Every replacement is Chinese and every search term is ASCII, so no rule can
  re-match an earlier rule's output — the sequence cannot cascade.
"""
from __future__ import annotations

import re
from typing import Any

# (search, replacement) — ORDER IS SIGNIFICANT, see module docstring.
TRANSLATIONS: list[tuple[str, str]] = [
    ("Plies number",  "层数"),
    ("Marker Length", "版长"),
    ("Colors",        "颜色"),
    ("Order",         "订单数"),
    ("Real",          "裁剪数"),
    ("Marker Ratio",  "裁剪配比"),
    ("Marker",        "版"),
    ("Fabric Length", "面料长度"),
    ("Fabric Weight", "面料重量"),
    # Added beyond the original macro. "Total cut length" MUST precede
    # "Cut Length" — the sheet has both, and the short rule would otherwise
    # leave the total reading "Total 裁剪长度".
    ("Total cut length", "总裁剪长度"),
    ("Cut Length",       "裁剪长度"),
    ("Material Cost",    "材料成本"),
]

_COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(re.escape(src), re.IGNORECASE), dst) for src, dst in TRANSLATIONS
]

MARKER_EXT = ".mrk"

_CJK = re.compile(r"[一-鿿]")


def has_chinese(text: str) -> bool:
    """True when *text* already contains a Chinese character."""
    return bool(_CJK.search(text))


def _norm_color(text: str) -> str:
    """Case/space-insensitive colour key — matches the colour store's own
    normalisation ("NAVY", "navy", " Navy " all collapse together)."""
    return " ".join(str(text).split()).casefold()


def build_color_map(lookup: dict, client: str = "") -> dict[str, str]:
    """Flatten the colour store's ``{(client, brand, en): cn}`` into
    ``{normalised_en: cn}`` for whole-cell colour replacement.

    A colour can be mapped differently per client/brand, so rows for *client*
    are applied last and win; everything else is a fallback. Blank Chinese
    names are skipped so a half-filled row can't blank a colour out.
    """
    out: dict[str, str] = {}
    for scope in (False, True):          # others first, then the client's own
        for key, cn in (lookup or {}).items():
            if not cn:
                continue
            row_client = key[0] if isinstance(key, tuple) and key else ""
            en = key[2] if isinstance(key, tuple) and len(key) > 2 else ""
            if not en:
                continue
            is_client = bool(client) and str(row_client) == client
            if is_client == scope:
                out[_norm_color(en)] = cn
    return out


def translate_text(text: str) -> str:
    """Apply the label replacements to *text* (case-insensitive, substring)."""
    for pattern, repl in _COMPILED:
        # lambda, not the raw string: a replacement is inserted literally so
        # backslashes/group refs in it can never be interpreted.
        text = pattern.sub(lambda _m, r=repl: r, text)
    return text


def strip_path_and_ext(text: str) -> str:
    """Reduce a marker path to its bare name.

    ``D:\\Markers\\SS26\\ABC-1234.mrk`` -> ``ABC-1234``. Keeps text without a
    path or extension untouched. The extension check is case-insensitive
    (the macro's was not — ``.MRK`` slipped through it).
    """
    if "\\" in text:
        text = text.rsplit("\\", 1)[-1]
    if text.lower().endswith(MARKER_EXT):
        text = text[: -len(MARKER_EXT)]
    return text


def clean_value(value: Any, color_map: dict[str, str] | None = None) -> Any:
    """Clean one cell value; non-text and formulas pass through untouched.

    When *color_map* is given, a cell whose **whole** value is a known English
    colour becomes its Chinese name from the PO colour data. Whole-cell only —
    a substring rule here would corrupt any text that merely contains a colour
    word. A colour that is already Chinese is left alone.
    """
    if not isinstance(value, str):
        return value
    if value.startswith("="):        # never rewrite a formula
        return value
    if color_map and not has_chinese(value):
        cn = color_map.get(_norm_color(value))
        if cn:
            return cn                # a colour cell is only ever the colour
    return strip_path_and_ext(translate_text(value))


def clean_worksheet(ws, color_map: dict[str, str] | None = None) -> int:
    """Clean every cell of *ws* in place. Returns the number of cells changed."""
    changed = 0
    for row in ws.iter_rows():
        for cell in row:
            old = cell.value
            if not isinstance(old, str):
                continue
            new = clean_value(old, color_map)
            if new != old:
                cell.value = new
                changed += 1
    return changed


def clean_workbook(wb, color_map: dict[str, str] | None = None) -> int:
    """Clean every worksheet of *wb* in place. Returns total cells changed."""
    return sum(clean_worksheet(ws, color_map) for ws in wb.worksheets)
