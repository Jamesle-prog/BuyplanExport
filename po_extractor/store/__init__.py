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
    """Return a fresh FabricMasterStore wired to the canonical DB.

    NOTE: this function previously existed only in ``ui.stores`` —
    importing it from ``po_extractor.store.fabric_master_store`` raised
    ``ImportError`` which was silently swallowed by callers, leaving the
    fabric_master cache empty (BUG fixed in v1.53.0).  Always import via
    ``from po_extractor.store import get_fabric_master_store``.
    """
    return FabricMasterStore(_db_path())


def get_color_translation_store() -> ColorTranslationStore:
    """Return a fresh ColorTranslationStore wired to the canonical DB."""
    return ColorTranslationStore(_db_path())


def get_boat_sample_store() -> BoatSampleStore:
    """Return a fresh BoatSampleStore wired to the canonical DB."""
    return BoatSampleStore(_db_path())


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
    "ColorTranslationStore", "BoatSampleStore",
    "get_po_store", "get_sky_east_store", "get_fabric_master_store",
    "get_color_translation_store", "get_boat_sample_store",
    "list_all_brands",
]
