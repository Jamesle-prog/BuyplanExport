"""Run the warehouse web scanner:  python -m web_scan

Environment:
  PO_SCAN_PORT       listen port (default 8502)
  PO_SCAN_PASSWORD   shared gate password (default 'scan' — SET THIS in prod)
  PO_SCAN_COMPANIES  comma-separated company scope (default: all companies)
"""
from __future__ import annotations

import os
import socket

import uvicorn

from web_scan.app import app


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


def _say(msg: str) -> None:
    """Print ASCII-safely — a redirected Windows console is often GBK and
    chokes on non-ASCII, which must never take the server down."""
    try:
        print(msg)
    except Exception:
        print(msg.encode("ascii", "replace").decode("ascii"))


def main() -> None:
    port = int(os.environ.get("PO_SCAN_PORT", "8502"))
    if not os.environ.get("PO_SCAN_PASSWORD", "").strip():
        _say("WARNING: PO_SCAN_PASSWORD is not set - using the default 'scan'. "
             "Set PO_SCAN_PASSWORD before exposing this on a shared network.")
    _say(f"Warehouse web scanner -> http://{_lan_ip()}:{port}  "
         f"(open this on the PDA browser)")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
