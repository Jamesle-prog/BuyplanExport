"""Sidebar CPRS server-status indicator.

Gives operators an at-a-glance signal that the CPRS knowledge-base API is up,
so a whole-server outage is obvious immediately instead of surfacing only when
a requirements document or buy plan comes back with blank requirement columns.

The health probe is cached with a short TTL, so it costs one request every
``_TTL`` seconds regardless of how often Streamlit reruns the sidebar; a manual
Refresh clears the cache. The probe uses a short timeout so a *down* server
never freezes the sidebar for the client's full 8 s (connection-refused is
instant anyway; the timeout only bounds a host that accepts but hangs).
"""
from __future__ import annotations

import streamlit as st

from ui.i18n import t

_TTL = 20            # seconds a health result is trusted before re-probing
_PROBE_TIMEOUT = 3.0  # keep the sidebar snappy when CPRS is unreachable


@st.cache_data(ttl=_TTL, show_spinner=False)
def _probe(base: str, api_key: str) -> dict:
    """Health snapshot for (base, api_key), cached per-args with a TTL so every
    session shares one probe. Never raises — a failure is reported as down with
    the reason."""
    from po_extractor.utils.cprs_client import CprsClient
    try:
        return CprsClient(base, api_key, timeout=_PROBE_TIMEOUT).health_info()
    except Exception as exc:                       # never break the sidebar
        return {"ok": False, "status": "", "db": "", "version": "",
                "message": f"Could not reach CPRS: {exc}"}


def _host(base: str) -> str:
    """Bare host:port for a compact caption (drop scheme + path)."""
    return str(base or "").split("://")[-1].split("/")[0]


def render_sidebar_cprs_status() -> None:
    """Render the CPRS status line in the sidebar. Safe to call every rerun."""
    from po_extractor.store import get_app_settings_store
    from po_extractor.store.app_settings_store import (
        KEY_CPRS_BASE_URL, KEY_CPRS_API_KEY,
    )
    try:
        s = get_app_settings_store()
        base = (s.get(KEY_CPRS_BASE_URL, "") or "").strip()
        api_key = s.get(KEY_CPRS_API_KEY, "") or ""
    except Exception:
        base, api_key = "", ""

    st.markdown(f"**{t('CPRS server')}**")
    if not base:
        st.caption(f"⚪ {t('Not configured')}")
        return

    info = _probe(base, api_key)
    if info.get("ok"):
        ver = info.get("version") or ""
        st.markdown(f"🟢 **{t('Online')}**" + (f" · v{ver}" if ver else ""))
        st.caption(f"{_host(base)} · db: {info.get('db', '?')}")
    else:
        st.markdown(f"🔴 **{t('Offline')}**")
        # The reason (connection refused / HTTP status / …) is the whole point.
        st.caption(f"{_host(base)} — {info.get('message', '')}")

    if st.button(f"🔄 {t('Refresh')}", key="cprs_status_refresh",
                 use_container_width=True):
        _probe.clear()
        st.rerun()
