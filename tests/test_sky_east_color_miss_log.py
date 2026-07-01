"""Tests for SkyEastStore's colour-resolution-miss diagnostic log.

Scoped to Sky East specifically (not the GIII po_exceptions Exception
Queue, which is a different pipeline / different kind of failure) so a
reviewer can see, for every colour that failed to resolve during buy plan
generation, exactly what the client's PO said.
"""
from __future__ import annotations

import pytest

from po_extractor.store.sky_east_store import SkyEastStore


@pytest.fixture
def store(tmp_path):
    return SkyEastStore(str(tmp_path / "test.db"))


def test_log_color_miss_then_list(store):
    store.log_color_miss(
        pc_no="HHPPC048", contract_no="26302-ZA7158", style="BL4257",
        po_no="PO2338263C", client_po_color="Dark Brown",
        attempted_color="Dark Brown", source="progress",
    )
    df = store.list_color_misses()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["pc_no"] == "HHPPC048"
    assert row["style"] == "BL4257"
    assert row["client_po_color"] == "Dark Brown"
    assert row["source"] == "progress"
    assert row["logged_at"]


def test_list_color_misses_newest_first(store):
    store.log_color_miss(
        pc_no="P1", contract_no="C1", style="S1", po_no="PO1",
        client_po_color="Old Miss", attempted_color="Old Miss", source="db",
    )
    store.log_color_miss(
        pc_no="P2", contract_no="C2", style="S2", po_no="PO2",
        client_po_color="New Miss", attempted_color="New Miss", source="db",
    )
    df = store.list_color_misses()
    assert list(df["client_po_color"]) == ["New Miss", "Old Miss"]


def test_log_color_miss_is_append_only_no_dedup(store):
    """Re-running a generation over the same bad data logs another entry —
    deliberately not deduped, so the count reflects each run's failures.
    """
    for _ in range(3):
        store.log_color_miss(
            pc_no="P1", contract_no="C1", style="S1", po_no="PO1",
            client_po_color="Repeat Miss", attempted_color="Repeat Miss",
            source="db",
        )
    assert len(store.list_color_misses()) == 3


def test_clear_color_misses(store):
    store.log_color_miss(
        pc_no="P1", contract_no="C1", style="S1", po_no="PO1",
        client_po_color="X", attempted_color="X", source="db",
    )
    removed = store.clear_color_misses()
    assert removed == 1
    assert store.list_color_misses().empty


def test_list_color_misses_empty_by_default(store):
    assert store.list_color_misses().empty
