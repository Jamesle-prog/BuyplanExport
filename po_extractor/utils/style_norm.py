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

import threading

# Per-thread record of adjustments, so a processing run can TELL the user
# what it changed ("TP3267-3/4SLV → TP3267-3_4SLV") instead of renaming
# silently. Thread-local for the same reason as store/audit_context: Streamlit
# runs each browser session in its own thread, and one user's upload must not
# report another user's styles. Inactive unless a pipeline opts in, so the
# hundreds of normalize calls on already-clean values cost one attribute read.
_local = threading.local()


def begin_collecting_changes() -> None:
    """Start recording style adjustments for the current run. Call at the
    top of a file-processing pipeline; pair with :func:`end_collecting_changes`."""
    _local.changes = {}


def end_collecting_changes() -> list[tuple[str, str]]:
    """Stop recording and return [(as_in_file, as_stored), ...] in first-seen
    order, deduplicated. Empty when nothing was adjusted."""
    changes = getattr(_local, "changes", None) or {}
    _local.changes = None
    return list(changes.items())


def normalize_style_no(style):
    """Return *style* with every ``/`` (and ``\\``) as ``_``, stripped.

    None passes through as None (POMetadata.style is Optional); non-strings
    pass through untouched -- this must never turn a missing value into the
    text "None" or raise mid-parse.
    """
    if not isinstance(style, str):
        return style
    fixed = style.replace("/", "_").replace("\\", "_").strip()
    if fixed != style.strip():
        changes = getattr(_local, "changes", None)
        if changes is not None:
            changes.setdefault(style.strip(), fixed)
    return fixed
