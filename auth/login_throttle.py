"""Sign-in throttle — failed attempts cost something, process-wide.

The app is reachable from the network, so a wrong password must not be free
to retry forever.  After ``LOGIN_FAIL_THRESHOLD`` failures a key (the
lower-cased username) locks out with exponential backoff, capped at
``LOGIN_MAX_LOCK_S``; a coarser per-source-address key catches username
spraying without locking everyone else out.

Why this is its own module and not part of app.py
--------------------------------------------------
Streamlit runs ``app.py`` by ``exec``-ing it into a **fresh module
namespace on every script run** (``ScriptRunner._new_module("__main__")``).
Any dict defined at app.py module level is therefore recreated on every
rerun — including the rerun that follows each failed attempt — so a
counter kept there never reaches the threshold.  That is exactly what the
previous implementation did, and it never locked anyone out (verified: 8
wrong passwords against a threshold of 5, no lockout).

Imported modules are different: they live in ``sys.modules`` for the life
of the process and are shared by every session thread.  State kept here
genuinely is process-wide.

The counters are in-memory on purpose: a lockout that survives a server
restart would need persistence and a way for an admin to clear it, and a
restart is itself a reasonable "unlock".  The login log keeps the audit
trail.
"""
from __future__ import annotations

import threading
import time

from po_extractor.config import (
    LOGIN_BASE_LOCK_S, LOGIN_FAIL_THRESHOLD, LOGIN_GLOBAL_LOCK_S,
    LOGIN_GLOBAL_THRESHOLD, LOGIN_MAX_LOCK_S,
)

GLOBAL_KEY = "\x00global"
_SOURCE_PREFIX = "\x00src:"


def source_key(source: str) -> str:
    """Brake key for a client address; the process-wide key when unknown.

    Username spraying comes from one source, so the brake is per address:
    one colleague hammering a wrong password no longer locks the whole team
    out.  With no address (Streamlit build without request headers) it falls
    back to a single global brake — safe, if blunt."""
    return _SOURCE_PREFIX + source if source else GLOBAL_KEY

_lock = threading.Lock()
_failures: dict[str, tuple[int, float]] = {}   # key → (fails, locked_until)


def lock_remaining(key: str) -> int:
    """Seconds left on the lockout for *key* (0 = not locked)."""
    with _lock:
        _count, until = _failures.get(key, (0, 0.0))
        remaining = until - time.time()
    return int(remaining) + 1 if remaining > 0 else 0


def record_failure(key: str, *, threshold: int = LOGIN_FAIL_THRESHOLD,
                   base_lock_s: float = LOGIN_BASE_LOCK_S,
                   max_lock_s: float = LOGIN_MAX_LOCK_S) -> None:
    """Count one failed attempt against *key*; lock it once over threshold.

    Lock length doubles with every failure past the threshold — 60 s, 120 s,
    240 s … — up to *max_lock_s*, so a slow brute force gets slower still.
    """
    with _lock:
        count, _until = _failures.get(key, (0, 0.0))
        count += 1
        lock_s = 0.0
        if count >= threshold:
            lock_s = min(base_lock_s * (2 ** (count - threshold)), max_lock_s)
        _failures[key] = (count, time.time() + lock_s)


def record_global_failure(source: str = "") -> None:
    """The username-spraying brake: many failures across *any* usernames
    from one *source* address."""
    record_failure(source_key(source), threshold=LOGIN_GLOBAL_THRESHOLD,
                   base_lock_s=LOGIN_GLOBAL_LOCK_S, max_lock_s=LOGIN_GLOBAL_LOCK_S)


def record_success(key: str) -> None:
    """A correct password clears that key's history."""
    with _lock:
        _failures.pop(key, None)


def wait_seconds(key: str, source: str = "") -> int:
    """Seconds a sign-in for *key* from *source* must wait — the longer of the
    username's own lock and its source's spraying brake.  0 means go ahead."""
    return max(lock_remaining(key), lock_remaining(source_key(source)))


def reset() -> None:
    """Forget every counter.  For tests and an admin 'unlock all'."""
    with _lock:
        _failures.clear()
