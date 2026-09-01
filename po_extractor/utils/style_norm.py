"""One spelling for a style number: ``/`` is written and searched as ``_``.

Client files carry the same style both ways -- ``TP3267-3/4SLV`` (a 3/4
sleeve) in one file, ``TP3267-3_4SLV`` in another, because Windows filenames
cannot hold ``/`` so every photo, folder and copied-from-a-filename value
already uses ``_``. Stored raw, the two spellings are different strings: the
fabric mapping missed the PO's style, the search box found one and not the
other, and the photo was there but never matched.

The rule, decided 2026-08-31: **``/`` in a style number is stored, matched
and searched as ``_``** -- everywhere. Normalise at intake (the dataclasses
every parser builds, and the store writes that skip them), migrate what is
already on disk, and treat a typed ``/`` as ``_`` in search boxes.

Only ``style`` fields. PO numbers, colours ("BLK/WHT") and fabric codes keep
their slashes -- a colourway's ``/`` is meaningful and never appears in a
filename-keyed lookup.
"""
from __future__ import annotations


def normalize_style_no(style):
    """Return *style* with every ``/`` (and ``\\``) as ``_``, stripped.

    None passes through as None (POMetadata.style is Optional); non-strings
    pass through untouched -- this must never turn a missing value into the
    text "None" or raise mid-parse.
    """
    if not isinstance(style, str):
        return style
    return style.replace("/", "_").replace("\\", "_").strip()
