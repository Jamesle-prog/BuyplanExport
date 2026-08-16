"""Corrections the AI made are remembered, and answer before it is asked again.

The point of the table is that the second file carrying the same odd spelling
costs nothing. The risk it has to avoid is a remembered answer putting a value
onto a row that never had it — so a correction only ever applies when its
target is still among the values on file for that row.
"""
from __future__ import annotations

import pytest

from po_extractor.store.ai_corrections_store import (
    KIND_SKY_EAST_COLOUR, SOURCE_AI, SOURCE_USER, AiCorrectionStore, normalise,
)


@pytest.fixture
def store(tmp_path):
    AiCorrectionStore._checked_paths.clear()
    return AiCorrectionStore(str(tmp_path / "corr.db"))


K = KIND_SKY_EAST_COLOUR


# ── remembering and recalling ───────────────────────────────────────────────

def test_a_correction_is_recalled(store):
    store.record(K, "", "DK Grey", "Dark Grey")
    assert store.lookup(K, "", "DK Grey", ["Dark Grey", "Navy"]) == "Dark Grey"


def test_recall_ignores_case_and_punctuation(store):
    """The same habit typed slightly differently is the same habit."""
    store.record(K, "", "(DK Grey)", "Dark Grey")
    for variant in ["dk grey", "DK  GREY", "DK-Grey", "(dk grey)"]:
        assert store.lookup(K, "", variant, ["Dark Grey"]) == "Dark Grey"


def test_the_answer_comes_back_spelled_as_it_is_on_file(store):
    """The caller matches on the candidate it holds, so the stored spelling
    must not be handed back in place of the row's own."""
    store.record(K, "", "DK Grey", "dark grey")
    assert store.lookup(K, "", "DK Grey", ["Dark Grey"]) == "Dark Grey"


def test_an_unknown_value_returns_nothing(store):
    assert store.lookup(K, "", "Chartreuse", ["Navy"]) is None


def test_scopes_do_not_leak_into_each_other(store):
    store.record(K, "ClientA", "Blue", "Navy")
    assert store.lookup(K, "ClientA", "Blue", ["Navy"]) == "Navy"
    assert store.lookup(K, "ClientB", "Blue", ["Navy"]) is None


# ── the safety rule ─────────────────────────────────────────────────────────

def test_a_correction_never_introduces_a_value_not_on_file(store):
    """The whole guard. "Blue"->"Navy" learned on one order must not put Navy
    onto an item whose colours are Black and Cream."""
    store.record(K, "", "Blue", "Navy")
    assert store.lookup(K, "", "Blue", ["Black", "Cream"]) is None


def test_without_candidates_the_stored_answer_is_returned_as_is(store):
    """Callers that have no candidate list opt out of the guard knowingly."""
    store.record(K, "", "Blue", "Navy")
    assert store.lookup(K, "", "Blue") == "Navy"


# ── what is worth recording ─────────────────────────────────────────────────

def test_a_value_that_means_itself_is_not_recorded(store):
    """Plain comparison already handles it; storing it would be noise."""
    assert store.record(K, "", "Dark Grey", "dark grey") is False
    assert store.record(K, "", "(Navy)", "Navy") is False
    assert store.list_all().empty


def test_blank_input_is_not_recorded(store):
    assert store.record(K, "", "", "Navy") is False
    assert store.record(K, "", "Navy", "") is False


def test_a_later_answer_replaces_an_earlier_one(store):
    store.record(K, "", "DK Grey", "Dark Grey")
    store.record(K, "", "DK Grey", "Charcoal")
    assert store.lookup(K, "", "DK Grey", ["Charcoal", "Dark Grey"]) == "Charcoal"
    assert len(store.list_all()) == 1          # replaced, not duplicated


def test_the_ai_never_overwrites_a_person(store):
    """Someone who corrected it by hand had the order in front of them."""
    store.record(K, "", "DK Grey", "Dark Grey", source=SOURCE_USER)
    assert store.record(K, "", "DK Grey", "Charcoal", source=SOURCE_AI) is False
    assert store.lookup(K, "", "DK Grey", ["Dark Grey", "Charcoal"]) == "Dark Grey"


def test_a_person_may_overrule_the_ai(store):
    store.record(K, "", "DK Grey", "Charcoal", source=SOURCE_AI)
    assert store.record(K, "", "DK Grey", "Dark Grey", source=SOURCE_USER) is True
    assert store.lookup(K, "", "DK Grey", ["Dark Grey", "Charcoal"]) == "Dark Grey"


# ── review and undo ─────────────────────────────────────────────────────────

def test_use_is_counted_so_a_wrong_one_can_be_spotted(store):
    store.record(K, "", "DK Grey", "Dark Grey")
    for _ in range(3):
        store.lookup(K, "", "DK Grey", ["Dark Grey"])
    row = store.list_all().iloc[0]
    assert int(row["times_used"]) == 3
    assert row["last_used_at"]


def test_a_correction_can_be_deleted(store):
    store.record(K, "", "DK Grey", "Dark Grey")
    cid = int(store.list_all().iloc[0]["id"])
    assert store.delete(cid) is True
    assert store.lookup(K, "", "DK Grey", ["Dark Grey"]) is None
    assert store.delete(cid) is False


def test_list_all_can_be_filtered_by_kind(store):
    store.record(K, "", "DK Grey", "Dark Grey")
    store.record("other_kind", "", "XX", "YY")
    assert len(store.list_all()) == 2
    assert len(store.list_all(kind=K)) == 1


def test_normalise_matches_the_identity_rule():
    """It has to agree with sky_east_store.colour_key, or a correction would
    be recorded for a spelling that path never asks about."""
    from po_extractor.store.sky_east_store import colour_key
    for v in ["(dark grey)", "Dark Grey", "DK  GREY", "黑色", "2#-80#", ""]:
        assert normalise(v) == colour_key(v)


# ── End to end: the AI is asked once, the database answers thereafter ───────

def _sky_east_store(tmp_path, monkeypatch, corr_store, calls, *, ai_on=True):
    """A SkyEastStore whose AI layer is stubbed and whose corrections table is
    the scratch one, so nothing touches the real database or the network."""
    from po_extractor.store.sky_east_store import SkyEastStore
    import po_extractor.lookups.color_ai_enhance as ai

    SkyEastStore._checked_paths.clear()
    store = SkyEastStore(str(tmp_path / "se.db"))
    monkeypatch.setattr(SkyEastStore, "_ai_settings",
                        staticmethod(lambda: (ai_on, "k", "deepseek-chat")))
    monkeypatch.setattr(SkyEastStore, "_corrections",
                        staticmethod(lambda: corr_store))

    def fake_match(client_color, candidates, api_key, model="deepseek-chat"):
        calls.append(client_color)
        return "Dark Grey" if client_color == "DK Grey" else ""
    monkeypatch.setattr(ai, "match_color_to_candidates", fake_match)
    return store


def _contract(colour):
    from tests.test_sky_east_store import _make_contract, _make_item
    return _make_contract([_make_item(style="ZLD060", zalando_po="PO1",
                                      color_name=colour, sizes={"S": 1},
                                      total_qty=1)])


def test_the_ai_is_asked_once_then_the_database_answers(tmp_path, monkeypatch,
                                                        store):
    calls: list[str] = []
    se = _sky_east_store(tmp_path, monkeypatch, store, calls)

    se.save_contract_checked(_contract("Dark Grey"))       # the row on file
    se.save_contract_checked(_contract("DK Grey"))         # asks the AI
    assert calls == ["DK Grey"]
    assert len(se.list_items(pc_nos=["PC1"])) == 1
    assert store.lookup(KIND_SKY_EAST_COLOUR, "", "DK Grey", ["Dark Grey"]) \
        == "Dark Grey"

    se.save_contract_checked(_contract("DK Grey"))         # answered from DB
    se.save_contract_checked(_contract("dk  grey"))        # variant, still DB
    assert calls == ["DK Grey"], "the AI should not have been asked again"
    assert len(se.list_items(pc_nos=["PC1"])) == 1


def test_a_learned_correction_applies_even_with_ai_switched_off(tmp_path,
                                                                monkeypatch,
                                                                store):
    """Once established it is a fact about the spelling, not an AI feature —
    and it costs nothing, so the toggle shouldn't gate it."""
    calls: list[str] = []
    store.record(KIND_SKY_EAST_COLOUR, "", "DK Grey", "Dark Grey")
    se = _sky_east_store(tmp_path, monkeypatch, store, calls, ai_on=False)

    se.save_contract_checked(_contract("Dark Grey"))
    se.save_contract_checked(_contract("DK Grey"))
    assert calls == []
    assert len(se.list_items(pc_nos=["PC1"])) == 1


def test_a_correction_cannot_merge_a_genuinely_different_colourway(tmp_path,
                                                                   monkeypatch,
                                                                   store):
    """"DK Grey"->"Dark Grey" must not touch an item whose colour is Navy."""
    calls: list[str] = []
    store.record(KIND_SKY_EAST_COLOUR, "", "DK Grey", "Dark Grey")
    se = _sky_east_store(tmp_path, monkeypatch, store, calls, ai_on=False)

    se.save_contract_checked(_contract("Navy"))
    se.save_contract_checked(_contract("DK Grey"))
    assert len(se.list_items(pc_nos=["PC1"])) == 2      # stayed separate
