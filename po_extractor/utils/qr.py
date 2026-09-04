"""QR code generation for presentation sheets.

Wraps ``segno`` (pure Python, no dependencies) behind a small API so the
rest of the code never imports it directly.  The import is deferred and the
absence of the library is reported as a clear message rather than an
ImportError from inside an export: a missing optional dependency should not
look like a bug in the exporter.
"""
from __future__ import annotations

import io

_INSTALL_HINT = (
    "QR code generation needs the 'segno' package — install it with "
    "`pip install segno` (pure Python, no extra dependencies)."
)


class QRUnavailable(RuntimeError):
    """Raised when segno is not installed."""


def available() -> bool:
    """True when QR codes can be generated in this environment."""
    try:
        import segno  # noqa: F401
        return True
    except ImportError:
        return False


def qr_png(data: str, *, scale: int = 4, border: int = 2) -> bytes:
    """PNG bytes of a QR code encoding *data*.

    *scale* is pixels per module; 4 keeps a typical URL readable when the
    image is printed at ~3 cm square.
    """
    if not data:
        raise ValueError("QR data must not be empty")
    try:
        import segno
    except ImportError as exc:
        raise QRUnavailable(_INSTALL_HINT) from exc

    buf = io.BytesIO()
    # error='m' (~15% recovery) survives a printed sheet being scuffed or
    # photocopied, without inflating the module count the way 'h' would.
    segno.make(data, error="m").save(buf, kind="png", scale=scale, border=border)
    return buf.getvalue()


def scan_url(base_url: str, token: str) -> str:
    """The URL a presentation's QR code should encode.

    Points at the web_scan service's presentation route, which logs the scan
    and shows what was on the sheet.
    """
    return f"{(base_url or '').rstrip('/')}/p/{token}"
