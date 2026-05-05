"""Machine-lock license validation.

How it works
------------
On first run the app writes a ``license.key`` file next to this module.
The key binds the installation to a hardware fingerprint derived from the
MAC address and platform identity of the current machine.  Copying the
folder to a different machine produces a different fingerprint so
``validate_license()`` returns False and the app refuses to start.

Re-registering on a new machine
--------------------------------
1. Delete (or do not copy) ``license.key``.
2. Start the app once on the new machine — a fresh key is written automatically.

Centrally-managed deployment
-----------------------------
Pre-generate a key for a target machine without needing to run the app on
it first::

    python -m auth.generate_license        # prints machine_id of *this* machine

Copy the resulting ``license.key`` alongside the app before first launch.
The app will then reject any machine whose fingerprint does not match the file.
"""
from __future__ import annotations

import hashlib
import hmac
import platform
import uuid
from pathlib import Path

_LICENSE_KEY_PATH = Path(__file__).parent / "license.key"

# Shared HMAC secret — prevents the key file from being forged by hand.
# Keep this value consistent across all distributed builds.
_SECRET = b"GIII-PO-Automation-2024-\xf3\x9a\xc1\x77"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _machine_id() -> str:
    """Hardware fingerprint: first 32 hex chars of SHA-256(MAC:node:machine)."""
    raw = f"{hex(uuid.getnode())}:{platform.node()}:{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _sign(mid: str) -> str:
    """Return HMAC-SHA256 hex digest of *mid* using the embedded secret."""
    return hmac.new(_SECRET, mid.encode(), hashlib.sha256).hexdigest()


def _write_key(path: Path, mid: str) -> None:
    """Write ``<machine_id>:<signature>`` to *path*."""
    path.write_text(f"{mid}:{_sign(mid)}\n", encoding="ascii")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_license() -> tuple[bool, str]:
    """Return (is_valid, message).

    * First run (no ``license.key``): generates and writes the key, returns True.
    * Subsequent runs: verifies HMAC integrity and machine fingerprint match.
    """
    mid = _machine_id()

    if not _LICENSE_KEY_PATH.exists():
        try:
            _write_key(_LICENSE_KEY_PATH, mid)
            return True, "License registered for this machine."
        except OSError as exc:
            return False, f"Could not write license file ({_LICENSE_KEY_PATH}): {exc}"

    try:
        raw = _LICENSE_KEY_PATH.read_text(encoding="ascii").strip()
        parts = raw.split(":")
        if len(parts) != 2:
            return False, (
                "License file is malformed. "
                "Delete license.key and restart to re-register."
            )

        stored_mid, stored_sig = parts

        # Tamper check — verify the HMAC over the stored machine_id
        if not hmac.compare_digest(stored_sig, _sign(stored_mid)):
            return False, (
                "License file has been tampered with. "
                "Contact your administrator or delete license.key to re-register."
            )

        # Machine check — compare stored fingerprint to current hardware
        if not hmac.compare_digest(stored_mid, mid):
            return False, (
                "This installation is locked to a different machine. "
                "Delete license.key on this machine and restart to re-register."
            )

        return True, "License valid."

    except Exception as exc:  # noqa: BLE001
        return False, f"License validation error: {exc}"


def current_machine_id() -> str:
    """Return the fingerprint for the current machine (useful for support/debugging)."""
    return _machine_id()
