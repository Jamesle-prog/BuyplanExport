"""Import, add, update, and delete fabric records."""
from __future__ import annotations

import os
import string
import tempfile
import time

import pandas as pd
import streamlit as st

from ui.i18n import t
from ui.shared import fragment_rerun

from auth.users import is_admin
from ui.fabric_db._shared import FABRIC_DB_LIST_RENAME
from ui.session_keys import SK


def _current_user() -> str:
    return str(st.session_state.get(SK.USERNAME) or "system").strip() or "system"


def _col_letter(n: int) -> str:
    letters = ""
    while n:
        n, r = divmod(n - 1, 26)
        letters = string.ascii_uppercase[r] + letters
    return letters


def _fabric_db_show_flash() -> None:
    """Render (and clear) the outcome of the last import/delete action.

    The action handlers end with ``st.rerun()`` (to refresh the record count,
    version history, etc.), which discards everything rendered in the same
    run -- so success/info banners written just before it only flashed for a
    moment. Stash them in session state instead and render on the NEXT run.
    """
    flash = st.session_state.pop(SK.FABRIC_DB_FLASH, None)
    if not flash:
        return
    kind = flash.get("kind", "info")
    (st.success if kind == "success" else st.info)(flash["text"])
    col_map = flash.get("col_map") or {}
    if col_map:
        with st.expander(t("🗂 Detected column layout"), expanded=False):
            rows = [
                {"Column": _col_letter(c), "Field": f}
                for f, c in sorted(col_map.items(), key=lambda x: x[1])
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                         width="content")
            unmatched = flash.get("unmatched") or []
            if unmatched:
                st.caption(
                    "⚠️ Unrecognised headers (not mapped to any field): "
                    + ", ".join(f"Col {_col_letter(c)} '{h}'"
                                for c, h in unmatched[:10])
                )


def _fabric_db_do_propose(store, uploaded, clear_first: bool = False) -> None:
    """Write *uploaded* to a temp file and SUBMIT it for review.

    Nothing touches the live fabric table here -- the file is parsed,
    quality-checked, diffed against the latest version, and staged as a
    pending proposal that a reviewer must approve (see
    _fabric_db_pending_review_section).
    """
    with st.spinner("Checking fabric data…"):
        try:
            t0 = time.time()
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(uploaded.getbuffer())
                tmp_path = tmp.name
            try:
                result = store.propose_import(
                    tmp_path, source_file_name=uploaded.name,
                    proposed_by=_current_user(), clear_first=clear_first,
                )
            finally:
                os.unlink(tmp_path)
            m, s = divmod(int(time.time() - t0), 60)

            if result.get("blocked_by_pending"):
                st.error(t(
                    "Another proposal by **{who}** is already awaiting review — "
                    "approve, reject, or cancel it first (see the Pending Review "
                    "panel above)."
                ).format(who=result['pending_proposed_by']))
                return
            if result.get("unchanged"):
                st.session_state[SK.FABRIC_DB_FLASH] = {
                    "kind": "info",
                    "text": (
                        f"ℹ️ Checked in {m}:{s:02d} — the file matches the latest "
                        f"fabric list exactly (v{result['version_id']}); there is "
                        f"nothing to review."
                    ),
                }
                fragment_rerun()
                return

            n_warn = len(result.get("warnings") or [])
            risk_note = " ⚠️ **Bulk change — flagged high-risk.**" if result.get("high_risk") else ""
            st.session_state[SK.FABRIC_DB_FLASH] = {
                "kind": "info",
                "text": (
                    f"📋 Submitted for review in {m}:{s:02d} — "
                    f"**+{result['diff_added']}** new / "
                    f"**-{result['diff_removed']}** removed / "
                    f"**~{result['diff_changed']}** changed across "
                    f"{result['row_count']} row(s)"
                    + (f", {n_warn} data-quality warning(s)" if n_warn else "")
                    + f".{risk_note} An admin must approve before this takes effect."
                ),
                "col_map": result.get("col_map", {}),
                "unmatched": result.get("unmatched_headers", []),
            }
            from po_extractor.utils.notifications import notify_fabric_pending
            notify_fabric_pending(
                _current_user(), result.get("row_count", 0),
                note=(f"+{result['diff_added']} / -{result['diff_removed']} / "
                      f"~{result['diff_changed']}"),
            )
            fragment_rerun()
        except Exception as exc:
            st.error(t("Upload check failed: {exc}").format(exc=exc))


def _fabric_db_pending_review_section(store) -> None:
    """Review panel for the pending fabric-list proposal (if any): metadata,
    data-quality warnings, the full prospective diff, and — for admins —
    Approve / Reject controls (two-person rule: the proposer needs a
    justification comment to self-approve; high-risk bulk changes need an
    explicit acknowledgment). The proposer (or an admin) can withdraw."""
    pending = store.get_pending()
    if not pending:
        return

    user = _current_user()
    admin = is_admin(user)
    mode = "Full replacement (Delete All & Reimport)" if pending["clear_first"] else "Update / Add"
    when = str(pending["created_at"])[:19].replace("T", " ")

    st.warning(t(
        "📋 **Fabric list change awaiting review** — proposed by **{who}** at "
        "{when} · `{file}` · {mode}"
    ).format(who=pending['proposed_by'], when=when,
             file=pending['source_file'] or '—', mode=mode))
    with st.expander(t("Review pending fabric list change"), expanded=True):
        st.markdown(
            f"**+{pending['diff_added']}** new / "
            f"**-{pending['diff_removed']}** removed / "
            f"**~{pending['diff_changed']}** changed "
            f"· {pending['row_count']} row(s) in file"
            + (f" · {pending['skipped']} skipped (no 公司面料编号)" if pending["skipped"] else "")
        )

        warnings = pending.get("warnings") or []
        if warnings:
            with st.expander(t("⚠️ {n} data-quality warning(s)").format(n=len(warnings)), expanded=False):
                for w in warnings:
                    st.markdown(f"- {w}")

        diff_rows = store.get_pending_diff(pending["id"])
        if diff_rows:
            df = pd.DataFrame([{
                "Quality No.": d["quality_no"],
                "Change":      d["change_type"],
                "Field":       d["field"] or "",
                "Old":         d["old_value"] or "",
                "New":         d["new_value"] or "",
            } for d in diff_rows])
            st.dataframe(df, width="stretch", hide_index=True, height=300)
        else:
            st.info(
                t("No differences against the current data any more (the table "
                "may have changed since this was proposed) — approving will "
                "not create a new version.")
            )

        if pending["high_risk"]:
            st.error(
                t("⚠️ **High-risk bulk change** — this proposal removes more than "
                "10 records or touches over 20% of the table.")
            )

        if admin:
            comment = st.text_input(
                "Review comment"
                + (" (required to reject; required to approve your own proposal)"),
                key="fabric_db_review_comment",
            )
            ack_ok = True
            if pending["high_risk"]:
                ack_ok = st.checkbox(
                    t("I understand this is a bulk change and have checked the diff above"),
                    key="fabric_db_review_risk_ack",
                )
            col_a, col_r, col_c = st.columns(3)
            if col_a.button(t("✅ Approve & apply"), type="primary",
                            width="stretch", disabled=not ack_ok,
                            key="fabric_db_review_approve"):
                try:
                    outcome = store.approve_pending(pending["id"], reviewed_by=user,
                                                    comment=comment)
                    st.session_state[SK.FABRIC_DB_FLASH] = {
                        "kind": "success",
                        "text": (
                            f"✅ Approved by {user} — "
                            + (f"no data change (still v{outcome['version_id']})."
                               if outcome["unchanged"] else
                               f"**{outcome['inserted']}** new, "
                               f"**{outcome['updated']}** updated — now "
                               f"v{outcome['version_id']}.")
                        ),
                    }
                    fragment_rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if col_r.button(t("❌ Reject"), width="stretch",
                            key="fabric_db_review_reject"):
                try:
                    store.reject_pending(pending["id"], reviewed_by=user,
                                         comment=comment)
                    st.session_state[SK.FABRIC_DB_FLASH] = {
                        "kind": "info",
                        "text": f"❌ Proposal rejected by {user}: {comment.strip()}",
                    }
                    fragment_rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if (user == pending["proposed_by"] or admin) and \
                    col_c.button(t("↩ Withdraw proposal"), width="stretch",
                                 key="fabric_db_review_cancel"):
                store.cancel_pending(pending["id"], by=user)
                st.session_state[SK.FABRIC_DB_FLASH] = {
                    "kind": "info", "text": "↩ Proposal withdrawn.",
                }
                fragment_rerun()
        else:
            st.info(t("Waiting for an admin to review this change."))
            if user == pending["proposed_by"]:
                if st.button(t("↩ Withdraw my proposal"), key="fabric_db_review_cancel_own"):
                    store.cancel_pending(pending["id"], by=user)
                    st.session_state[SK.FABRIC_DB_FLASH] = {
                        "kind": "info", "text": "↩ Proposal withdrawn.",
                    }
                    fragment_rerun()


def _fabric_db_upload_section(store, count: int) -> None:
    """Single expander with radio-button toggle: Update/Add  vs  Clear All & Reimport.

    Uploads are STAGED for peer review, never applied directly -- and a new
    upload is blocked while another proposal is still awaiting review."""
    with st.expander(t("📂 Import Fabric Table (面料统计表.xlsx)"),
                     expanded=(count == 0)):

        if store.get_pending():
            st.info(
                t("A fabric list change is already awaiting review — approve, "
                "reject, or withdraw it (panel above) before submitting "
                "another upload.")
            )
            return

        st.caption(
            t("🔒 Uploads are submitted for review — an admin must approve the "
            "change before it takes effect. Buy plans keep using the current "
            "approved version until then.")
        )

        mode = st.radio(
            t("Import mode"),
            ["➕ Update / Add", "🗑 Clear All & Reimport"],
            horizontal=True,
            key="fabric_db_import_mode",
            label_visibility="collapsed",
        )

        if mode == "➕ Update / Add":
            st.caption(
                t("Existing records with the same 公司面料编号 will be updated; "
                "new records will be added.  No data is deleted.")
            )
            uploaded = st.file_uploader(
                t("面料统计表.xlsx"),
                type=["xlsx", "xlsm", "xls"],
                key="fabric_db_uploader",
                label_visibility="collapsed",
            )
            if uploaded and st.button(t("📋  Submit for Review"), type="primary",
                                       key="fabric_db_import"):
                _fabric_db_do_propose(store, uploaded)

        else:  # Clear All & Reimport
            st.warning(
                t("**Every existing record will be replaced** by the new file "
                "once the proposal is approved. Use this when the column "
                "layout has changed or you need a clean slate.")
            )
            reimport_file = st.file_uploader(
                t("面料统计表.xlsx (full replacement)"),
                type=["xlsx", "xlsm", "xls"],
                key="fabric_db_reimport_uploader",
                label_visibility="collapsed",
            )
            confirmed = st.checkbox(
                t("I understand approval of this proposal will replace ALL existing fabric records"),
                key="fabric_db_clear_confirm",
            )
            if reimport_file and confirmed:
                if st.button(t("📋  Submit Full Replacement for Review"), type="primary",
                             key="fabric_db_clear_reimport"):
                    _fabric_db_do_propose(store, reimport_file, clear_first=True)
            elif reimport_file and not confirmed:
                st.caption(t("☝️ Tick the checkbox above to enable the button."))


def _fabric_db_delete_section(store) -> None:
    """Expander: search and delete individual fabric records by 公司面料编号."""
    with st.expander(t("🗑 Delete Selected Records"), expanded=False):
        st.caption(
            t("Search for fabrics to delete.  Select one or more rows, then confirm deletion.")
        )

        del_q = st.text_input(
            t("Search by 公司面料编号, composition, or supplier"),
            placeholder="e.g. BO-DW240485 · Cotton · 德帽",
            key="fabric_db_del_search",
        )

        if not del_q.strip():
            st.info(t("Enter a search term above to find records."))
            return

        rows = store.search(del_q.strip(), limit=200)
        if not rows:
            st.warning(t("No records match your search."))
            return

        df = pd.DataFrame(rows)
        show_cols = [c for c in FABRIC_DB_LIST_RENAME if c in df.columns]
        display_df = df[show_cols].rename(columns=FABRIC_DB_LIST_RENAME)

        # Let the user pick rows via multiselect on quality_no
        all_qnos = df["quality_no"].tolist()
        selected = st.multiselect(
            t("Select record(s) to delete ({n} found):").format(n=len(all_qnos)),
            options=all_qnos,
            key="fabric_db_del_sel",
        )

        # Show the full table for reference
        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            column_config={
                "综合标识 Key": st.column_config.TextColumn(width="large"),
                "克重 GSM":    st.column_config.NumberColumn(format="%.0f"),
                "有效门幅 CM": st.column_config.NumberColumn(format="%.0f"),
                "烫缩率":      st.column_config.NumberColumn(format="%.2f"),
                "短码率":      st.column_config.NumberColumn(format="%.2f"),
            },
        )

        if not selected:
            return

        st.warning(f"**{len(selected)}** record(s) selected for deletion: "
                   + ", ".join(f"`{q}`" for q in selected[:10])
                   + (" …" if len(selected) > 10 else ""))

        if st.button(t("🗑️ Delete {n} record(s)").format(n=len(selected)), type="primary",
                     key="fabric_db_del_confirm"):
            deleted = store.delete_by_quality_nos(selected)
            st.session_state[SK.FABRIC_DB_FLASH] = {
                "kind": "success",
                "text": (f"✅ {deleted} record(s) deleted. The deletion is "
                         f"recorded in the version history below."),
            }
            # Clear selection and rerun
            st.session_state.pop("fabric_db_del_sel", None)
            fragment_rerun()
