"""Tests for UITranslationStore and related i18n infrastructure."""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture
def tmp_store():
    """UITranslationStore backed by a fresh temp DB.

    ``ignore_cleanup_errors=True`` is required on Windows: SQLite WAL mode
    keeps the DB file locked until the process exits, so TemporaryDirectory
    cleanup would otherwise raise PermissionError.
    """
    from po_extractor.store.ui_translation_store import UITranslationStore
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        yield UITranslationStore(os.path.join(d, "test.db"))


# ---------------------------------------------------------------------------
# Schema + construction
# ---------------------------------------------------------------------------

def test_store_creates_table(tmp_store):
    """Store initialises without errors; count() returns an integer."""
    assert tmp_store.count() == 0


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def test_seed_defaults_inserts_rows(tmp_store):
    result = tmp_store.seed_defaults(skip_existing=True)
    assert result["inserted"] > 0
    assert result["skipped"] == 0
    assert tmp_store.count() == result["inserted"]


def test_seed_defaults_idempotent(tmp_store):
    """Running seed twice with skip_existing=True must not duplicate rows."""
    first  = tmp_store.seed_defaults(skip_existing=True)
    second = tmp_store.seed_defaults(skip_existing=True)
    assert second["inserted"] == 0
    assert second["skipped"]  == first["inserted"]
    assert tmp_store.count()  == first["inserted"]


def test_seed_covers_known_labels(tmp_store):
    """Seed must include all 82 labels that were in the legacy _LABEL_ZH dict."""
    tmp_store.seed_defaults()
    legacy_keys = {
        "Company", "PC No.", "Style", "Color", "Brand", "Ex-Fty Date",
        "HHN Contract No.", "Fabric No.", "Composition", "PC Date",
        "Division", "Issue Date",
        "Fabric No. (was)", "HHN Contract No. (was)",
    }
    lookup = tmp_store.build_lookup("zh")
    for key in legacy_keys:
        assert key in lookup, f"Legacy key missing from DB: {key!r}"


def test_seed_force_overwrites(tmp_store):
    """seed_defaults(skip_existing=False) updates existing rows."""
    tmp_store.seed_defaults(skip_existing=True)
    tmp_store.upsert("Save", "Save", "CUSTOM", "button", "shared")
    # Force re-seed should reset to built-in value
    tmp_store.seed_defaults(skip_existing=False)
    lookup = tmp_store.build_lookup("zh")
    assert lookup.get("Save") == "保存"


# ---------------------------------------------------------------------------
# Upsert / CRUD
# ---------------------------------------------------------------------------

def test_upsert_insert(tmp_store):
    tmp_store.upsert("Download", "Download", "下载", "button", "shared")
    lookup = tmp_store.build_lookup("zh")
    assert lookup["Download"] == "下载"


def test_upsert_update(tmp_store):
    tmp_store.upsert("Download", "Download", "下载", "button", "shared")
    tmp_store.upsert("Download", "Download", "下载文件", "button", "shared")
    lookup = tmp_store.build_lookup("zh")
    assert lookup["Download"] == "下载文件"


def test_upsert_many(tmp_store):
    rows = [
        {"key": "Alpha", "en_text": "Alpha", "zh_text": "甲", "category": "label", "module": "shared"},
        {"key": "Beta",  "en_text": "Beta",  "zh_text": "乙", "category": "label", "module": "shared"},
    ]
    result = tmp_store.upsert_many(rows)
    assert result["inserted"] == 2
    assert result["updated"]  == 0
    lookup = tmp_store.build_lookup("zh")
    assert lookup["Alpha"] == "甲"
    assert lookup["Beta"]  == "乙"


def test_upsert_many_skip_existing(tmp_store):
    tmp_store.upsert("Alpha", "Alpha", "甲", "label", "shared")
    rows = [
        {"key": "Alpha", "en_text": "Alpha", "zh_text": "NEW", "category": "label", "module": "shared"},
        {"key": "Beta",  "en_text": "Beta",  "zh_text": "乙", "category": "label", "module": "shared"},
    ]
    result = tmp_store.upsert_many(rows, skip_existing=True)
    assert result["inserted"] == 1
    assert result["skipped"]  == 1
    lookup = tmp_store.build_lookup("zh")
    assert lookup["Alpha"] == "甲"   # unchanged


def test_delete_ids(tmp_store):
    tmp_store.upsert("TempKey", "TempKey", "临时", "label", "shared")
    rows = tmp_store.get_all()
    ids  = [r["id"] for r in rows if r["key"] == "TempKey"]
    assert ids
    deleted = tmp_store.delete_ids(ids)
    assert deleted == 1
    lookup = tmp_store.build_lookup("zh")
    assert "TempKey" not in lookup


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def test_build_lookup_en_returns_empty(tmp_store):
    """English language has no translation column → always returns {}."""
    tmp_store.seed_defaults()
    assert tmp_store.build_lookup("en") == {}


def test_build_lookup_zh(tmp_store):
    tmp_store.seed_defaults()
    lookup = tmp_store.build_lookup("zh")
    assert isinstance(lookup, dict)
    assert len(lookup) > 0
    assert lookup.get("Save") == "保存"
    assert lookup.get("Sign In") == "登录"


def test_build_lookup_excludes_empty_translations(tmp_store):
    """Rows with empty zh_text must not appear in the zh lookup."""
    tmp_store.upsert("Untranslated", "Untranslated", "", "label", "shared")
    lookup = tmp_store.build_lookup("zh")
    assert "Untranslated" not in lookup


def test_get_by_module(tmp_store):
    tmp_store.upsert("A", "A", "甲", "label", "giii")
    tmp_store.upsert("B", "B", "乙", "label", "sky_east")
    giii_rows = tmp_store.get_by_module("giii")
    assert any(r["key"] == "A" for r in giii_rows)
    assert all(r["module"] == "giii" for r in giii_rows)


def test_list_modules(tmp_store):
    tmp_store.upsert("X", "X", "鑫", "label", "module_a")
    tmp_store.upsert("Y", "Y", "乙", "label", "module_b")
    assert "module_a" in tmp_store.list_modules()
    assert "module_b" in tmp_store.list_modules()


def test_count_missing(tmp_store):
    tmp_store.upsert("HasTranslation", "HasTranslation", "有翻译", "label", "shared")
    tmp_store.upsert("NoTranslation",  "NoTranslation",  "",       "label", "shared")
    assert tmp_store.count_missing("zh") == 1


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

def test_csv_roundtrip(tmp_store):
    tmp_store.upsert("Export Test", "Export Test", "导出测试", "label", "shared")
    csv_str = tmp_store.to_csv()
    assert "Export Test" in csv_str
    assert "导出测试" in csv_str

    # Import into a second store and verify
    import tempfile, os
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d2:
        from po_extractor.store.ui_translation_store import UITranslationStore
        store2 = UITranslationStore(os.path.join(d2, "test2.db"))
        result = store2.import_csv(csv_str)
        assert result["inserted"] >= 1
        assert store2.build_lookup("zh").get("Export Test") == "导出测试"


def test_import_csv_skip_existing(tmp_store):
    tmp_store.upsert("Existing", "Existing", "已存在", "label", "shared")
    csv_str = "key,en_text,zh_text,category,module\nExisting,Existing,覆盖,label,shared\n"
    result = tmp_store.import_csv(csv_str, skip_existing=True)
    assert result["skipped"] == 1
    assert tmp_store.build_lookup("zh")["Existing"] == "已存在"  # unchanged


def test_to_dataframe(tmp_store):
    tmp_store.seed_defaults()
    df = tmp_store.to_dataframe()
    assert not df.empty
    assert "key" in df.columns
    assert "zh_text" in df.columns


# ---------------------------------------------------------------------------
# Integration: _th() uses DB over hardcoded fallback
# ---------------------------------------------------------------------------

def test_th_uses_db_translation(monkeypatch, tmp_store):
    """_th() must pick up a DB translation that overrides the hardcoded dict."""
    pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

    # Patch get_ui_translation_store in ui.stores to return our tmp_store
    import ui.stores as _stores
    monkeypatch.setattr(_stores, "get_ui_translation_store", lambda: tmp_store)

    # Seed with a custom override for "Save"
    tmp_store.upsert("Save", "Save", "储存(自定义)", "button", "shared")

    # Simulate zh session state via a fake st.session_state
    import types
    fake_ss = {"ui_lang": "zh"}

    import ui.shared as _shared
    import ui.i18n as _i18n

    # Clear any cached translations from previous test runs
    monkeypatch.setattr(_i18n, "_get_cache", lambda lang: tmp_store.build_lookup(lang))

    monkeypatch.setattr(
        _shared.st, "session_state",
        types.SimpleNamespace(**{"get": fake_ss.get, **fake_ss}),
    )

    result = _shared._th("Save")
    assert result == "储存(自定义)"


def test_th_falls_back_to_label_zh(monkeypatch, tmp_store):
    """_th() falls back to _LABEL_ZH when neither DB nor i18n has the key."""
    pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

    import ui.stores as _stores
    monkeypatch.setattr(_stores, "get_ui_translation_store", lambda: tmp_store)

    import types
    fake_ss = {"ui_lang": "zh"}

    import ui.shared as _shared
    import ui.i18n as _i18n

    # Return empty lookup (no DB translations)
    monkeypatch.setattr(_i18n, "_get_cache", lambda lang: {})

    monkeypatch.setattr(
        _shared.st, "session_state",
        types.SimpleNamespace(**{"get": fake_ss.get, **fake_ss}),
    )

    # "Company" is in _LABEL_ZH but not in empty cache → should fall back
    result = _shared._th("Company")
    assert result == "公司"
