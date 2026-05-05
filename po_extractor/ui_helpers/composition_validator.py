"""Fabric composition validator for wash-label generation.

Delegates to :mod:`po_extractor.utils.composition_check` which provides the
canonical fiber dictionary (KNOWN_FIBERS + user-defined custom fibers) and
structured issue detection for:

  PARSE — no ``<pct>%<fiber>`` tokens found
  SUM   — percentages don't add to 100 %
  SPELL — fiber name not in the dictionary (with fuzzy suggestion)
  CASE  — fiber name doesn't start with a capital letter

Missing compositions (empty / null) are caught here before delegation.
"""
from __future__ import annotations

_EMPTY = frozenset({"", "nan", "none", "n/a", "-"})

# Human-readable labels for each issue kind
_KIND_LABEL: dict[str, str] = {
    "PARSE": "Cannot parse",
    "SUM":   "Sum ≠ 100%",
    "SPELL": "Unknown fiber",
    "CASE":  "Wrong capitalization",
}


def validate_fabric_parts(
    fabric_parts_by_style: dict,
    fm_cache: dict | None = None,
) -> list[dict]:
    """Validate composition strings for all FabricPart objects.

    Uses the canonical fiber dictionary from
    :mod:`po_extractor.utils.composition_check` (KNOWN_FIBERS + any custom
    fibers the user has added via the Admin panel).

    Parameters
    ----------
    fabric_parts_by_style : {style: [FabricPart, ...], ...}
    fm_cache : optional {hhn_no: record} dict returned by
        ``FabricMasterStore.get_batch_enrichment()``.  When provided, missing
        compositions are diagnosed more precisely:

        * HHN not in ``fm_cache``  →  "Fabric code not found in Fabric DB"
        * HHN in ``fm_cache`` but ``composition_en`` is empty
                                   →  "Found in Fabric DB but composition is empty"

        When *None* the generic "Missing composition" message is used.

    Returns
    -------
    list of error dicts — one entry per problematic fabric part:

    .. code-block:: python

        {
            "style":       str,
            "combo_idx":   int,
            "seq":         int,
            "body_part":   str,
            "hhn_no":      str,
            "composition": str,   # current (possibly wrong) value
            "issue":       str,   # human-readable description
            "suggestion":  str,   # best-guess correction (may be empty)
        }

    Sorted by (style, combo_idx, seq).
    """
    from po_extractor.utils.composition_check import (
        validate_composition as _vc,
        get_all_fibers       as _get_fibers,
    )

    all_fibers = _get_fibers()   # load KNOWN_FIBERS + custom once for the batch
    errors: list[dict] = []

    for style, parts in fabric_parts_by_style.items():
        for p in parts:
            comp_raw = getattr(p, "composition", "") or ""
            comp     = str(comp_raw).strip()
            hhn      = str(getattr(p, "hhn_no", "") or "").strip()

            base = {
                "style":       style,
                "combo_idx":   getattr(p, "combo_idx", 0),
                "seq":         getattr(p, "seq", 0),
                "body_part":   getattr(p, "body_part", "") or "",
                "hhn_no":      hhn,
                "composition": comp,
            }

            # ── Missing / null composition ───────────────────────────────────
            if comp.lower() in _EMPTY:
                # Diagnose *why* it's missing using the FM cache when available
                if fm_cache is not None and hhn:
                    if hhn not in fm_cache:
                        issue = f"Fabric code '{hhn}' not found in Fabric DB"
                    else:
                        db_comp = str(
                            fm_cache[hhn].get("composition_en") or ""
                        ).strip()
                        if not db_comp or db_comp.lower() in _EMPTY:
                            issue = (
                                f"Fabric code '{hhn}' is in Fabric DB "
                                "but has no composition — please fill it in the 🧵 Fabric DB tab"
                            )
                        else:
                            # Should not happen (enrichment would have filled it),
                            # but handle gracefully.
                            issue = "Missing composition"
                else:
                    issue = "Missing composition"

                errors.append({**base, "composition": "", "issue": issue,
                                "suggestion": ""})
                continue

            # ── Delegate to the shared validator ────────────────────────────
            issues = _vc(comp, all_fibers=all_fibers)
            if not issues:
                continue   # composition is fully valid

            # Collapse all issues for this part into one row
            msgs:        list[str] = []
            suggestions: list[str] = []
            for iss in issues:
                label = _KIND_LABEL.get(iss.kind, iss.kind)
                msgs.append(f"[{label}] {iss.detail}")
                if iss.suggestions:
                    suggestions.append(iss.suggestions)

            errors.append({
                **base,
                "issue":      "; ".join(msgs),
                "suggestion": ", ".join(dict.fromkeys(suggestions)),  # dedup, keep order
            })

    errors.sort(key=lambda r: (r["style"], r["combo_idx"], r["seq"]))
    return errors
