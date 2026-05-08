"""Canonical store factories for po_extractor.

Every code path that needs a store goes through one of these factories.
This eliminates the class of bugs where a function importable from one
package (e.g. ``ui.stores.get_fabric_master_store``) silently fails when
imported from another (e.g. ``po_extractor.store.fabric_master_store``).

Streamlit-specific caching wrappers live in ``ui/stores.py`` and call into
these factories — that file is the *only* place ``@st.cache_resource``
should appear; everything else uses the plain factories below.
"""
from __future__ import annotations

from .po_store import POStore
from .sky_east_store import SkyEastStore
from .fabric_master_store import FabricMasterStore
from .color_translation_store import ColorTranslationStore
from .boat_sample_store import BoatSampleStore
from .ui_translation_store import UITranslationStore
from .app_settings_store import AppSettingsStore


def _db_path() -> str:
    """Return the canonical DB path.  Lazy import keeps po_extractor.store
    importable when po_extractor.config is initialised later (e.g. tests).
    """
    from ..config import DB_PATH
    return DB_PATH


# ── Public factory API ───────────────────────────────────────────────────────

def get_po_store() -> POStore:
    """Return a fresh POStore wired to the canonical DB."""
    return POStore(_db_path())


def get_sky_east_store() -> SkyEastStore:
    """Return a fresh SkyEastStore wired to the canonical DB."""
    return SkyEastStore(_db_path())


def get_fabric_master_store() -> FabricMasterStore:
    """Return a fresh FabricMasterStore wired to the centralised fabric master DB.

    The DB path is resolved fresh on every call via ``get_fabric_db_path()``,
    so an admin can change it in the Settings UI and the new path takes effect
    immediately without an app restart.

    The fabric master lives in its own dedicated file (``fabric_master.db`` by
    default) rather than in ``po_history.db`` so that other applications can
    point their own ``FabricMasterStore`` — or the standalone
    ``FabricMasterClient`` — at the same file and share the data.

    Auto-migration
    --------------
    On the first call after the fabric DB was split out (v1.7.2), the new
    ``fabric_master.db`` is empty but the legacy ``po_history.db`` still holds
    all the fabric records.  This factory detects that condition (new DB empty,
    legacy DB non-empty, different paths) and automatically copies the data
    so exports continue to work without manual admin intervention.

    NOTE: this function previously existed only in ``ui.stores`` —
    importing it from ``po_extractor.store.fabric_master_store`` raised
    ``ImportError`` which was silently swallowed by callers, leaving the
    fabric_master cache empty (BUG fixed in v1.53.0).  Always import via
    ``from po_extractor.store import get_fabric_master_store``.
    """
    from ..config import get_fabric_db_path
    fabric_path = get_fabric_db_path()
    store = FabricMasterStore(fabric_path)
    # One-time auto-migration: if the dedicated fabric DB is empty and the
    # legacy po_history.db still has fabric records, copy them over silently.
    if fabric_path != _db_path() and store.count() == 0:
        if _legacy_has_fabric_data(_db_path()):
            try:
                FabricMasterStore.migrate_from_db(_db_path(), fabric_path)
            except Exception:
                pass  # Never crash the app over a migration failure
    return store


def _legacy_has_fabric_data(db_path: str) -> bool:
    """Return True if *db_path* contains a non-empty fabric_master table."""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        has_table = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='fabric_master'"
        ).fetchone()
        if not has_table:
            conn.close()
            return False
        count = conn.execute("SELECT COUNT(*) FROM fabric_master").fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def get_color_translation_store() -> ColorTranslationStore:
    """Return a fresh ColorTranslationStore wired to the canonical DB."""
    return ColorTranslationStore(_db_path())


def get_boat_sample_store() -> BoatSampleStore:
    """Return a fresh BoatSampleStore wired to the canonical DB."""
    return BoatSampleStore(_db_path())


def get_ui_translation_store() -> UITranslationStore:
    """Return a fresh UITranslationStore wired to the canonical DB."""
    return UITranslationStore(_db_path())


def get_app_settings_store() -> AppSettingsStore:
    """Return a fresh AppSettingsStore wired to the canonical DB."""
    return AppSettingsStore(_db_path())


# ── Cross-store helpers ──────────────────────────────────────────────────────

def list_all_brands(company: str) -> list[str]:
    """Return the union of brands known under *company* across every store
    that holds brand data.

    Sources (deduplicated, sorted):
      • ColorTranslationStore.list_brands(client=company)
      • BoatSampleStore.list_known_brands(company)

    Use this anywhere you need a complete brand picker — it ensures that
    brands auto-registered by one source (e.g. boat-sample requirements
    inserted when Sky East orders are loaded) still appear in pickers
    powered by another source.
    """
    if not company:
        return []
    seen: set[str] = set()
    seen.update(get_color_translation_store().list_brands(client=company) or [])
    seen.update(get_boat_sample_store().list_known_brands(company) or set())
    return sorted(seen)


__all__ = [
    "POStore", "SkyEastStore", "FabricMasterStore",
    "ColorTranslationStore", "BoatSampleStore", "UITranslationStore",
    "AppSettingsStore",
    "get_po_store", "get_sky_east_store", "get_fabric_master_store",
    "get_color_translation_store", "get_boat_sample_store",
    "get_ui_translation_store", "get_app_settings_store",
    "list_all_brands",
]
