"""One MATCHING key for a style number: ``/`` compares equal to ``_``.

Client files carry the same style both ways -- ``TP3267-3/4SLV`` (a 3/4
sleeve) in one file, ``TP3267-3_4SLV`` in another, because Windows filenames
cannot hold ``/`` so photos and filename-derived copies use ``_``. Compared
raw, the two spellings are different strings: the fabric mapping missed the
PO's style, search found one spelling and not the other.

The rule, settled 2026-09-01 (replacing the 2026-08-31 store-as-underscore
attempt): **what the file says is what is stored and what is shown** -- the
slash never changes on screen or in an export. Only *comparisons* use this
key: fabric-mapping and consumption lookups, production-tracking row
identity, cutting-plan style filters, search boxes, photo filenames. Same
pattern as ``sky_east_store.colour_key`` -- raw value kept, matching done on
a normalised key.

Only ``style`` fields. Colours ("BLK/WHT") and fabric codes keep slash
semantics everywhere, including matching.
"""
from __future__ import annotations


def style_key(style) -> str:
    """The comparison key for a style number: ``/`` and ``\`` as ``_``,
    stripped. Never raises; non-strings key as "" (they identify nothing).
    """
    if not isinstance(style, str):
        return ""
    return style.replace("/", "_").replace("\\", "_").strip()


# The 2026-08-31 intake-rewrite name, kept so any straggler import still
# resolves; new code says style_key.
normalize_style_no = style_key
