"""Regression: the fabric-master legacy auto-migration must actually run.

Locks the v2.26.x fix: ``FabricMasterStore.__init__`` runs schema migrations
that stamp ``PRAGMA user_version`` to 1 then 2 — even on a brand-new empty
DB — and ``get_fabric_master_store()`` used the same pragma (``>= 1``) as its
"legacy copy already done" marker, probed *after* constructing the store.
The probe therefore always passed and ``migrate_from_db`` was dead code:
a fresh deployment with a populated legacy ``po_history.db`` silently got an
empty fabric DB (blank 综合key / composition in every buy plan).

The fix gives the factory marker its own bit (0x100) so the schema-migration
values can never satisfy it.

Run with: ``pytest tests/test_fabric_migration_factory.py -v``
"""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def split_dbs(tmp_path, monkeypatch):
    """Point the factory at a fresh fabric DB + a seeded legacy DB."""
    import po_extractor.config as cfg
    import po_extractor.store as pkg
    from po_extractor.store.fabric_master_store import FabricMasterStore

    legacy = tmp_path / "po_history.db"
    fabric = tmp_path / "fabric_master.db"

    # Seed the LEGACY db with a fabric_master table + one row — the pre-split
    # state a real deployment upgrades from.
    FabricMasterStore(str(legacy))
    with sqlite3.connect(legacy) as c:
        c.execute(
            "INSERT INTO fabric_master "
            "(quality_no, display_key, composition_en, weight_gsm, "
            "cuttable_width_cm) VALUES ('__HHN_MIG__', '', '100%Test', 200, 140)"
        )

    monkeypatch.setattr(pkg, "_db_path", lambda: str(legacy))
    monkeypatch.setattr(cfg, "get_fabric_db_path", lambda: str(fabric))
    return legacy, fabric


def test_fresh_fabric_db_receives_legacy_rows(split_dbs):
    """First factory call on a fresh fabric DB must copy the legacy rows —
    the historical bug returned an empty store forever."""
    import po_extractor.store as pkg

    store = pkg.get_fabric_master_store()
    _legacy, fabric = split_dbs
    assert store.db_path == str(fabric)
    assert store.count() == 1, (
        "Legacy fabric rows were NOT migrated into the fresh fabric DB — "
        "the factory's user_version marker collided with the schema "
        "migrations' stamps again (probe passed before migrate_from_db ran)."
    )


def test_marker_bit_persists_and_skips_reprobe(split_dbs):
    """After a successful first call the marker bit must be set (fast path)
    without clobbering the schema-migration version in the low bits."""
    import po_extractor.store as pkg

    pkg.get_fabric_master_store()
    _legacy, fabric = split_dbs
    with sqlite3.connect(fabric) as c:
        uv = c.execute("PRAGMA user_version").fetchone()[0]
    assert uv & pkg._FABRIC_MIGRATION_MARKER_BIT, "marker bit not stamped"
    assert uv & 0xFF == 2, (
        f"schema-migration version lost when stamping the marker: {uv:#x}"
    )
    # Second call takes the fast path and still sees the data.
    assert pkg.get_fabric_master_store().count() == 1


def test_intentionally_empty_fabric_db_not_remigrated(split_dbs, monkeypatch):
    """Deleting all fabric rows after migration must NOT trigger a re-copy —
    the marker records that the check already ran."""
    import po_extractor.store as pkg

    store = pkg.get_fabric_master_store()
    assert store.count() == 1
    with sqlite3.connect(store.db_path) as c:
        c.execute("DELETE FROM fabric_master")
    assert pkg.get_fabric_master_store().count() == 0, (
        "An intentionally emptied fabric DB was re-migrated from legacy — "
        "the marker must make the check one-shot."
    )
