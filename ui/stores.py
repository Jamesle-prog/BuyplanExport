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
    ProductionTrackingStore,
    FactoryProgressStore,
    CmptContractStore,
    EmailInboxStore,
    FactoryRegistryStore,
    LoginLogStore,
    get_po_store as _get_po_store,
    get_sky_east_store as _get_sky_east_store,
    get_fabric_master_store as _get_fabric_master_store,
    get_color_translation_store as _get_color_translation_store,
    get_boat_sample_store as _get_boat_sample_store,
    get_ui_translation_store as _get_ui_translation_store,
    get_app_settings_store as _get_app_settings_store,
    get_production_tracking_store as _get_production_tracking_store,
    get_factory_progress_store as _get_factory_progress_store,
    get_cmpt_contract_store as _get_cmpt_contract_store,
    get_email_inbox_store as _get_email_inbox_store,
    get_factory_registry_store as _get_factory_registry_store,
    get_login_log_store as _get_login_log_store,
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
    """Return a fresh SkyEastStore.

    Deliberately uncached: construction is cheap because the class-level
    ``SkyEastStore._checked_paths`` guard runs schema-ensure only once per
    db_path per process (see the store).  Do NOT ``functools.cache`` this
    wrapper — a fresh instance per call avoids the stale-class hot-reload
    issue entirely.
    """
    return _get_sky_east_store()


def get_fabric_master_store() -> FabricMasterStore:
    """Return a fresh FabricMasterStore.

    Deliberately uncached: the fabric DB path is admin-changeable at
    runtime, and the class-level ``FabricMasterStore._checked_paths`` guard
    already makes repeated construction cheap (schema-ensure once per
    db_path per process, so a newly configured path still gets its ensure).
    """
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


@functools.cache
def get_production_tracking_store() -> ProductionTrackingStore:
    """Return the cached ProductionTrackingStore.

    Cached with ``functools.cache`` (same rationale as ColorTranslationStore /
    AppSettingsStore): construction calls ``_ensure_schema()`` which opens a
    SQLite connection and runs ``PRAGMA table_info`` — doing this on every
    Streamlit render adds unnecessary latency.

    ``functools.cache`` (not ``@st.cache_resource``) is intentional: it ties
    the cached instance to this function object.  When Streamlit hot-reloads
    the module the function is recreated, its cache is empty, and a fresh
    instance is built from the current class definition — avoiding the
    stale-class AttributeError that ``st.cache_resource`` causes across
    hot-reloads.

    Data freshness: ``list_all()`` and ``list_untracked_pos()`` open their own
    connections on every call, so they always see committed writes regardless
    of instance caching.
    """
    return _get_production_tracking_store()


@functools.cache
def get_factory_progress_store() -> FactoryProgressStore:
    """Return the cached FactoryProgressStore (same ``functools.cache``
    rationale as get_production_tracking_store above)."""
    return _get_factory_progress_store()


@functools.cache
def get_cmpt_contract_store() -> CmptContractStore:
    """Return the cached CmptContractStore (same ``functools.cache``
    rationale as get_production_tracking_store above)."""
    return _get_cmpt_contract_store()


@functools.cache
def get_email_inbox_store() -> EmailInboxStore:
    """Return the cached EmailInboxStore (same ``functools.cache``
    rationale as get_production_tracking_store above)."""
    return _get_email_inbox_store()


@functools.cache
def get_factory_registry_store() -> FactoryRegistryStore:
    """Return the cached FactoryRegistryStore (same ``functools.cache``
    rationale as get_production_tracking_store above)."""
    return _get_factory_registry_store()


@functools.cache
def get_login_log_store() -> LoginLogStore:
    """Return the cached LoginLogStore (same ``functools.cache`` rationale as
    get_production_tracking_store above)."""
    return _get_login_log_store()


# ── Convenience helpers exported for UI code ────────────────────────────────

def list_all_brands(company: str) -> list[str]:
    """See ``po_extractor.store.list_all_brands``."""
    return _list_all_brands(company)


@functools.cache
def _cprs_client_cached(base_url: str, api_key: str):
    from po_extractor.utils.cprs_client import CprsClient
    return CprsClient(base_url, api_key)


def get_cprs_client():
    """Return the session-cached CPRS client, or None when unconfigured.

    Cached per (base_url, api_key) so the client's internal reference-data /
    evaluation caches survive Streamlit reruns — previously a fresh client
    was built on every generate click, refetching everything. Changing the
    settings yields new args and therefore a fresh client.
    """
    from po_extractor.store.app_settings_store import (
        KEY_CPRS_BASE_URL, KEY_CPRS_API_KEY,
    )
    s = get_app_settings_store()
    base = (s.get(KEY_CPRS_BASE_URL, "") or "").strip()
    if not base:
        return None
    return _cprs_client_cached(base, s.get(KEY_CPRS_API_KEY, "") or "")
