"""Validate fabric composition strings (面料成分 英文).

A valid composition string is a space-separated list of ``<pct>%<fiber>`` tokens
where the percentages add up to exactly 100. Example:

    "60%Cotton 40%Polyester"           → OK
    "68%Polyester 28%Cotton 4%Spandex" → OK
    "100%Cotton"                       → OK
    "60%Cotton 30%Polyster"            → SPELL  (Polyster → Polyester)
    "60%Cotton 30%Polyester"           → SUM    (90 ≠ 100)
    "100% Cotton"                      → OK     (whitespace tolerated)

Multi-layer fabrics (Face / Back labels) are not SUM-checked because each
layer is expected to sum to 100% independently.

User-defined fibers are stored in  po_extractor/data/custom_fibers.json  and
are merged with KNOWN_FIBERS at validation time (custom takes priority).
"""
from __future__ import annotations

import json
import re
from difflib import get_close_matches
from pathlib import Path
from typing import NamedTuple

# Path to the user-editable custom-fiber sidecar
_DATA_DIR = Path(__file__).parent.parent / "data"
_CUSTOM_FIBERS_PATH = _DATA_DIR / "custom_fibers.json"

# ---------------------------------------------------------------------------
# Built-in fiber dictionary
# ---------------------------------------------------------------------------
# Lowercase lookup keys → canonical display name.
KNOWN_FIBERS: dict[str, str] = {
    # ── Natural ──────────────────────────────────────────────────────────────
    "cotton":                   "Cotton",
    "wool":                     "Wool",
    "silk":                     "Silk",
    "linen":                    "Linen",
    "hemp":                     "Hemp",
    "cashmere":                 "Cashmere",
    "alpaca":                   "Alpaca",
    "mohair":                   "Mohair",
    "ramie":                    "Ramie",
    "jute":                     "Jute",
    "bamboo":                   "Bamboo",
    # Cotton variants / certifications
    "organic cotton":           "Organic Cotton",
    "bci cotton":               "BCI Cotton",
    "pima cotton":              "Pima Cotton",
    "long staple cotton":       "Long Staple Cotton",
    # Silk variants
    "mulberry silk":            "Mulberry Silk",
    "spun silk":                "Spun Silk",
    # ── Regenerated cellulose ─────────────────────────────────────────────────
    "viscose":                  "Viscose",
    "rayon":                    "Rayon",
    "modal":                    "Modal",
    "micro modal":              "Micro Modal",
    "tencel":                   "Tencel",
    "lyocell":                  "Lyocell",
    "acetate":                  "Acetate",
    "acetic acid":              "Acetic Acid",   # alternative name for acetate fibre
    "cupro":                    "Cupro",
    "ecovero":                  "Ecovero",       # Lenzing branded sustainable viscose
    "bamboo fiber":             "Bamboo Fiber",
    # ── Synthetic ────────────────────────────────────────────────────────────
    "polyester":                "Polyester",
    "recycle polyester":        "Recycle Polyester",
    "recycled polyester":       "Recycled Polyester",
    "polyester spun":           "Polyester Spun",
    "nylon":                    "Nylon",
    "polyamide":                "Polyamide",
    "recycle nylon":            "Recycle Nylon",
    "recycled nylon":           "Recycled Nylon",
    "acrylic":                  "Acrylic",
    "spandex":                  "Spandex",
    "elastane":                 "Elastane",
    "lycra":                    "Lycra",
    "elastomultiester":         "Elastomultiester",
    "polypropylene":            "Polypropylene",
    "polyurethane":             "Polyurethane",
    "sorona":                   "Sorona",        # DuPont bio-based fibre
    "poy":                      "POY",           # Partially Oriented Yarn
    # Recycled cotton
    "recycle cotton":           "Recycle Cotton",
    "recycled cotton":          "Recycled Cotton",
    # ── Metallic / decorative ─────────────────────────────────────────────────
    "lurex":                    "Lurex",
    "metallic":                 "Metallic",
    "metal":                    "Metal",
    "silver":                   "Silver",        # antimicrobial silver thread
    # ── Leather / skin ───────────────────────────────────────────────────────
    "goat leather":             "Goat Leather",
    "pig leather":              "Pig Leather",
    "cowhide":                  "Cowhide",
    "cow leather":              "Cow Leather",
    "sheepskin":                "Sheepskin",
    "goat skin":                "Goat Skin",
    # ── Trade abbreviations / generic ────────────────────────────────────────
    "pu":                       "PU",
    "pvc":                      "PVC",
    "ea":                       "EA",
    "el":                       "EL",
    "pa":                       "PA",
    "pe":                       "PE",
    "tr":                       "TR",            # Terylene/Rayon blend code
    "tl":                       "TL",
    "cmd":                      "CMD",
    "man-made fiber":           "Man-made Fiber",
    "other chemical fiber":     "Other Chemical Fiber",
    "other":                    "Other",
}

# Token pattern: <pct>% <fiber-words>   — fiber name runs until the next digit or EOL.
# '+' is a terminator so "5%Spandex+Sequins" yields (5, "Spandex") cleanly.
_TOKEN_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*%\s*([A-Za-z][A-Za-z\s\-/]*?)(?=\s*\d|\s*[,;+]|\s*$)',
)

# Multi-layer fabric detection — these compositions have a separate 100 % per layer
# so the total will legitimately exceed 100 % and SUM checks must be skipped.
_MULTILAYER_RE = re.compile(
    r'\b(?:face|back|lining|inner|outer|shell)\b'   # "Face 65%..." / "Back 100%..."
    r'|\b[fb]\s*[：:]',                              # "F:100%PU / B:100%Viscose"
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Custom-fiber persistence
# ---------------------------------------------------------------------------

def load_custom_fibers() -> dict[str, str]:
    """Load user-defined fibers from the JSON sidecar file.

    Returns an empty dict when the file does not exist or is malformed.
    """
    try:
        with _CUSTOM_FIBERS_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return {
            str(k).lower().strip(): str(v).strip()
            for k, v in data.items()
            if str(k).strip() and str(v).strip()
        }
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_custom_fibers(fibers: dict[str, str]) -> None:
    """Persist user-defined fibers to the JSON sidecar file.

    Keys are normalised to lowercase; empty / blank entries are dropped.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean = {
        str(k).lower().strip(): str(v).strip()
        for k, v in fibers.items()
        if str(k).strip() and str(v).strip()
    }
    with _CUSTOM_FIBERS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(clean, fh, ensure_ascii=False, indent=2, sort_keys=True)


def get_all_fibers() -> dict[str, str]:
    """Return KNOWN_FIBERS merged with user-defined custom fibers.

    Custom entries take priority on key conflicts so users can override
    built-in canonical names.
    """
    merged = dict(KNOWN_FIBERS)
    merged.update(load_custom_fibers())
    return merged


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class CompositionIssue(NamedTuple):
    quality_no: str
    composition: str
    kind: str             # "SUM" | "SPELL" | "PARSE" | "CASE"
    detail: str
    total_pct: float
    suggestions: str      # comma-joined suggested fixes (empty if none)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Collapse whitespace, strip."""
    return re.sub(r'\s+', ' ', (s or '').strip())


def _strip_annotations(text: str) -> str:
    """Remove parenthetical annotations before tokenising.

    Handles both ASCII ``(Split)`` and full-width Chinese ``（Metalized）``
    parentheses which appear as descriptive notes rather than fibre names.
    """
    return re.sub(r'\s*[（(][^）)]*[）)]\s*', ' ', text)


def parse_composition(s: str) -> list[tuple[float, str]]:
    """Return [(pct, fiber_token), …] parsed from the string.

    Fiber tokens are returned in the original casing; percentages as floats.
    """
    if not s:
        return []
    text = _normalize(s)
    text = _strip_annotations(text)
    out: list[tuple[float, str]] = []
    for m in _TOKEN_RE.finditer(text):
        pct = float(m.group(1))
        name = _normalize(m.group(2))
        if name:
            out.append((pct, name))
    return out


def _suggest_fiber(token: str, all_fibers: dict[str, str]) -> str:
    """Return a likely canonical fiber name for a misspelled token, or ''."""
    key = token.lower().strip()
    if key in all_fibers:
        return ""  # already valid
    canonical_names = tuple(sorted(set(all_fibers.values()), key=str.lower))
    matches = get_close_matches(key, list(all_fibers.keys()), n=1, cutoff=0.75)
    if matches:
        return all_fibers[matches[0]]
    # Try against canonical display names too (handles e.g. "Polyster" → "Polyester")
    matches = get_close_matches(token, canonical_names, n=1, cutoff=0.75)
    return matches[0] if matches else ""


# ---------------------------------------------------------------------------
# Public validation API
# ---------------------------------------------------------------------------

def validate_composition(
    composition: str,
    quality_no: str = "",
    all_fibers: dict[str, str] | None = None,
) -> list[CompositionIssue]:
    """Return zero or more issues for a single composition string.

    Returns an empty list when the string is fully valid.

    Parameters
    ----------
    all_fibers:
        Pre-built fiber dict (KNOWN_FIBERS + custom).  When *None* the dict
        is loaded fresh via :func:`get_all_fibers` — pass an explicit value
        when calling in a loop to avoid repeated file reads.
    """
    if all_fibers is None:
        all_fibers = get_all_fibers()

    issues: list[CompositionIssue] = []
    raw = composition or ""
    if not raw.strip():
        return issues

    parts = parse_composition(raw)
    if not parts:
        issues.append(CompositionIssue(
            quality_no=quality_no, composition=raw, kind="PARSE",
            detail="Could not parse any '<pct>% <fiber>' tokens",
            total_pct=0.0, suggestions="",
        ))
        return issues

    # Sum check — skip for multi-layer fabrics (Face / Back labels); tolerate
    # floating-point drift (±0.5 pp is safe for whole-number inputs).
    total = round(sum(pct for pct, _ in parts), 2)
    is_multilayer = bool(_MULTILAYER_RE.search(raw))
    if not is_multilayer and abs(total - 100.0) > 0.5:
        issues.append(CompositionIssue(
            quality_no=quality_no, composition=raw, kind="SUM",
            detail=f"Percentages total {total}% (expected 100%)",
            total_pct=total, suggestions="",
        ))

    # Spelling check — one issue per unknown fiber token
    seen_bad: set[str] = set()
    for _, name in parts:
        key = name.lower().strip()
        if key in all_fibers or name in seen_bad:
            continue
        suggestion = _suggest_fiber(name, all_fibers)
        seen_bad.add(name)
        issues.append(CompositionIssue(
            quality_no=quality_no, composition=raw, kind="SPELL",
            detail=f"Unknown fiber '{name}'"
                   + (f" — did you mean '{suggestion}'?" if suggestion else ""),
            total_pct=total,
            suggestions=suggestion,
        ))

    # Case check — each fiber name must start with a capital letter
    seen_case: set[str] = set()
    for _, name in parts:
        if name in seen_case:
            continue
        seen_case.add(name)
        # Check the first alphabetic character of the token
        first_alpha = next((c for c in name if c.isalpha()), None)
        if first_alpha and first_alpha.islower():
            # Suggest the corrected version: capitalise first alphabetic char
            corrected = name[0].upper() + name[1:] if name else name
            issues.append(CompositionIssue(
                quality_no=quality_no, composition=raw, kind="CASE",
                detail=f"Fiber '{name}' should start with a capital letter",
                total_pct=total,
                suggestions=corrected,
            ))

    return issues


def validate_all(records: list[dict]) -> list[CompositionIssue]:
    """Validate a batch of ``{quality_no, composition_en}`` dicts at once.

    Custom fibers are loaded once and reused for the whole batch.
    """
    all_fibers = get_all_fibers()
    issues: list[CompositionIssue] = []
    for r in records:
        q = str(r.get("quality_no") or "")
        c = str(r.get("composition_en") or "")
        issues.extend(validate_composition(c, q, all_fibers=all_fibers))
    return issues
