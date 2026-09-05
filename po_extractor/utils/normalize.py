"""Shared string / cell normalisation — the single home for every "clean a
cell value" helper that used to be copy-pasted per module.

Each function here replaced several near-identical private copies whose
*differences* were real (a parser that blanks Excel error strings, one that
formats integral floats as ints, one that truncates instead of rounding).
Those differences are keyword flags with the old copy's behaviour as the
caller's chosen value, so every call site keeps exactly the semantics it had.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable


# ── header / key normalisation ──────────────────────────────────────────────

def normalize_header(s: str | None) -> str:
    """Normalize a header / column label for alias matching.

    * Strips surrounding whitespace
    * Maps full-width brackets, colons, spaces and yen signs to ASCII equivalents
    * Converts ``\\n`` to a regular space
    * Collapses any run of whitespace to a single space
    * Lowercases the result
    """
    if s is None:
        return ""
    s = str(s).strip()
    s = (
        s.replace('（', '(')   # （
         .replace('）', ')')   # ）
         .replace('：', ':')   # ：
         .replace('　', ' ')   # ideographic space
         .replace('￥', '\xa5')  # ￥ → ¥
         .replace('\n', ' ')
    )
    return re.sub(r'\s+', ' ', s.lower())


def normalize_text(v: Any) -> str:
    """Trimmed, lower-cased, whitespace collapsed — no bracket folding.

    The cutting-plan parser's cell/label comparison: both sides go through
    the same function, so punctuation is compared literally."""
    if v is None:
        return ""
    return " ".join(str(v).split()).strip().lower()


def norm_header_key(v: Any) -> str:
    """Heading text reduced to a comparable key: lower-cased, full-width
    brackets folded, *all* whitespace removed.

    For headings that wrap onto two lines (``发票金额\\n(报关金额）``) and mix
    full-width and ASCII brackets — used by the settlement and fabric-
    condition parsers, whose alias tables are written in this form."""
    if v is None:
        return ""
    s = str(v).strip().lower()
    s = s.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", s)


def normalize_key(s: Any) -> str:
    """Strip whitespace, drop every non-alphanumeric, upper-case — the key
    form for all style / PO / code lookups."""
    return re.sub(r'[^A-Za-z0-9]', '', str(s).strip()).upper()


# ── cell text ───────────────────────────────────────────────────────────────

# A cached formula error (e.g. a VLOOKUP that couldn't resolve) is stored by
# openpyxl as the literal text "#N/A" — not None.  Treated as a value it would
# leak into match keys and generated cells.
_EXCEL_ERROR_RE = re.compile(
    r'^#(N/A|REF!|VALUE!|DIV/0!|NAME\?|NULL!|NUM!|SPILL!|CALC!)$', re.IGNORECASE,
)


def cell_text(val: Any, *, dates: bool = False, int_floats: bool = False,
              drop_nan: bool = False, drop_excel_errors: bool = False) -> str:
    """A cell value as stripped text; ``''`` for None.

    * ``dates``             — ``datetime``/``date`` → ``YYYY-MM-DD``
    * ``int_floats``        — ``3.0`` → ``"3"`` (a count that Excel stored as float)
    * ``drop_nan``          — the literal strings ``nan`` / ``none`` become ``''``
    * ``drop_excel_errors`` — cached ``#N/A``-style error strings become ``''``
    """
    if val is None:
        return ""
    if dates and isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    if int_floats and isinstance(val, float) and val.is_integer():
        return str(int(val))
    s = str(val).strip()
    if drop_nan and s.lower() in ("nan", "none"):
        return ""
    if drop_excel_errors and _EXCEL_ERROR_RE.match(s):
        return ""
    return s


def cell_date_text(v: Any) -> str:
    """A date-ish cell → ISO string; ``''`` when empty/falsy; other text
    stripped.  Accepts real date cells, pandas Timestamps and ``'2026-08-01'``."""
    if not v:
        return ""
    if hasattr(v, "isoformat"):
        return v.date().isoformat() if hasattr(v, "date") else v.isoformat()
    return str(v).strip()


# WPS Office embeds in-cell pictures as =DISPIMG("ID_...", ...) formulas; the
# ID keys into the workbook's cellimages.xml part.
_DISPIMG_RE = re.compile(r'DISPIMG\("(ID_[0-9A-Fa-f]+)"', re.IGNORECASE)


def dispimg_id(val: Any) -> str:
    """Image ID from a WPS DISPIMG cell formula, or ``''``."""
    if not val:
        return ""
    m = _DISPIMG_RE.search(str(val))
    return m.group(1) if m else ""


# ── numbers ─────────────────────────────────────────────────────────────────

_CURRENCY_NOISE = ("$", "£", "¥", "\xa0")


def to_float(v: Any, *, default: float | None = None,
             commas: bool = True, bools: bool = False,
             strip_currency: bool = False,
             percent: str | None = None,
             none_tokens: Iterable[str] = ()) -> float | None:
    """Float value of a cell, or *default* when it isn't one.

    * ``commas``         — strip thousands separators before parsing
    * ``bools``          — accept ``True``/``False`` as 1.0/0.0 (else → default)
    * ``strip_currency`` — drop ``$ £ ¥`` and non-breaking spaces
    * ``percent``        — ``"ratio"``: ``"3.25%"`` → 0.0325; ``"strip"``: → 3.25
    * ``none_tokens``    — extra texts meaning empty (``"nan"``, ``"-"`` …)
    """
    if v is None:
        return default
    if isinstance(v, bool):
        return float(v) if bools else default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if commas:
        s = s.replace(",", "")
    if strip_currency:
        for ch in _CURRENCY_NOISE:
            s = s.replace(ch, "")
        s = s.strip()
    if not s or s.lower() in {t.lower() for t in none_tokens}:
        return default
    is_pct = False
    if percent and s.endswith("%"):
        s = s[:-1]
        is_pct = percent == "ratio"
    try:
        f = float(s)
    except (ValueError, TypeError):
        return default
    return f / 100 if is_pct else f


def to_int(v: Any, *, default: int | None = None, strict: bool = False,
           rounding: str = "round", **float_kw) -> int | None:
    """Integer value of a cell, or *default*.

    * ``strict``   — only ints, integral floats and pure digit strings count;
                     ``"12.5"`` and ``"-3"`` give *default* (no rounding at all)
    * ``rounding`` — ``"round"`` (12.7 → 13) or ``"trunc"`` (12.7 → 12)
    Remaining keywords go to :func:`to_float`.
    """
    if strict:
        if v is None or isinstance(v, bool):
            return default
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
        s = str(v).strip()
        return int(s) if s.isdigit() else default
    f = to_float(v, default=None, **float_kw)
    if f is None:
        return default
    return int(f) if rounding == "trunc" else int(round(f))


# ── output formatting ───────────────────────────────────────────────────────

def yes_no(v: Any) -> str:
    """``Y`` / ``N`` for a truthy / falsy value; ``''`` for None."""
    return "" if v is None else ("Y" if v else "N")
