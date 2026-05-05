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

import os

import streamlit as st

from po_extractor.store import (
    POStore,
    SkyEastStore,
    FabricMasterStore,
    ColorTranslationStore,
    BoatSampleStore,
    get_po_store as _get_po_store,
    get_sky_east_store as _get_sky_east_store,
    get_fabric_master_store as _get_fabric_master_store,
    get_color_translation_store as _get_color_translation_store,
    get_boat_sample_store as _get_boat_sample_store,
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


@st.cache_resource
def get_color_translation_store() -> ColorTranslationStore:
    """Return the cached ColorTranslationStore."""
    return _get_color_translation_store()


def get_boat_sample_store() -> BoatSampleStore:
    """Return a fresh BoatSampleStore (not cached — lightweight wrapper)."""
    return _get_boat_sample_store()


# ── Convenience helpers exported for UI code ────────────────────────────────

def list_all_brands(company: str) -> list[str]:
    """See ``po_extractor.store.list_all_brands``."""
    return _list_all_brands(company)
