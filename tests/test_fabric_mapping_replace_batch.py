"""Regression tests for POStore.replace_fabric_parts_batch (Fix 5).

The "Replace all" import mode in ui/fabric_mapping_view.py used to call
``delete_fabric_parts()`` and ``save_fabric_parts_batch()`` as two separate
calls -- each opens its own ``self._conn()`` connection/transaction. If the
save half raised after the delete had already committed, the source's
fabric-mapping data was permanently gone. ``replace_fabric_parts_batch()``
does the delete + insert inside a SINGLE transaction, so a failure during
the insert half rolls back the delete too.
"""
from __future__ import annotations

import pytest

from po_extractor.models.fabric_part import FabricPart
from po_extractor.store.po_store import POStore


@pytest.fixture
def store(tmp_path):
    return POStore(str(tmp_path / "test.db"))


def test_replace_fabric_parts_batch_deletes_and_inserts_atomically(store):
    # Seed existing data for the source.
    store.save_fabric_parts_batch("giii", {
        "STY1": [FabricPart(combo_idx=0, seq=1, body_part="Body", hhn_no="HHN-OLD")],
    })
    assert store.list_mapped_styles("giii") == {"STY1"}

    deleted = store.replace_fabric_parts_batch("giii", {
        "STY2": [FabricPart(combo_idx=0, seq=1, body_part="Body", hhn_no="HHN-NEW")],
    })

    assert deleted == 1
    assert store.list_mapped_styles("giii") == {"STY2"}
    parts = store.load_fabric_parts_for_styles(["STY2"], source="giii")
    assert parts["STY2"][0].hhn_no == "HHN-NEW"


def test_replace_fabric_parts_batch_only_touches_its_own_source(store):
    store.save_fabric_parts_batch("giii", {
        "STY1": [FabricPart(combo_idx=0, seq=1, body_part="Body", hhn_no="HHN-GIII")],
    })
    store.save_fabric_parts_batch("sky_east", {
        "STY1": [FabricPart(combo_idx=0, seq=1, body_part="Body", hhn_no="HHN-SE")],
    })

    store.replace_fabric_parts_batch("giii", {})

    assert store.list_mapped_styles("giii") == set()
    assert store.list_mapped_styles("sky_east") == {"STY1"}


def test_replace_fabric_parts_batch_rolls_back_delete_on_insert_failure(store):
    """The core guarantee: if the insert half blows up, the pre-existing rows
    for this source must still be there afterward -- NOT silently deleted.
    This is exactly the data-loss scenario the fix closes.

    Triggers a real mid-transaction failure via ``enrich_from_lookup`` (a
    real parameter of both ``save_fabric_parts_batch`` and
    ``replace_fabric_parts_batch``) rather than monkeypatching sqlite
    internals -- ``sqlite3.Connection.execute`` is a read-only slot and
    can't be patched directly.
    """
    store.save_fabric_parts_batch("giii", {
        "STY1": [FabricPart(combo_idx=0, seq=1, body_part="Body", hhn_no="HHN-OLD")],
    })

    class _BoomLookup:
        def get_fabric_detail(self, hhn_no):
            raise RuntimeError("simulated fabric lookup failure mid-insert")

    with pytest.raises(RuntimeError):
        store.replace_fabric_parts_batch(
            "giii",
            {"STY2": [FabricPart(combo_idx=0, seq=1, body_part="Body",
                                  hhn_no="HHN-NEW", composition="")]},
            enrich_from_lookup=_BoomLookup(),
        )

    assert store.list_mapped_styles("giii") == {"STY1"}, (
        "the pre-existing row for 'giii' must survive a failed replace -- "
        "the delete must have rolled back together with the failed insert"
    )
