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


def count_fabric_rows(db_path: str) -> int:
    """Return the row count of the ``fabric_master`` table in *db_path*.

    Returns 0 when the table doesn't exist or the DB can't be opened.
    Single source of truth — both auto-migration logic and the admin
    Settings UI ("legacy DB inspector") rely on this helper.
    """
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        try:
            has_table = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='fabric_master'"
            ).fetchone()
            if not has_table:
                return 0
            return conn.execute("SELECT COUNT(*) FROM fabric_master").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def _legacy_has_fabric_data(db_path: str) -> bool:
    """Backward-compat shim — prefer :func:`count_fabric_rows` for new code."""
    return count_fabric_rows(db_path) > 0


# Marker key written to the fabric DB after auto-migration so subsequent
# factory calls skip the legacy probe entirely (saves two SQLite opens
# per ``get_fabric_master_store()`` on a fresh-but-intentionally-empty DB).
_FABRIC_MIGRATION_PRAGMA = 1   # PRAGMA user_version value after migration


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
    so exports continue to work without manual admin intervention.  Once a
    migration has run, ``PRAGMA user_version`` on the fabric DB is set so
    later calls skip the check entirely.
    """
    import sqlite3
    from contextlib import closing
    from ..config import get_fabric_db_path
    fabric_path = get_fabric_db_path()
    store = FabricMasterStore(fabric_path)

    if fabric_path == _db_path():
        return store   # No split — single-DB mode, nothing to migrate.

    # Fast path: marker already set → migration ran (or wasn't needed).
    # NOTE: ``with sqlite3.connect(...) as conn`` only commits/rolls back; it
    # does NOT close the connection.  We wrap in contextlib.closing() so the
    # handle is released — without this every factory call leaked one fd.
    try:
        with closing(sqlite3.connect(fabric_path)) as _probe:
            uv = _probe.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        uv = 0
    if uv >= _FABRIC_MIGRATION_PRAGMA:
        return store

    # Slow path: only on first run after the v1.7.2 split.
    legacy_count = count_fabric_rows(_db_path())
    needs_migration = store.count() == 0 and legacy_count > 0
    migration_ok = True
    if needs_migration:
        try:
            FabricMasterStore.migrate_from_db(_db_path(), fabric_path)
        except Exception as _exc:
            migration_ok = False
            # Surface the cause — silent failure here would leave the buy plan
            # exporting with empty 综合keys with no signal to the user.
            import warnings as _w
            _w.warn(f"[fabric_master] auto-migration failed: {_exc!r}")

    # Only stamp the marker on success (or when no migration was needed).
    # Stamping on partial-failure would lock in a half-copied DB and prevent
    # the next factory call from retrying.
    if migration_ok:
        try:
            with closing(sqlite3.connect(fabric_path)) as _stamp:
                _stamp.execute(f"PRAGMA user_version = {_FABRIC_MIGRATION_PRAGMA}")
                _stamp.commit()
        except sqlite3.Error:
            pass
    return store


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
    "list_all_brands", "count_fabric_rows",
]
