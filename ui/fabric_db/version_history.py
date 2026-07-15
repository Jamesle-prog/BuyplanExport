"""Fabric-list version history — upload log + incremental diff viewer.

Read-only: the version log (fabric_versions / fabric_version_diff) is never
pruned or manually cleared, unlike the colour-translation audit log — only
the underlying snapshot DATA (fabric_master_snapshot) is bounded to the
current + 3 previous versions (see FabricMasterStore.import_from_xlsx).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.i18n import t


def _fabric_db_version_history(store) -> None:
    versions = store.list_versions(limit=50)
    with st.expander(
        f"📜 {t('Version History')} ({len(versions)})",
        expanded=False,
    ):
        st.caption(t(
            "Every fabric-table upload creates a new version. The current "
            "version plus the 3 most recent previous versions stay fully "
            "browsable below and selectable when generating a buy plan; "
            "older versions' data is pruned automatically, but this log of "
            "who uploaded what and what changed is kept forever."
        ))
        if not versions:
            st.info(t("No uploads recorded yet."))
            return

        for v in versions:
            summary = store.get_diff_summary(v["version_id"])
            badge = (f"+{summary['added']} / -{summary['removed']} / "
                     f"~{summary['changed']}")
            when = str(v["created_at"])[:19].replace("T", " ")
            label = (f"v{v['version_id']} · {when} · {t('by')} {v['uploaded_by']} "
                     f"· {v['source_file'] or '—'} · {badge}")
            with st.expander(label, expanded=False):
                st.caption(
                    f"{t('Rows')}: {v['row_count']:,} · "
                    f"{t('inserted')} {v['inserted']} / "
                    f"{t('updated')} {v['updated']} / "
                    f"{t('skipped')} {v['skipped']}"
                )
                diff_rows = store.get_version_diff(v["version_id"])
                if not diff_rows:
                    st.caption(t(
                        "No changes detected in this version (identical "
                        "data, or the first tracked import)."
                    ))
                    continue
                df = pd.DataFrame([{
                    "Quality No.": d["quality_no"],
                    "Change":      d["change_type"],
                    "Field":       d["field"] or "",
                    "Old":         d["old_value"] or "",
                    "New":         d["new_value"] or "",
                } for d in diff_rows])
                st.dataframe(
                    df, width="stretch", hide_index=True, height=300,
                    column_config={
                        "Quality No.": st.column_config.TextColumn(t("Quality No."), width="medium"),
                        "Change":      st.column_config.TextColumn(t("Change"),      width="small"),
                        "Field":       st.column_config.TextColumn(t("Field"),       width="medium"),
                        "Old":         st.column_config.TextColumn(t("Old value"),   width="medium"),
                        "New":         st.column_config.TextColumn(t("New value"),   width="medium"),
                    },
                )


def _fabric_version_options(store) -> list[tuple[str, int | None]]:
    """Return [(label, version_id_or_None), ...] for a version-picker
    selectbox, newest first, with the latest entry labelled distinctly and
    mapped to ``None`` (so callers pass it straight through as "no override,
    use the live table" — the same meaning as omitting version_id entirely).
    """
    versions = store.list_versions(limit=4)
    options: list[tuple[str, int | None]] = []
    for i, v in enumerate(versions):
        when = str(v["created_at"])[:10]
        if i == 0:
            options.append((f"{t('Latest')} (v{v['version_id']} · {when})", None))
        else:
            options.append((f"v{v['version_id']} · {when}", v["version_id"]))
    if not options:
        options.append((t("Latest"), None))
    return options
