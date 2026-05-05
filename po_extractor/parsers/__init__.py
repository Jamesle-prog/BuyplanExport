from ..config import FORMAT_INFOR_NEXUS, FORMAT_LEGACY
from ..detectors import detect_format
from ..models import POData
from ..utils.pdf_reader import read_pdf_text
from . import infor_nexus, legacy_giii
from .client_excel import parse_client_excel
from .sky_east_excel import parse_sky_east


def parse_pdf(pdf_path: str) -> POData:
    text = read_pdf_text(pdf_path)
    fmt = detect_format(text)
    if fmt == FORMAT_LEGACY:
        return legacy_giii.parse(text, pdf_path)
    if fmt == FORMAT_INFOR_NEXUS:
        return infor_nexus.parse(text, pdf_path)
    raise ValueError(f"Unknown PO format: {pdf_path}")


def parse_excel(xlsx_path: str, sheet_name: str = "1.1.PO_Client") -> POData:
    """Parse a client Excel file using the two-row header mapping format."""
    return parse_client_excel(xlsx_path, sheet_name=sheet_name)


__all__ = ["parse_pdf", "parse_excel", "parse_sky_east"]
