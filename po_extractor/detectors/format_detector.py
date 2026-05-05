"""Auto-detect PO format from extracted PDF text."""
from ..config import (
    FORMAT_INFOR_NEXUS, FORMAT_LEGACY, FORMAT_UNKNOWN,
    FORMAT_DETECTION_KEYWORDS,
)

_KW = FORMAT_DETECTION_KEYWORDS


def detect_format(text: str) -> str:
    if any(kw in text for kw in _KW["infor_nexus_primary"]):
        return FORMAT_INFOR_NEXUS
    if all(kw in text for kw in _KW["legacy_giii_required"]):
        return FORMAT_LEGACY
    # Fallback: secondary signals suggest Infor Nexus
    if all(kw in text for kw in _KW["infor_nexus_fallback"]):
        return FORMAT_INFOR_NEXUS
    return FORMAT_UNKNOWN
