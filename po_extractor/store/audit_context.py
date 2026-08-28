"""Who is acting right now, for the change log.

The stores are deliberately Streamlit-free, so they cannot read
``st.session_state`` to find the signed-in user. Threading a ``username``
argument through every write method would touch a very large surface and would
be silently forgotten by the next writer added -- exactly how the existing
history tables ended up recording *what* changed but not *who*.

Instead the UI stamps the current user once per script run (app.py, right after
the logged-in check) and every store reads it from here.

Thread-local on purpose: Streamlit runs each browser session's script in its
own thread, so a plain module global would leak one user's identity into
another's writes on a shared server -- the exact failure this table exists to
prevent. Streamlit may also REUSE a thread for a different session later, which
is why :func:`set_current_user` is called at the top of every run rather than
once at login: each run overwrites the slot before any store can read a stale
value.

Reading is never fatal: :func:`current_user` returns "" when nothing is set
(a background job, a test, a CLI script), and callers record the empty string
rather than failing the write they were asked to do.
"""
from __future__ import annotations

import threading

_local = threading.local()


def set_current_user(username: str | None) -> None:
    """Record who the current script run belongs to. Call once per run."""
    _local.username = (username or "").strip()


def current_user() -> str:
    """The signed-in user for this thread, or "" if unknown."""
    return getattr(_local, "username", "") or ""


def clear_current_user() -> None:
    """Forget the current user (sign-out, and test isolation)."""
    _local.username = ""
