"""Streamlit-aware store factories.

This module is the **only** place ``@st.cache_resource`` should appear for
data stores.  Every factory delegates to the canonical, non-Streamlit
factories in ``po_extractor.store`` so there is exactly one wiring point
between code and DB.

Pre-refactor history
--------------------
v1.53.0 fixed a class of silent-failure bugs caused by the same factory
function existing under different import paths (``ui.stores`` vs.
``po_extractor.store.<module>``).  The exporter modules tried to import
from ``po_extractor.store.fabric_master_store`` — that path didn't have
the factory, the ``ImportError`` was swallowed by a bare ``except``, and
the fabric_master cache was silently empty.  After the refactor every
caller imports from ``po_extractor.store`` and the factory is guaranteed
to exist.
"""
from __future__ import annotations

import functools
import os

import streamlit as st

from po_extractor.store import (
    POStore,
    SkyEastStore,
    FabricMasterStore,
    ColorTranslationStore,
    BoatSampleStore,
    UITranslationStore,
    AppSettingsStore,
    get_po_store as _get_po_store,
    get_sky_east_store as _get_sky_east_store,
    get_fabric_master_store as _get_fabric_master_store,
    get_color_translation_store as _get_color_translation_store,
    get_boat_sample_store as _get_boat_sample_store,
    get_ui_translation_store as _get_ui_translation_store,
    get_app_settings_store as _get_app_settings_store,
    list_all_brands as _list_all_brands,
)
from po_extractor.config import DATA_DIR, DB_PATH   # canonical path constants

IMAGES_DIR_DEFAULT = os.path.join(DATA_DIR, "images")


# ── Cached factories (Streamlit @st.cache_resource is keyed per-process) ────

@st.cache_resource
def get_store() -> POStore:
    """Return the cached shared POStore (SQLite-backed)."""
    return _get_po_store()


def get_sky_east_store() -> SkyEastStore:
    """Return a fresh SkyEastStore (not cached — lightweight wrapper)."""
    return _get_sky_east_store()


def get_fabric_master_store() -> FabricMasterStore:
    """Return a fresh FabricMasterStore (not cached — lightweight wrapper)."""
    return _get_fabric_master_store()


@functools.cache
def get_color_translation_store() -> ColorTranslationStore:
    """Return the cached ColorTranslationStore.

    Cached with ``functools.cache`` (not ``st.cache_resource``) on purpose:
    ``__init__`` opens a SQLite connection and runs ``_ensure_schema()``, so
    repeated construction on every Streamlit render is genuinely expensive.

    ``functools.cache`` ties the cached instance to *this function object*.
    When Streamlit hot-reloads the module after a code change, the function
    is recreated and its cache is empty, so a fresh instance is built from
    the current class definition — avoiding the stale-class AttributeError
    that ``st.cache_resource`` caused (it preserves the cached object across
    reloads, leaving its ``__class__`` pointing at the pre-reload class).
    """
    return _get_color_translation_store()


def get_boat_sample_store() -> BoatSampleStore:
    """Return a fresh BoatSampleStore (not cached — lightweight wrapper)."""
    return _get_boat_sample_store()


@st.cache_resource
def get_ui_translation_store() -> UITranslationStore:
    """Return the cached UITranslationStore (seeds defaults on first access)."""
    store = _get_ui_translation_store()
    store.seed_defaults(skip_existing=True)
    return store


@functools.cache
def get_app_settings_store() -> AppSettingsStore:
    """Return the cached AppSettingsStore.

    Uses ``functools.cache`` (same rationale as ColorTranslationStore) to
    avoid the stale-class issue that ``@st.cache_resource`` causes on
    Streamlit hot-reloads.
    """
    return _get_app_settings_store()


# ── Convenience helpers exported for UI code ────────────────────────────────

def list_all_brands(company: str) -> list[str]:
    """See ``po_extractor.store.list_all_brands``."""
    return _list_all_brands(company)
