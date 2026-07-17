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
            "Every data change creates a new version — an upload whose "
            "contents actually differ from the latest list, or a manual "
            "record deletion. Re-uploading an identical file does not. The "
            "current version plus the 3 most recent previous versions stay "
            "fully browsable below and selectable when generating a buy "
            "plan; older versions' data is pruned automatically, but this "
            "log of who changed what is kept forever."
        ))
        if not versions:
            st.info(t("No uploads recorded yet."))
            return

        latest_id = versions[0]["version_id"]
        from po_extractor.store._fabric_version_schema import _SNAPSHOT_KEEP_VERSIONS
        _restorable_min = latest_id - _SNAPSHOT_KEEP_VERSIONS + 1

        for v in versions:
            summary = store.get_diff_summary(v["version_id"])
            badge = (f"+{summary['added']} / -{summary['removed']} / "
                     f"~{summary['changed']}")
            when = str(v["created_at"])[:19].replace("T", " ")
            label = (f"v{v['version_id']} · {when} · {t('by')} {v['uploaded_by']} "
                     f"· {v['source_file'] or '—'} · {badge}")
            with st.expander(label, expanded=False):
                _review_note = ""
                if v.get("approved_by"):
                    _review_note = f" · {t('approved by')} {v['approved_by']}"
                    if v.get("review_comment"):
                        _review_note += f" ({v['review_comment']})"
                st.caption(
                    f"{t('Rows')}: {v['row_count']:,} · "
                    f"{t('inserted')} {v['inserted']} / "
                    f"{t('updated')} {v['updated']} / "
                    f"{t('skipped')} {v['skipped']}"
                    + _review_note
                )
                # Rollback: stage this version's snapshot as a full-replacement
                # proposal through the same review gate as any upload.
                if v["version_id"] != latest_id and v["version_id"] >= _restorable_min:
                    if st.button(
                        f"↩ {t('Restore this version (submits for review)')}",
                        key=f"fabric_db_restore_{v['version_id']}",
                    ):
                        from ui.session_keys import SK
                        from ui.fabric_db.import_section import _current_user
                        try:
                            r = store.propose_restore(v["version_id"],
                                                      proposed_by=_current_user())
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            if r.get("blocked_by_pending"):
                                st.error(t(
                                    "Another proposal is already awaiting review — "
                                    "resolve it first."
                                ))
                            elif r.get("unchanged"):
                                st.info(t(
                                    "This version matches the current data — "
                                    "nothing to restore."
                                ))
                            else:
                                st.session_state[SK.FABRIC_DB_FLASH] = {
                                    "kind": "info",
                                    "text": (
                                        f"📋 Restore of v{v['version_id']} submitted "
                                        f"for review — an admin must approve before "
                                        f"it takes effect."
                                    ),
                                }
                                st.rerun()
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
