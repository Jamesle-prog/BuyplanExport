from ..config import FORMAT_INFOR_NEXUS, FORMAT_LEGACY
from ..detectors import detect_format
from ..models import POData
from ..utils.pdf_reader import read_pdf_text
from . import infor_nexus, legacy_giii, deepseek_parser
from .client_excel import parse_client_excel
from .sky_east_excel import parse_sky_east


def parse_pdf(pdf_path: str) -> POData:
    """Regex-based PDF parser (fast, no API required)."""
    text = read_pdf_text(pdf_path)
    fmt = detect_format(text)
    if fmt == FORMAT_LEGACY:
        return legacy_giii.parse(text, pdf_path)
    if fmt == FORMAT_INFOR_NEXUS:
        return infor_nexus.parse(text, pdf_path)
    raise ValueError(f"Unknown PO format: {pdf_path}")


def parse_pdf_ai(pdf_path: str, api_key: str,
                 model: str = "deepseek-chat") -> POData:
    """AI-powered PDF parser using DeepSeek API.

    Falls back to the regex parser if the API call fails, so the pipeline
    never silently drops a file.  The returned POData includes
    parser_version='ds-1.0' so results can be distinguished in history.
    """
    text = read_pdf_text(pdf_path)
    fmt = detect_format(text)
    try:
        return deepseek_parser.parse(text, pdf_path,
                                     api_key=api_key, model=model,
                                     source_format=fmt)
    except Exception as exc:
        import warnings
        warnings.warn(f"[deepseek_parser] API call failed, falling back to regex: {exc!r}")
        return parse_pdf(pdf_path)


def parse_excel(xlsx_path: str, sheet_name: str = "1.1.PO_Client") -> POData:
    """Parse a client Excel file using the two-row header mapping format."""
    return parse_client_excel(xlsx_path, sheet_name=sheet_name)


__all__ = ["parse_pdf", "parse_pdf_ai", "parse_excel", "parse_sky_east"]
