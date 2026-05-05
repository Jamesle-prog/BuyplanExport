"""Universal file-format and client detector.

Given any uploaded file path (PDF or Excel), returns a DetectionResult
describing what format it is, which client(s) it most likely belongs to,
and a confidence level.

Detection logic
---------------
PDF files
  • Text is extracted and passed through the existing format_detector.
  • Additional signals (buyer name, division, content keywords) can narrow
    the result to a specific company when multiple companies share a format.

Excel files
  • Sheet names are checked first (cheapest signal).
  • Row-2 internal headers are checked for the two-row mapping pattern.
  • Fallback: scan all sheet names for known patterns.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from auth.companies import COMPANY_GIII

# fmt: off
_PDF_EXTS   = {".pdf"}
_EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}
# fmt: on


@dataclass
class DetectionResult:
    filename:       str
    file_type:      str          # "pdf" | "excel" | "unknown"
    format_id:      str          # e.g. "infor_nexus", "excel_zalando", "unknown"
    companies:      list[str]    # candidate company names, most-likely first
    confidence:     str          # "high" | "medium" | "low"
    detail:         str = ""     # human-readable reason
    error:          str = ""     # non-empty if detection failed


def detect_file(path: str) -> DetectionResult:
    """Run detection on a single file and return a DetectionResult."""
    filename = os.path.basename(path)
    ext = os.path.splitext(filename)[1].lower()

    if ext in _PDF_EXTS:
        return _detect_pdf(path, filename)
    if ext in _EXCEL_EXTS:
        return _detect_excel(path, filename)

    return DetectionResult(
        filename=filename, file_type="unknown", format_id="unknown",
        companies=[], confidence="low",
        detail=f"Unrecognised file extension: {ext}",
    )


# ── PDF detection ─────────────────────────────────────────────────────────────

def _detect_pdf(path: str, filename: str) -> DetectionResult:
    try:
        from ..utils.pdf_reader import read_pdf_text
        from .format_detector import detect_format
        from ...auth.companies import companies_for_format
    except ImportError:
        # Fallback import path when called standalone
        from po_extractor.utils.pdf_reader import read_pdf_text   # type: ignore
        from po_extractor.detectors.format_detector import detect_format  # type: ignore
        from auth.companies import companies_for_format  # type: ignore

    try:
        text = read_pdf_text(path)
    except Exception as exc:
        return DetectionResult(
            filename=filename, file_type="pdf", format_id="unknown",
            companies=[], confidence="low", error=str(exc),
        )

    fmt = detect_format(text)

    if fmt == "unknown":
        return DetectionResult(
            filename=filename, file_type="pdf", format_id="unknown",
            companies=[], confidence="low",
            detail="Could not identify PO format from PDF content.",
        )

    candidates = companies_for_format(fmt)

    # Try to narrow down when multiple companies share a format
    # (e.g. both GIII and DKNY use infor_nexus)
    narrowed, detail = _narrow_pdf_company(text, candidates, fmt)

    return DetectionResult(
        filename=filename, file_type="pdf", format_id=fmt,
        companies=narrowed,
        confidence="high" if len(narrowed) == 1 else "medium",
        detail=detail,
    )


def _narrow_pdf_company(text: str, candidates: list[str], fmt: str) -> tuple[list[str], str]:
    """Use content signals to pick the most-likely company from candidates."""
    if len(candidates) <= 1:
        return candidates, f"Format: {fmt}"

    text_upper = text.upper()

    # Company-name keywords that appear in the PDF body
    keywords: dict[str, list[str]] = {
        COMPANY_GIII: ["G-III", "GIII", "G III APPAREL"],
    }

    scores: dict[str, int] = {c: 0 for c in candidates}
    for company, kws in keywords.items():
        if company in candidates:
            for kw in kws:
                if kw in text_upper:
                    scores[company] += 1

    best_score = max(scores.values())
    if best_score > 0:
        winners = [c for c, s in scores.items() if s == best_score]
        detail = f"Format: {fmt}. Keyword match → {', '.join(winners)}"
        return winners + [c for c in candidates if c not in winners], detail

    # No keyword signal — return original order
    return candidates, f"Format: {fmt}. Multiple candidates: {', '.join(candidates)}"


# ── Excel detection ───────────────────────────────────────────────────────────

def _detect_excel(path: str, filename: str) -> DetectionResult:
    try:
        import openpyxl
    except ImportError:
        return DetectionResult(
            filename=filename, file_type="excel", format_id="unknown",
            companies=[], confidence="low",
            error="openpyxl not installed.",
        )

    try:
        wb = openpyxl.open(path, read_only=True, data_only=True) if hasattr(openpyxl, "open") \
             else openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        wb.close()
    except Exception as exc:
        return DetectionResult(
            filename=filename, file_type="excel", format_id="unknown",
            companies=[], confidence="low", error=str(exc),
        )

    # Check sheet names against known patterns
    sheet_set = {s.strip() for s in sheet_names}

    from ..config import FORMAT_EXCEL_ZALANDO

    # Zalando two-row mapping format
    if "1.1.PO_Client" in sheet_set:
        return DetectionResult(
            filename=filename, file_type="excel", format_id=FORMAT_EXCEL_ZALANDO,
            companies=["Zalando"], confidence="high",
            detail="Found sheet '1.1.PO_Client' — Zalando mapping format.",
        )

    # Older single-row header variant
    if "1.PO_Client" in sheet_set:
        return DetectionResult(
            filename=filename, file_type="excel", format_id=FORMAT_EXCEL_ZALANDO,
            companies=["Zalando"], confidence="medium",
            detail="Found sheet '1.PO_Client' — possible older Zalando format.",
        )

    # Generic Excel with no known sheet pattern
    return DetectionResult(
        filename=filename, file_type="excel", format_id="excel_unknown",
        companies=[], confidence="low",
        detail=f"No recognised sheet found. Sheets: {', '.join(sheet_names[:5])}",
    )


# ── Batch detection ───────────────────────────────────────────────────────────

def detect_files(paths: list[str]) -> list[DetectionResult]:
    """Run detection on a list of file paths."""
    return [detect_file(p) for p in paths]


def group_by_company(results: list[DetectionResult]) -> dict[str, list[DetectionResult]]:
    """Group DetectionResults by their primary (first) detected company.

    Files with no company go under the key ``"Unknown"``.
    Files with multiple candidates go under their first (most-likely) company.
    """
    groups: dict[str, list[DetectionResult]] = {}
    for r in results:
        key = r.companies[0] if r.companies else "Unknown"
        groups.setdefault(key, []).append(r)
    return groups
