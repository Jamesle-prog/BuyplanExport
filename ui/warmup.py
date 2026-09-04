"""Pre-load the heavy imports the first sign-in would otherwise pay for.

The login page deliberately imports almost nothing, which keeps a cold
server's first page fast.  The cost moves to the first click instead: the
first ``verify_password`` loads bcrypt and computes the timing-pad hash
(~0.3 s), the first login-log write imports ``po_extractor.store`` — and
with it pandas, numpy and openpyxl (~0.6 s here) — and the first section
render imports the view layer on top.  On Windows, antivirus real-time
scanning of a venv's many DLLs commonly turns that ~1 s into several
seconds, so the *first* sign-in after every service start feels broken
while later ones are fine.

``warm_up()`` does those imports on a daemon thread as soon as the server
starts serving, so they overlap with the user reading the login page
instead of following their click.  Python's per-module import lock makes
concurrent imports from the script thread safe; whichever thread gets
there first does the work and the other waits on the lock.

Only modules that are safe to import off the script thread are warmed —
libraries and stores, not ``ui.*`` views, which may touch Streamlit's
per-thread script context at import.

Process-once guard lives in this module (not app.py) for the same reason
the login throttle does: app.py's globals are recreated on every rerun.
"""
from __future__ import annotations

import threading

_started = False
_lock = threading.Lock()


def _warm_bcrypt_pad() -> None:
    from auth.users import warm_bcrypt
    warm_bcrypt()


# Order: what the first sign-in needs first.  Each step is independent so one
# failure (e.g. an optional package missing) doesn't skip the rest.
_STEPS = (
    lambda: __import__("bcrypt"),
    _warm_bcrypt_pad,
    lambda: __import__("numpy"),
    lambda: __import__("pandas"),
    lambda: __import__("openpyxl"),
    lambda: __import__("po_extractor.store"),
    lambda: __import__("ui.stores"),
)


def _do_warm_up(steps=_STEPS) -> None:
    for step in steps:
        try:
            step()
        except Exception:
            pass   # warming is an optimisation; it must never break the app


def warm_up() -> None:
    """Start the warm-up thread; a no-op after the first call in a process."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_do_warm_up, name="import-warmup",
                     daemon=True).start()
