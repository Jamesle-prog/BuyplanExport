"""Admin panel: UI Translation Management (🌐 Translations tab).

Allows admins to:
  • Browse all translation strings, filtered by module / category
  • Edit Chinese translations inline via st.data_editor
  • Add individual new strings
  • Import / export translations as CSV
  • Seed missing built-in defaults
  • Clear the session cache so changes take effect immediately
"""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from ui.i18n import clear_cache, supported_langs, t
from ui.shared import lazy_sections, CSV_MIME
from ui.stores import get_ui_translation_store


# ── Constants ─────────────────────────────────────────────────────────────────

_LANG_DISPLAY = {"zh": "Chinese (中文)"}

_EDIT_COLS = {
    "key":      st.column_config.TextColumn("Key (English)",    width="large",  disabled=True),
    "zh_text":  st.column_config.TextColumn("Chinese (中文)",   width="large"),
    "category": st.column_config.TextColumn("Category",         width="small",  disabled=True),
    "module":   st.column_config.TextColumn("Module",           width="small",  disabled=True),
}


# ── Main entry point ──────────────────────────────────────────────────────────

def show_i18n_admin() -> None:
    """Render the full Translations admin panel."""
    store = get_ui_translation_store()

    st.subheader("🌐 " + t("UI Translation Management"))
    st.caption(
        f"**{store.count()} {t('keys')}** · "
        f"**{store.count_missing('zh')} {t('missing Chinese translations')}** · "
        + t("Changes take effect immediately after saving.")
    )

    lazy_sections([
        (f"📋 {t('Browse & Edit')}",    lambda: _show_browse_tab(store)),
        (f"➕ {t('Add Key')}",             lambda: _show_add_tab(store)),
        (f"📤 {t('Import / Export')}", lambda: _show_import_export_tab(store)),
        (f"🌱 {t('Seed Defaults')}",   lambda: _show_seed_tab(store)),
    ], key="admin_i18n_section_nav")


# ── Browse & Edit ─────────────────────────────────────────────────────────────

def _show_browse_tab(store) -> None:
    all_modules    = ["(all)"] + store.list_modules()
    all_categories = ["(all)"] + store.list_categories()

    f1, f2, f3 = st.columns([2, 2, 3])
    with f1:
        sel_module = st.selectbox(t("Module"), all_modules, key="i18n_mod_filter")
    with f2:
        sel_cat = st.selectbox(t("Category"), all_categories, key="i18n_cat_filter")
    with f3:
        search = st.text_input(t("Search (key / Chinese text)"), key="i18n_search",
                               placeholder=t("type to filter..."))

    rows = (store.get_by_module(sel_module)
            if sel_module != "(all)" else store.get_all())

    if sel_cat != "(all)":
        rows = [r for r in rows if r.get("category") == sel_cat]

    if search:
        q = search.lower()
        rows = [
            r for r in rows
            if q in r.get("key", "").lower() or q in r.get("zh_text", "").lower()
        ]

    if not rows:
        st.info(t("No translations match the current filter."))
        return

    st.caption(f"{len(rows)} " + t("row(s) shown"))

    df = pd.DataFrame(rows)[["key", "zh_text", "category", "module"]]

    edited = st.data_editor(
        df,
        column_config=_EDIT_COLS,
        width="stretch",
        hide_index=True,
        key="i18n_editor",
        num_rows="fixed",
    )

    sv1, sv2 = st.columns([1, 4])
    with sv1:
        if st.button("💾 " + t("Save changes"), type="primary",
                     width="stretch", key="i18n_save"):
            saved = 0
            for _, row in edited.iterrows():
                key     = str(row.get("key",      "") or "").strip()
                zh_text = str(row.get("zh_text",  "") or "").strip()
                cat     = str(row.get("category", "") or "").strip()
                mod     = str(row.get("module",   "") or "").strip()
                if not key:
                    continue
                store.upsert(key, key, zh_text, cat, mod)
                saved += 1
            clear_cache("zh")
            st.success(f"{t('Saved')} {saved} " + t("translation(s). Cache cleared."))
            st.rerun()

    with sv2:
        # Delete section (separate expander to avoid accidental clicks)
        with st.expander("🗑 " + t("Delete selected keys")):
            to_del = st.multiselect(
                t("Keys to delete"),
                [r["key"] for r in rows],
                key="i18n_del_keys",
            )
            if st.button(t("Delete"), disabled=not to_del,
                         type="primary", key="i18n_del_btn"):
                with store._conn() as conn:
                    ph = ",".join("?" * len(to_del))
                    conn.execute(
                        f"DELETE FROM ui_translations WHERE key IN ({ph})",
                        to_del,
                    )
                clear_cache("zh")
                st.success(f"{t('Deleted')} {len(to_del)} " + t("key(s). Cache cleared."))
                st.rerun()


# ── Add single key ────────────────────────────────────────────────────────────

def _show_add_tab(store) -> None:
    st.markdown(f"**{t('Add a new translation key')}**")

    with st.form("i18n_add_form", clear_on_submit=True):
        key      = st.text_input(t("Key (English text, used in UI)"),
                                 placeholder="e.g. Download Report")
        zh_text  = st.text_input(t("Chinese translation (中文)"),
                                 placeholder="e.g. 下载报告")
        c1, c2 = st.columns(2)
        with c1:
            category = st.selectbox(t("Category"),
                                    ["label", "button", "header",
                                     "message", "caption", ""],
                                    key="i18n_add_cat")
        with c2:
            module   = st.selectbox(t("Module"),
                                    ["shared", "giii", "sky_east",
                                     "admin", "summary", ""],
                                    key="i18n_add_mod")
        submitted = st.form_submit_button(t("Add"), type="primary",
                                          width="stretch")

    if submitted:
        key = key.strip()
        if not key:
            st.error(t("Key cannot be empty."))
        else:
            store.upsert(key, key, zh_text.strip(), category, module)
            clear_cache("zh")
            st.success(f"{t('Added key')} **{key!r}** → **{zh_text!r}**. " + t("Cache cleared."))


# ── Import / Export ───────────────────────────────────────────────────────────

def _show_import_export_tab(store) -> None:
    exp_col, imp_col = st.columns(2)

    with exp_col:
        st.markdown(f"**{t('Export')}**")
        st.caption(t("Download all translations as a CSV file."))
        if st.button(t("Generate CSV"), key="i18n_export_btn",
                     width="stretch"):
            csv_bytes = store.to_csv().encode("utf-8-sig")
            st.download_button(
                "📥 " + t("Download translations.csv"),
                data=csv_bytes,
                file_name="ui_translations.csv",
                mime=CSV_MIME,
                width="stretch",
                key="i18n_dl_btn",
            )

    with imp_col:
        st.markdown(f"**{t('Import')}**")
        st.caption(t(
            "Upload a CSV with columns: `key`, `en_text`, `zh_text`, "
            "`category`, `module`.  Existing keys are **updated** unless "
            "the *Skip existing* option is checked."
        ))
        uploaded = st.file_uploader(
            t("CSV file"),
            type=["csv"],
            key="i18n_import_file",
            label_visibility="collapsed",
        )
        skip = st.checkbox(t("Skip existing keys"), value=False,
                           key="i18n_skip_existing")
        if uploaded and st.button(t("Import"), type="primary",
                                  width="stretch", key="i18n_import_btn"):
            try:
                csv_text = uploaded.getvalue().decode("utf-8-sig")
                result   = store.import_csv(csv_text, skip_existing=skip)
                clear_cache("zh")
                st.success(
                    f"{t('Import complete')} — "
                    f"**{result['inserted']}** {t('inserted')}, "
                    f"**{result['updated']}** {t('updated')}, "
                    f"**{result['skipped']}** {t('skipped')}. "
                    + t("Cache cleared.")
                )
            except Exception as exc:
                st.error(t("Import failed:") + f" {exc}")


# ── Seed defaults ─────────────────────────────────────────────────────────────

def _show_seed_tab(store) -> None:
    st.markdown(f"**{t('Seed built-in default translations')}**")
    st.caption(
        f"{t('The system ships with')} **{len(__import__('po_extractor.store.ui_translation_store', fromlist=['_SEED'])._SEED)}** "  # noqa: E501
        + t("built-in translation strings.  "
            "Run this to populate any that are missing from the database — "
            "already-present keys are never overwritten.")
    )

    missing = store.count_missing("zh")
    total   = store.count()
    st.metric(t("Total keys in DB"),       total)
    st.metric(t("Missing Chinese (zh)"),   missing)

    if st.button("🌱 " + t("Seed missing defaults"), type="primary",
                 width="stretch", key="i18n_seed_btn"):
        result = store.seed_defaults(skip_existing=True)
        clear_cache("zh")
        st.success(
            f"{t('Seeded')} **{result['inserted']}** {t('new key(s)')} · "
            f"**{result['skipped']}** {t('already existed.')} "
            + t("Cache cleared.")
        )
        st.rerun()

    st.divider()
    st.markdown(f"**{t('Force re-seed (overwrite existing)')}**")
    st.caption("⚠️ " + t(
        "Resets ALL built-in strings to their default Chinese translations, "
        "overwriting any manual edits to those keys."
    ))
    with st.expander(t("Force re-seed (destructive)")):
        if st.button("⚠️ " + t("Force re-seed all defaults"),
                     type="primary", key="i18n_force_seed"):
            result = store.seed_defaults(skip_existing=False)
            clear_cache("zh")
            # seed_defaults now reports inserted/updated separately (existing
            # rows are UPDATEd, not counted as "inserted") — sum both for the
            # total-processed count this message has always shown.
            total_seeded = result['inserted'] + result.get('updated', 0)
            st.success(
                f"{t('Force-seeded')} **{total_seeded}** " + t("key(s). Cache cleared.")
            )
            st.rerun()

    st.divider()
    st.markdown(f"**{t('Clear translation cache')}**")
    st.caption(t("Forces the next page load to re-read all translations from the DB."))
    if st.button("🔄 " + t("Clear cache"), width="content", key="i18n_clear_cache"):
        clear_cache()
        st.success(t("Translation cache cleared."))
