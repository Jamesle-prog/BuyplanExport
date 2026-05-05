"""Field-level validation for fabric_master records.

Checks performed per record
---------------------------
MISSING     — required field is None / empty
RANGE       — numeric value outside the expected range
CONSISTENCY — two fields contradict each other
FORMAT      — string does not match expected pattern
"""
from __future__ import annotations

import re
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Data type
# ---------------------------------------------------------------------------

class FabricFieldIssue(NamedTuple):
    quality_no: str
    field:      str
    kind:       str   # "MISSING" | "RANGE" | "CONSISTENCY" | "FORMAT"
    value:      str
    detail:     str


# ---------------------------------------------------------------------------
# Thresholds  (warn when outside these ranges — not hard errors)
# ---------------------------------------------------------------------------

_GSM_MIN       =  50.0
_GSM_MAX       = 800.0
_WIDTH_MIN     =  30.0
_WIDTH_MAX     = 250.0
_SHRINK_MAX    =  30.0   # % — flag above this as suspicious
_SHORT_MAX     =  15.0   # % — flag above this as suspicious

# quality_no format:  2-5 alpha  ·  hyphen  ·  2-5 alpha  ·  hyphen  ·  4-8 digits
# Examples:  BO-DW240485  ·  MQ-BD181446  ·  HHN-JA-01715
_QNO_RE = re.compile(r'^[A-Za-z]{2,5}-[A-Za-z]{1,5}-?\d{4,8}$')


# ---------------------------------------------------------------------------
# Single-record validator
# ---------------------------------------------------------------------------

def validate_record(rec: dict) -> list[FabricFieldIssue]:
    """Return a list of issues for one ``fabric_master`` record dict."""
    issues: list[FabricFieldIssue] = []
    qno = str(rec.get("quality_no") or "").strip()

    # ── quality_no ────────────────────────────────────────────────────────────
    if not qno:
        issues.append(FabricFieldIssue(
            quality_no="", field="quality_no", kind="MISSING",
            value="", detail="quality_no is empty",
        ))
    elif not _QNO_RE.match(qno):
        issues.append(FabricFieldIssue(
            quality_no=qno, field="quality_no", kind="FORMAT",
            value=qno,
            detail=f"'{qno}' does not match expected pattern "
                   "(e.g. BO-DW240485 / MQ-BD181446)",
        ))

    # ── weight_gsm ────────────────────────────────────────────────────────────
    gsm = rec.get("weight_gsm")
    if gsm is not None:
        if gsm <= 0:
            issues.append(FabricFieldIssue(
                quality_no=qno, field="weight_gsm", kind="RANGE",
                value=str(gsm), detail="Weight (g/m²) must be positive",
            ))
        elif not (_GSM_MIN <= gsm <= _GSM_MAX):
            issues.append(FabricFieldIssue(
                quality_no=qno, field="weight_gsm", kind="RANGE",
                value=str(gsm),
                detail=f"Weight {gsm} g/m² is outside the typical range "
                       f"{int(_GSM_MIN)}–{int(_GSM_MAX)} g/m²",
            ))

    # ── width fields ──────────────────────────────────────────────────────────
    cw = rec.get("cuttable_width_cm")
    fw = rec.get("full_width_cm")

    for field_name, val, label in [
        ("cuttable_width_cm", cw, "Cuttable width"),
        ("full_width_cm",     fw, "Full width"),
    ]:
        if val is None:
            continue
        if val <= 0:
            issues.append(FabricFieldIssue(
                quality_no=qno, field=field_name, kind="RANGE",
                value=str(val), detail=f"{label} must be positive",
            ))
        elif not (_WIDTH_MIN <= val <= _WIDTH_MAX):
            issues.append(FabricFieldIssue(
                quality_no=qno, field=field_name, kind="RANGE",
                value=str(val),
                detail=f"{label} {val} cm is outside the typical range "
                       f"{int(_WIDTH_MIN)}–{int(_WIDTH_MAX)} cm",
            ))

    if cw and fw and cw > 0 and fw > 0 and cw > fw:
        issues.append(FabricFieldIssue(
            quality_no=qno, field="cuttable_width_cm", kind="CONSISTENCY",
            value=f"{cw} > {fw}",
            detail=f"Cuttable width ({cw} cm) exceeds full width ({fw} cm)",
        ))

    # ── shrinkage_rate ────────────────────────────────────────────────────────
    sr = rec.get("shrinkage_rate")
    if sr is not None:
        if sr < 0:
            issues.append(FabricFieldIssue(
                quality_no=qno, field="shrinkage_rate", kind="RANGE",
                value=str(sr), detail="Shrinkage rate cannot be negative",
            ))
        elif sr > _SHRINK_MAX:
            issues.append(FabricFieldIssue(
                quality_no=qno, field="shrinkage_rate", kind="RANGE",
                value=str(sr),
                detail=f"Shrinkage {sr}% is unusually high (expected ≤ {int(_SHRINK_MAX)}%)",
            ))

    # ── short_rate ────────────────────────────────────────────────────────────
    shr = rec.get("short_rate")
    if shr is not None:
        if shr < 0:
            issues.append(FabricFieldIssue(
                quality_no=qno, field="short_rate", kind="RANGE",
                value=str(shr), detail="Short rate cannot be negative",
            ))
        elif shr > _SHORT_MAX:
            issues.append(FabricFieldIssue(
                quality_no=qno, field="short_rate", kind="RANGE",
                value=str(shr),
                detail=f"Short rate {shr}% is unusually high (expected ≤ {int(_SHORT_MAX)}%)",
            ))

    return issues


# ---------------------------------------------------------------------------
# Batch validator
# ---------------------------------------------------------------------------

def validate_all_records(records: list[dict]) -> list[FabricFieldIssue]:
    """Validate a list of fabric_master record dicts.  Returns all issues found."""
    issues: list[FabricFieldIssue] = []
    for r in records:
        issues.extend(validate_record(r))
    return issues
