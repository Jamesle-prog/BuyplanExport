"""Factory dictionary: canonical + aliases, resolution, fuzzy suggestion,
unresolved detection, and canonical-aware factory scoping."""
from __future__ import annotations

import sqlite3

import pytest

from po_extractor.store.factory_registry_store import (
    FactoryRegistryStore, norm, factory_code,
)

_V1 = "01423 - CHANGZHOU JINTAN XINZHUAN"
_V2 = "01423 - CHANGZHOU JINTAN XINZHUANGYUAN GARMENT CO.,LTD."
_V3 = "213200 - SUZHOU SILK CO"


@pytest.fixture
def store(tmp_path):
    db = str(tmp_path / "po.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE po_metadata (po_number TEXT, factory TEXT)")
    conn.execute("CREATE TABLE production_tracking "
                 "(id INTEGER PRIMARY KEY, po_number TEXT, style TEXT, factory TEXT)")
    for f in (_V1, _V2, _V3):
        conn.execute("INSERT INTO po_metadata VALUES ('P', ?)", (f,))
    conn.commit(); conn.close()
    return FactoryRegistryStore(db)


# ── Normalisation ───────────────────────────────────────────────────────────

def test_norm_collapses_space_and_case():
    assert norm("  01423 -  Changzhou   Jintan ") == norm("01423 - CHANGZHOU JINTAN")


def test_factory_code_extracts_leading_code():
    assert factory_code(_V1) == "01423"
    assert factory_code("SUZHOU SILK") == ""      # no code prefix


# ── Resolution ──────────────────────────────────────────────────────────────

def test_unknown_before_registering(store):
    assert not store.is_known(_V1)
    assert store.resolve_id(_V1) is None


def test_add_canonical_makes_its_name_resolvable(store):
    cid = store.add_canonical("Changzhou Jintan", code="01423")
    assert store.canonical_name("changzhou   jintan") == "Changzhou Jintan"  # norm
    assert store.resolve_id("Changzhou Jintan") == cid


def test_alias_maps_variant_to_canonical(store):
    cid = store.add_canonical("Changzhou Jintan", code="01423")
    store.add_alias(_V1, cid)
    store.add_alias(_V2, cid)
    assert store.canonical_name(_V1) == "Changzhou Jintan"
    assert store.canonical_name(_V2) == "Changzhou Jintan"
    assert store.canonical_name(_V3) is None       # still unknown


def test_alias_conflict_is_rejected(store):
    a = store.add_canonical("Factory A")
    b = store.add_canonical("Factory B")
    store.add_alias(_V1, a)
    with pytest.raises(ValueError):
        store.add_alias(_V1, b)                     # already linked to A


def test_duplicate_canonical_name_rejected(store):
    store.add_canonical("Factory A")
    with pytest.raises(ValueError):
        store.add_canonical("  factory   a  ")      # same after norm


# ── Unresolved detection + suggestion ───────────────────────────────────────

def test_data_factories_dedupes_by_norm(store):
    # _V1/_V2/_V3 are three distinct strings.
    assert len(store.data_factories()) == 3


def test_unresolved_shrinks_as_names_are_linked(store):
    assert store.unresolved_count() == 3
    cid = store.add_canonical("Changzhou Jintan", code="01423")
    store.add_alias(_V1, cid)
    store.add_alias(_V2, cid)
    assert store.unresolved_count() == 1           # only _V3 left
    assert [u["raw"] for u in store.list_unresolved()] == [_V3]


def test_suggestion_matches_on_shared_code(store):
    cid = store.add_canonical("Changzhou Jintan", code="01423")
    store.add_alias(_V1, cid)
    # _V2 shares code 01423 → suggested to the same canonical.
    sugg = {u["raw"]: u["suggestion"] for u in store.list_unresolved()}
    assert sugg[_V2] is not None and sugg[_V2]["id"] == cid
    assert sugg[_V3] is None                        # different code, dissimilar


# ── Canonical-aware scoping ─────────────────────────────────────────────────

def test_scope_norms_expand_canonical_to_all_aliases(store):
    cid = store.add_canonical("Changzhou Jintan", code="01423")
    store.add_alias(_V1, cid)
    store.add_alias(_V2, cid)
    scope = store.scope_norms_for_names(["Changzhou Jintan"])
    assert norm(_V1) in scope and norm(_V2) in scope
    assert norm(_V3) not in scope


def test_scope_norms_legacy_exact_match_without_dict(store):
    """A user assigned a raw string before it was registered still matches
    that exact string (backward compatibility)."""
    scope = store.scope_norms_for_names([_V1])
    assert norm(_V1) in scope


# ── Editing ─────────────────────────────────────────────────────────────────

def test_rename_and_delete(store):
    cid = store.add_canonical("Old Name")
    store.rename_canonical(cid, "New Name")
    assert "New Name" in store.canonical_names()
    store.delete_canonical(cid)
    assert store.canonical_names() == []


def test_remove_alias(store):
    cid = store.add_canonical("Factory A")
    store.add_alias(_V1, cid)
    assert store.canonical_name(_V1) == "Factory A"
    store.remove_alias(_V1)
    assert store.canonical_name(_V1) is None
