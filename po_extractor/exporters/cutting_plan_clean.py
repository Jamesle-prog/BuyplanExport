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
    # ── Block titles and fixed headings ──────────────────────────────────
    # These come FIRST because several contain a word a later rule also
    # matches ("Marker Definition" vs "Marker", "Total cut length" vs "Cut
    # Length", "Spreading Plies" vs "Spreading"). Longest/most specific wins
    # by running earlier — the same reason the original macro ordered its own
    # rules the way it did.
    ("Order demands",     "订单需求"),
    ("Marker Definition", "版定义"),
    ("Spreading Plies",   "铺布层数"),
    ("Total Efficiency",  "总利用率"),
    ("Total Quantity",    "总数量"),
    ("Total Tables",      "总台数"),
    ("Total Cost",        "总成本"),
    ("Average Length",    "平均版长"),
    ("Waste Limits, cm",  "损耗上限,cm"),
    ("Cut plan operator", "裁剪计划员"),
    ("Style file",        "款式文件"),
    ("Style name",        "款式名称"),
    ("Order name",        "订单名称"),
    ("N Markers",         "版数"),
    ("Min Plies",         "最少层数"),
    ("Max Plies",         "最多层数"),
    ("File Name",         "文件名"),
    ("Width, cm",         "幅宽,cm"),
    ("Length, cm",        "长度,cm"),
    ("Efficiency,%",      "利用率,%"),
    ("PO Style(s)",       "订单款号"),
    ("Spreading",         "铺布"),
    ("Solution",          "排版结果"),
    ("Material Cost",     "材料成本"),   # MUST precede the bare "Material"
    ("Material",          "面料"),
    ("Quantity",          "数量"),
    ("Sizes",             "尺码"),
    ("Client",            "客户"),
    ("Sum",               "合计"),
    ("Date",              "日期"),
    ("Time",              "时间"),

    # ── The original macro's own rules, in its order ─────────────────────
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


def build_reverse_color_map(lookup: dict) -> dict[str, str]:
    """``{normalised chinese: normalised english}`` across every client/brand.

    Used to recognise a Chinese colour the *plan* already carries so it can be
    compared against what the PO calls that colour.
    """
    out: dict[str, str] = {}
    for key, cn in (lookup or {}).items():
        if not cn:
            continue
        en = key[2] if isinstance(key, tuple) and len(key) > 2 else ""
        if en:
            out.setdefault(_norm_color(cn), _norm_color(en))
    return out


def find_color_conflicts(wb, color_map: dict[str, str],
                         reverse_map: dict[str, str]) -> list[dict]:
    """Report cells where the plan's own Chinese colour disagrees with the PO's.

    **Read-only — changes nothing.** A cut plan that already names a colour in
    Chinese may be using a different house spelling than the PO (e.g. the plan
    says 深蓝 where the PO says 藏青 for Navy). Those are surfaced for a human
    to decide on rather than silently rewritten.

    Returns one entry per distinct disagreement::

        {"plan_cn", "po_cn", "english", "sheet", "cell"}
    """
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if not isinstance(v, str) or not has_chinese(v):
                    continue
                key = _norm_color(v)
                en = reverse_map.get(key)
                if not en:
                    continue          # not a colour we know — leave it be
                po_cn = (color_map or {}).get(en)
                if not po_cn or _norm_color(po_cn) == key:
                    continue          # agrees, or the PO has no name for it
                sig = (key, _norm_color(po_cn))
                if sig in seen:
                    continue
                seen.add(sig)
                out.append({"plan_cn": v.strip(), "po_cn": po_cn,
                            "english": en, "sheet": ws.title,
                            "cell": cell.coordinate})
    return out


def clean_value(value: Any, color_map: dict[str, str] | None = None,
                cn_overrides: dict[str, str] | None = None) -> Any:
    """Clean one cell value; non-text and formulas pass through untouched.

    When *color_map* is given, a cell whose **whole** value is a known English
    colour becomes its Chinese name from the PO colour data. Whole-cell only —
    a substring rule here would corrupt any text that merely contains a colour
    word.

    A colour that is **already Chinese** is left alone unless *cn_overrides*
    maps it (``{normalised plan colour: replacement}``) — that only happens
    once the user has explicitly approved the change.
    """
    if not isinstance(value, str):
        return value
    if value.startswith("="):        # never rewrite a formula
        return value
    key = _norm_color(value)
    if cn_overrides:
        repl = cn_overrides.get(key)
        if repl:
            return repl              # user-approved colour rename
    if color_map and not has_chinese(value):
        cn = color_map.get(key)
        if cn:
            return cn                # a colour cell is only ever the colour
    return strip_path_and_ext(translate_text(value))


# Header rows the cutting room doesn't use. Dropped from the delivered copy
# only — the canonical sheet keeps them because parsers.cutting_plan reads
# Order name / Date / Time back out of it. Matched on the label in column A,
# before translation, so these are the English originals.
# Kept on the sheet: Date, Order name, Style file N, Cut plan operator, Client
# — the cutting room uses those to identify the plan.
HEADER_ROWS_DROPPED = (
    "output folder path",
)


def _is_dropped_header(label: str) -> bool:
    s = " ".join(str(label).split()).casefold()
    # "Style name 1", "Style name 2", … — the "Style file N" rows kept above
    # already carry the style, so this is a duplicate of it.
    return s in HEADER_ROWS_DROPPED or s.startswith("style name")


# Metric columns the cutting room doesn't use. Matched on the heading before
# translation, so these are the English originals as the marker software wrote
# them. The cost column also repeats the fabric length rather than a cost.
COLUMNS_DROPPED = ("cut length", "material cost")


def _is_dropped_column(label: str) -> bool:
    s = " ".join(str(label).split()).casefold()
    return any(s.startswith(h) for h in COLUMNS_DROPPED)


def blank_dropped_columns(ws) -> int:
    """Empty the unwanted metric columns wherever they appear. Returns cells cleared.

    **Clears cells; never deletes columns** — deleting one would drag every
    column to its right out from under its heading.

    These headings repeat once per marker block rather than sitting in a single
    header row, so each occurrence is handled on its own: the heading is
    cleared, then the figures directly beneath it, stopping at the first cell
    that isn't a number (one blank row is stepped over, which is what separates
    a block's value row from its 合计 row).
    """
    cleared = 0
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str) or not _is_dropped_column(cell.value):
                continue
            cell.value = None
            cleared += 1
            # Walk down clearing this column's figures. Blank rows are stepped
            # OVER, not treated as the end — the value row sits a few rows
            # below its heading, with empty rows between. The block ends at the
            # next text cell in the column, which is the next block's heading.
            for r in range(cell.row + 1, ws.max_row + 1):
                below = ws.cell(r, cell.column)
                if below.value is None:
                    continue
                if isinstance(below.value, str):
                    break
                below.value = None
                cleared += 1
    return cleared


def drop_header_rows(ws) -> int:
    """Blank the header rows the cutting room doesn't read. Returns the count.

    **Clears cells; never deletes rows.** Deleting a row pulls everything below
    it up one, which slid the marker blocks out from under their own headings
    and wrecked the layout. Emptying the cells leaves every other cell exactly
    where it was — the row is simply blank.

    Only scans the top of the sheet, so a data cell that happens to read "Date"
    further down is left alone.
    """
    limit = min(ws.max_row, 30)
    cleared = 0
    for r in range(1, limit + 1):
        if not _is_dropped_header(ws.cell(r, 1).value or ""):
            continue
        for c in range(1, ws.max_column + 1):
            if ws.cell(r, c).value is not None:
                ws.cell(r, c).value = None
        cleared += 1
    return cleared


def clean_worksheet(ws, color_map: dict[str, str] | None = None,
                    cn_overrides: dict[str, str] | None = None) -> int:
    """Clean every cell of *ws* in place. Returns the number of cells changed."""
    # Blank rows and columns FIRST, while the labels are still their English
    # originals — the matchers key on the English text.
    changed = drop_header_rows(ws) + blank_dropped_columns(ws)
    for row in ws.iter_rows():
        for cell in row:
            old = cell.value
            if not isinstance(old, str):
                continue
            new = clean_value(old, color_map, cn_overrides)
            if new != old:
                cell.value = new
                changed += 1
    return changed


def clean_workbook(wb, color_map: dict[str, str] | None = None,
                   cn_overrides: dict[str, str] | None = None) -> int:
    """Clean every worksheet of *wb* in place. Returns total cells changed."""
    return sum(clean_worksheet(ws, color_map, cn_overrides)
               for ws in wb.worksheets)


# ── working on an already-built workbook (the UI's approve-then-apply path) ──

def conflicts_from_bytes(data: bytes, color_map: dict[str, str],
                         reverse_map: dict[str, str]) -> list[dict]:
    """:func:`find_color_conflicts` against built .xlsx bytes."""
    import openpyxl
    from io import BytesIO
    return find_color_conflicts(openpyxl.load_workbook(BytesIO(data)),
                                color_map, reverse_map)


def apply_color_overrides(data: bytes, overrides: dict[str, str]) -> bytes:
    """Return *data* with approved colour renames applied.

    Re-cleans the finished workbook instead of rebuilding it — the overrides
    only ever affect the cleanup pass, so nothing else can shift.
    """
    import openpyxl
    from io import BytesIO
    wb = openpyxl.load_workbook(BytesIO(data))
    clean_workbook(wb, color_map=None, cn_overrides=overrides)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
