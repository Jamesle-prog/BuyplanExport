"""Release changelog tab — version history for PO Extractor."""
from __future__ import annotations

import streamlit as st

# Entries live in ui/changelog_data.py (data only, newest first).
from ui.changelog_data import CHANGELOG as _CHANGELOG

# ---------------------------------------------------------------------------
# Type display config
# ---------------------------------------------------------------------------
_TYPE_CONFIG = {
    "feat":     ("🌟", "#0d6efd", "Feature"),
    "fix":      ("🐛", "#dc3545", "Fix"),
    "perf":     ("⚡", "#fd7e14", "Performance"),
    "refactor": ("♻️",  "#6c757d", "Refactor"),
    "security": ("🔒", "#198754", "Security"),
    "docs":     ("📄", "#6610f2", "Docs"),
}


# How many of the newest versions render outside the "Older versions"
# expander.  Everything is still just markdown -- but concatenated into ONE
# st.markdown call per group instead of ~4 elements per version, which at
# 200+ versions was ~900 DOM-mounted Streamlit elements on every rerun.
_RECENT_VERSION_COUNT = 20

_VERSION_SEPARATOR = (
    "<hr style='margin:0.9rem 0; border:none; "
    "border-top:1px solid rgba(128,128,128,0.35);'>"
)


def _version_card_html(entry: dict) -> str:
    """Build one version's card (header + typed entry lines) as an HTML string."""
    parts = [
        f"<div style='display:flex; align-items:baseline; gap:0.75rem;'>"
        f"<span style='font-size:1.15rem; font-weight:700;'>v{entry['version']}</span>"
        f"<span style='color:#888; font-size:0.85rem;'>{entry['date']}</span>"
        f"</div>"
    ]
    for item in entry["entries"]:
        ttype = item.get("type", "feat")
        icon, color, label = _TYPE_CONFIG.get(ttype, ("•", "#333", ttype))
        parts.append(
            f"<div style='margin: 0.15rem 0 0.15rem 1rem; font-size:0.92rem;'>"
            f"<span style='color:{color}; font-weight:600; margin-right:0.4rem'>{icon}</span>"
            f"{item['text']}"
            f"</div>"
        )
    return "".join(parts)


def show_changelog_tab() -> None:
    """Render the Releases / Changelog tab."""
    st.markdown("## 🔖 Release History")
    st.caption("All versions of PO Extractor, newest first.")

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_cols = st.columns(len(_TYPE_CONFIG))
    for col, (ttype, (icon, color, label)) in zip(legend_cols, _TYPE_CONFIG.items()):
        col.markdown(
            f"<span style='color:{color}; font-weight:600'>{icon} {label}</span>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Version cards ─────────────────────────────────────────────────────────
    recent = _CHANGELOG[:_RECENT_VERSION_COUNT]
    older  = _CHANGELOG[_RECENT_VERSION_COUNT:]

    st.markdown(
        _VERSION_SEPARATOR.join(_version_card_html(e) for e in recent),
        unsafe_allow_html=True,
    )

    if older:
        st.divider()
        with st.expander(
            f"📦 Older versions (v{older[-1]['version']} – v{older[0]['version']} · "
            f"{len(older)} releases)",
            expanded=False,
        ):
            st.markdown(
                _VERSION_SEPARATOR.join(_version_card_html(e) for e in older),
                unsafe_allow_html=True,
            )
