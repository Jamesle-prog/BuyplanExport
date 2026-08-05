"""Regression test for SkyEastStore.save_contract_checked's duplicate-key
bug within a single contract.

``existing_map`` was built ONCE before the item loop and never updated
inside it.  When a contract has two items sharing the same
(style, color_name, zalando_po) -- the table's own UNIQUE key -- both loop
iterations looked up the same stale pre-loop snapshot, so the second
iteration either silently overwrote the first iteration's real update with
no archive row, or double-archived the same original state while the
first item's update was lost.
"""
from __future__ import annotations


def _make_item(**over):
    from po_extractor.models.sky_east_data import SkyEastItem
    base = dict(
        pc_no="PC1", zalando_po="PO1", style="ST1", config_sku="SKU-1",
        article_name="A", brand="Anna Field", color_name="Blue",
        colour_code="Q11", launch_date="", fabric_item_no="HHP-JS-12345",
        fabrication="", contract_no="", sizes={"S": 1}, total_qty=1,
        fob_usd=1.0, total_cost_usd=1.0,
    )
    base.update(over)
    return SkyEastItem(**base)


def _make_contract(items, **over):
    from po_extractor.models.sky_east_data import SkyEastContract
    base = dict(pc_no="PC1", pc_date="2026-01-01", buyer="B", seller="S",
                currency="USD", payment_terms="TT", trade_term="FOB")
    base.update(over)
    return SkyEastContract(items=items, **base)


def test_duplicate_key_within_same_contract_both_updates_applied(tmp_path):
    """Two items sharing (style, color_name, zalando_po) within ONE
    save_contract_checked() call must both be reflected: the second item's
    values (the final DB state) must win, and the archive history must show
    two real transitions -- not the same pre-loop snapshot archived twice."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))

    # First save: establish a baseline row.
    store.save_contract_checked(_make_contract([
        _make_item(style="DUP", color_name="Red", zalando_po="POZ",
                   sizes={"S": 1}, total_qty=1, fob_usd=1.0),
    ]))

    # Second save: the SAME contract carries two items for the identical
    # (style, color_name, zalando_po) key with different quantities each
    # time -- simulating a source file that lists the same SKU twice with
    # a running total correction.
    result = store.save_contract_checked(_make_contract([
        _make_item(style="DUP", color_name="Red", zalando_po="POZ",
                   sizes={"S": 2}, total_qty=2, fob_usd=1.0),
        _make_item(style="DUP", color_name="Red", zalando_po="POZ",
                   sizes={"S": 3}, total_qty=3, fob_usd=1.0),
    ]))

    # Both iterations must be recognised as real updates (not a duplicate
    # comparing against the same stale snapshot twice).
    assert len(result["updated_items"]) == 2

    # The row actually stored must reflect the LAST item processed (qty=3),
    # proving the second iteration compared against the first iteration's
    # write, not the pre-loop DB state.
    items = store.list_items(["PC1"])
    row = items[(items["style"] == "DUP") & (items["zalando_po"] == "POZ")].iloc[0]
    assert int(row["total_qty"]) == 3
    assert int(row["s"]) == 3

    # Two real transitions (1->2, 2->3) means two archive rows, not zero or
    # a duplicated single snapshot.
    history = store.list_item_history("PC1", style="DUP")
    assert len(history) == 2
    archived_qtys = sorted(int(q) for q in history["total_qty"])
    assert archived_qtys == [1, 2], (
        f"expected archive of qty=1 (baseline) then qty=2 (first item's "
        f"write, overwritten by the second item) -- got {archived_qtys}"
    )


def test_return_label_persists_through_insert(tmp_path):
    """The Return Label value (Yes/No/NA from the client's PO) is written on
    insert, same as the other item fields."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))

    store.save_contract_checked(_make_contract([
        _make_item(style="RL1", color_name="Blue", zalando_po="PO1",
                   return_label="Yes"),
    ]))
    items = store.list_items(["PC1"])
    row = items[items["style"] == "RL1"].iloc[0]
    assert row["return_label"] == "Yes"


def test_return_label_change_alone_is_held_back_not_silently_dropped(tmp_path):
    """A Return Label change with sizes/qty/FOB otherwise identical used to
    be treated as a plain duplicate (skipped) -- the new value was silently
    discarded. It must now be surfaced as a pending confirmation instead."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL2", color_name="Blue", zalando_po="PO1", return_label="Yes"),
    ]))

    result = store.save_contract_checked(_make_contract([
        _make_item(style="RL2", color_name="Blue", zalando_po="PO1", return_label="No"),
    ]))

    assert result["duplicate_items"] == []
    assert len(result["pending_return_label"]) == 1
    pending = result["pending_return_label"][0]
    assert pending["old_return_label"] == "Yes"
    assert pending["new_return_label"] == "No"

    # Not written yet -- DB still shows the original value.
    items = store.list_items(["PC1"])
    assert items[items["style"] == "RL2"].iloc[0]["return_label"] == "Yes"


def test_return_label_change_with_other_changes_holds_back_the_whole_record(tmp_path):
    """When Return Label AND sizes/qty both differ, the whole item is held
    back -- not just the label -- so a size change never sneaks in
    unconfirmed alongside a Return Label change the user hasn't approved."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL3", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 1}, total_qty=1, return_label="Yes"),
    ]))

    result = store.save_contract_checked(_make_contract([
        _make_item(style="RL3", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 9}, total_qty=9, return_label="No"),
    ]))

    assert result["updated_items"] == []
    assert len(result["pending_return_label"]) == 1
    pending = result["pending_return_label"][0]
    assert pending["changed"]["return_label"] == ("Yes", "No")
    assert pending["changed"]["total_qty"] == (1, 9)

    items = store.list_items(["PC1"])
    row = items[items["style"] == "RL3"].iloc[0]
    assert row["return_label"] == "Yes"
    assert int(row["total_qty"]) == 1


def test_return_label_unchanged_other_fields_still_auto_update(tmp_path):
    """Regression guard: when Return Label is unchanged, size/qty/FOB changes
    must keep auto-updating exactly as before this feature -- only a Return
    Label change itself requires confirmation."""
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL4", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 1}, total_qty=1, return_label="Yes"),
    ]))

    result = store.save_contract_checked(_make_contract([
        _make_item(style="RL4", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 9}, total_qty=9, return_label="Yes"),
    ]))

    assert result["pending_return_label"] == []
    assert len(result["updated_items"]) == 1

    items = store.list_items(["PC1"])
    row = items[items["style"] == "RL4"].iloc[0]
    assert int(row["total_qty"]) == 9
    assert row["return_label"] == "Yes"


def test_apply_pending_item_writes_the_confirmed_replacement(tmp_path):
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL5", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 1}, total_qty=1, return_label="Yes"),
    ]))
    result = store.save_contract_checked(_make_contract([
        _make_item(style="RL5", color_name="Blue", zalando_po="PO1",
                   sizes={"S": 9}, total_qty=9, return_label="No"),
    ]))
    pending = result["pending_return_label"][0]

    outcome = store.apply_pending_item(pending["item"])
    assert outcome == "updated"

    items = store.list_items(["PC1"])
    row = items[items["style"] == "RL5"].iloc[0]
    assert row["return_label"] == "No"
    assert int(row["total_qty"]) == 9

    # The pre-confirmation state (qty=1, return_label=Yes) must be archived.
    history = store.list_item_history("PC1", style="RL5")
    assert history.iloc[0]["return_label"] == "Yes"
    assert int(history.iloc[0]["total_qty"]) == 1


def test_return_label_defaults_to_na_when_not_set(tmp_path):
    from po_extractor.store.sky_east_store import SkyEastStore

    store = SkyEastStore(str(tmp_path / "se.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="RL2", color_name="Red", zalando_po="PO2"),
    ]))
    items = store.list_items(["PC1"])
    assert items[items["style"] == "RL2"].iloc[0]["return_label"] == "NA"


# ── A colour retyped between revisions is the same item ─────────────────────
#
# HHPPC053 arrived twice: 2026-07-24 wrote the colours "(dark grey)",
# "(black)(off-white)", "(dark blue)"; 2026-07-30 wrote "Dark Grey", "black
# off white", "dark blue" -- same styles, same client POs, same quantities.
# Matched as raw text those read as new items, so the second upload inserted
# three rows beside the three it should have updated and the buy plan printed
# every style twice.

import pytest


@pytest.mark.parametrize("before, after", [
    ("(dark grey)", "Dark Grey"),                  # parens + case
    ("(black)(off-white)", "black off white"),     # parens + hyphen
    ("(dark blue)", "dark blue"),                  # parens only
    ("NAVY", "navy"),                              # case only
    ("CHOCOLATE BROWN", "chocolate  brown"),       # doubled space
])
def test_a_retyped_colour_updates_the_row_it_should(tmp_path, before, after):
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / f"se{abs(hash(before))}.db"))

    store.save_contract_checked(_make_contract([
        _make_item(style="ZLD060", zalando_po="PO2360361C", color_name=before,
                   config_sku="", sizes={"S": 500}, total_qty=500)]))
    result = store.save_contract_checked(_make_contract([
        _make_item(style="ZLD060", zalando_po="PO2360361C", color_name=after,
                   config_sku="EV421J0GZ-C12", sizes={"S": 500}, total_qty=500)]))

    df = store.list_items(pc_nos=["PC1"])
    assert len(df) == 1, "the retyped colour must not add a second line"
    assert result["new_items"] == []
    # The current file's spelling wins, and with it the Config SKU the older
    # parse didn't have -- that blank is what showed up in the buy plan.
    assert df.iloc[0]["color_name"] == after
    assert df.iloc[0]["config_sku"] == "EV421J0GZ-C12"


def test_genuinely_different_colourways_stay_separate(tmp_path):
    """Real second colourways sharing a style and PO -- from HHPPC042/045/043
    and HHPPC048. Merging these would lose a whole line of the order."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "se_ways.db"))

    for a, b in [("NAVY", "wine"), ("FUSHIA", "BURGUNDY"), ("BLACK", "CREAM"),
                 ("CHOCOLATE BROWN", "NAVY"), ("(dark blue)(white)", "(black)(white)")]:
        store.save_contract_checked(_make_contract([
            _make_item(style=f"S{a}{b}", zalando_po="POX", color_name=a),
            _make_item(style=f"S{a}{b}", zalando_po="POX", color_name=b)]))

    assert len(store.list_items(pc_nos=["PC1"])) == 10


def test_word_order_still_separates_a_colour_from_its_reverse(tmp_path):
    """Punctuation and case are noise; order is not -- body vs trim."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "se_order.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="(black)(white)"),
        _make_item(style="ST1", zalando_po="PO1", color_name="(white)(black)")]))
    assert len(store.list_items(pc_nos=["PC1"])) == 2


def test_a_real_change_still_archives_and_updates_across_a_retype(tmp_path):
    """The merge's own job -- archive the old state, write the new one -- has
    to keep working when the colour spelling moved at the same time."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "se_arch.db"))

    store.save_contract_checked(_make_contract([
        _make_item(style="DR5108", zalando_po="PO2361469C",
                   color_name="(black)(off-white)", sizes={"S": 400}, total_qty=400)]))
    result = store.save_contract_checked(_make_contract([
        _make_item(style="DR5108", zalando_po="PO2361469C",
                   color_name="black off white", sizes={"S": 450}, total_qty=450)]))

    assert len(result["updated_items"]) == 1
    assert len(store.list_items(pc_nos=["PC1"])) == 1
    assert int(store.list_items(pc_nos=["PC1"]).iloc[0]["total_qty"]) == 450
    hist = store.list_item_history("PC1", style="DR5108")
    assert len(hist) == 1
    assert int(hist.iloc[0]["total_qty"]) == 400          # the pre-change state


def test_colour_key_normalises_only_what_it_should():
    from po_extractor.store.sky_east_store import colour_key
    assert colour_key("(dark grey)") == colour_key("Dark Grey") == "dark grey"
    assert colour_key("(black)(off-white)") == colour_key("black off white")
    assert colour_key(None) == colour_key("") == ""
    assert colour_key("黑色") == "黑色"                    # CJK is kept
    assert colour_key("2#-80#") == "2 80"                 # digits are kept
    assert colour_key("navy") != colour_key("wine")


def test_an_unchanged_row_keeps_the_fields_the_user_patched(tmp_path):
    """The duplicate path must not become a full overwrite: fabric_item_no and
    contract_no are maintained in the app and usually blank in the file."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "se_patch.db"))

    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="(navy)")]))
    store.update_item_fields("PC1", "ST1", "(navy)", "PO1",
                             fabric_item_no="HHP-JS-99999", contract_no="26302-ZA1")

    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="Navy",
                   fabric_item_no="", contract_no="")]))

    row = store.list_items(pc_nos=["PC1"]).iloc[0]
    assert row["fabric_item_no"] == "HHP-JS-99999"     # not clobbered
    assert row["contract_no"] == "26302-ZA1"
    assert row["color_name"] == "Navy"                 # but the colour refreshed


def test_a_blank_incoming_sku_never_erases_one_on_file(tmp_path):
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "se_sku.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", config_sku="AN621C2PV-Q11")]))
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", config_sku="")]))
    assert store.list_items(pc_nos=["PC1"]).iloc[0]["config_sku"] == "AN621C2PV-Q11"


# ── AI-assisted matching (admin toggle, off by default) ─────────────────────

def _ai_store(tmp_path, monkeypatch, name, *, enabled=True, picks=None,
              calls=None):
    """A store whose AI layer is stubbed — no network, no API key needed."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / name))
    monkeypatch.setattr(
        SkyEastStore, "_ai_settings",
        staticmethod(lambda: (enabled, "k" if enabled else "", "deepseek-chat")))

    def fake_match(client_color, candidates, api_key, model="deepseek-chat"):
        if calls is not None:
            calls.append((client_color, tuple(candidates)))
        return (picks or {}).get(client_color, "")

    import po_extractor.lookups.color_ai_enhance as ai
    monkeypatch.setattr(ai, "match_color_to_candidates", fake_match)
    return store


def test_ai_matches_a_colour_normalisation_cannot(tmp_path, monkeypatch):
    """An abbreviation is a different string however it's normalised."""
    calls = []
    store = _ai_store(tmp_path, monkeypatch, "ai_on.db",
                      picks={"DK Grey": "Dark Grey"}, calls=calls)

    store.save_contract_checked(_make_contract([
        _make_item(style="ZLD060", zalando_po="PO1", color_name="Dark Grey",
                   sizes={"S": 500}, total_qty=500)]))
    result = store.save_contract_checked(_make_contract([
        _make_item(style="ZLD060", zalando_po="PO1", color_name="DK Grey",
                   sizes={"S": 600}, total_qty=600)]))

    assert len(store.list_items(pc_nos=["PC1"])) == 1
    assert result["new_items"] == []
    assert result["ai_matched_items"] == [("ZLD060", "Dark Grey", "DK Grey", "PO1")]
    assert int(store.list_items(pc_nos=["PC1"]).iloc[0]["total_qty"]) == 600
    # Only the colours on file for that same style + PO were offered.
    assert calls == [("DK Grey", ("Dark Grey",))]


def test_the_same_case_without_the_toggle_still_duplicates(tmp_path, monkeypatch):
    """The toggle is the whole difference — this is what admins are choosing
    between, so it is pinned rather than assumed."""
    store = _ai_store(tmp_path, monkeypatch, "ai_off.db", enabled=False,
                      picks={"DK Grey": "Dark Grey"})
    store.save_contract_checked(_make_contract([
        _make_item(style="ZLD060", zalando_po="PO1", color_name="Dark Grey")]))
    store.save_contract_checked(_make_contract([
        _make_item(style="ZLD060", zalando_po="PO1", color_name="DK Grey")]))
    assert len(store.list_items(pc_nos=["PC1"])) == 2


def test_ai_is_not_consulted_when_normalisation_already_matched(tmp_path,
                                                                monkeypatch):
    """No tokens spent on the case the cheap path handles."""
    calls = []
    store = _ai_store(tmp_path, monkeypatch, "ai_skip.db", calls=calls)
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="(dark grey)")]))
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="Dark Grey")]))
    assert calls == []
    assert len(store.list_items(pc_nos=["PC1"])) == 1


def test_a_declined_ai_match_stays_a_new_item(tmp_path, monkeypatch):
    """Navy is not Wine. An empty answer must not merge anything."""
    store = _ai_store(tmp_path, monkeypatch, "ai_no.db", picks={})
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="NAVY")]))
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="wine")]))
    assert len(store.list_items(pc_nos=["PC1"])) == 2


def test_an_answer_outside_the_candidates_is_refused(tmp_path, monkeypatch):
    """Guard against a model returning a colour that isn't on file."""
    store = _ai_store(tmp_path, monkeypatch, "ai_bad.db",
                      picks={"Teal": "Turquoise"})       # never offered
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="NAVY")]))
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="Teal")]))
    assert len(store.list_items(pc_nos=["PC1"])) == 2


def test_ai_never_reaches_across_to_another_po(tmp_path, monkeypatch):
    """Two POs for one style are two orders, not two spellings."""
    calls = []
    store = _ai_store(tmp_path, monkeypatch, "ai_po.db",
                      picks={"DK Grey": "Dark Grey"}, calls=calls)
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO_A", color_name="Dark Grey")]))
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO_B", color_name="DK Grey")]))
    assert len(store.list_items(pc_nos=["PC1"])) == 2
    assert calls == []          # no candidates on PO_B, so nothing to ask


def test_an_api_failure_degrades_to_normalisation(tmp_path, monkeypatch):
    """An import must never fail because the AI call did."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "ai_err.db"))
    monkeypatch.setattr(SkyEastStore, "_ai_settings",
                        staticmethod(lambda: (True, "k", "deepseek-chat")))
    import po_extractor.lookups.color_ai_enhance as ai

    def boom(*a, **k):
        raise RuntimeError("api down")
    monkeypatch.setattr(ai, "match_color_to_candidates", boom)

    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="Dark Grey")]))
    store.save_contract_checked(_make_contract([
        _make_item(style="ST1", zalando_po="PO1", color_name="DK Grey")]))
    assert len(store.list_items(pc_nos=["PC1"])) == 2      # duplicate, but no crash


def test_ai_stays_off_without_an_api_key(tmp_path):
    """The toggle alone must not enable it — _ai_settings gates on the key."""
    from po_extractor.store.sky_east_store import SkyEastStore
    from po_extractor.store.app_settings_store import (
        KEY_DEEPSEEK_API_KEY, KEY_ITEM_COLOUR_AI_MATCH,
    )
    from po_extractor.store import app_settings_store as mod
    settings = mod.AppSettingsStore(str(tmp_path / "settings.db"))
    settings.set(KEY_ITEM_COLOUR_AI_MATCH, "true")
    settings.set(KEY_DEEPSEEK_API_KEY, "")

    import po_extractor.store as store_pkg
    real = store_pkg.get_app_settings_store
    store_pkg.get_app_settings_store = lambda: settings
    try:
        assert SkyEastStore._ai_settings()[0] is False
    finally:
        store_pkg.get_app_settings_store = real


def test_ai_matching_is_off_by_default():
    from po_extractor.store.app_settings_store import (
        _DEFAULTS, KEY_ITEM_COLOUR_AI_MATCH,
    )
    assert _DEFAULTS[KEY_ITEM_COLOUR_AI_MATCH] == "false"


# ── Replace vs merge at upload ───────────────────────────────────────────────

def test_replace_drops_items_the_new_file_does_not_list(tmp_path):
    """The point of replace: merge alone can never remove a withdrawn style,
    or a row that duplicated one already on file."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "rep.db"))

    store.save_contract_checked(_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="Red"),
        _make_item(style="B", zalando_po="PO2", color_name="Blue"),
        _make_item(style="GONE", zalando_po="PO3", color_name="Black")]))
    result = store.replace_contract(_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="Red"),
        _make_item(style="B", zalando_po="PO2", color_name="Blue")]))

    assert sorted(store.list_items(pc_nos=["PC1"])["style"]) == ["A", "B"]
    assert result["removed_items"] == [("GONE", "Black", "PO3")]
    assert len(result["new_items"]) == 2


def test_merge_is_still_the_default_and_removes_nothing(tmp_path):
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "mrg.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="Red"),
        _make_item(style="KEEP", zalando_po="PO3", color_name="Black")]))
    store.save_many_contracts_checked([_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="Red")])])
    assert sorted(store.list_items(pc_nos=["PC1"])["style"]) == ["A", "KEEP"]


def test_replace_archives_what_it_removes(tmp_path):
    """A replace run in error has to be recoverable."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "rep_arch.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="GONE", zalando_po="PO3", color_name="Black",
                   sizes={"S": 250}, total_qty=250)]))
    store.replace_contract(_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="Red")]))

    hist = store.list_item_history("PC1", style="GONE")
    assert len(hist) == 1
    assert int(hist.iloc[0]["total_qty"]) == 250


def test_replace_keeps_the_fabric_no_and_contract_no_entered_in_the_app(tmp_path):
    """Neither field is in the contract file. "The file is the whole truth"
    is about which items exist, not about discarding work it never carried."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "rep_keep.db"))

    store.save_contract_checked(_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="(red)")]))
    store.update_item_fields("PC1", "A", "(red)", "PO1",
                             fabric_item_no="HHP-JS-12345", contract_no="26302-ZA9")

    store.replace_contract(_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="Red",   # retyped
                   fabric_item_no="", contract_no="")]))

    row = store.list_items(pc_nos=["PC1"]).iloc[0]
    assert row["fabric_item_no"] == "HHP-JS-12345"
    assert row["contract_no"] == "26302-ZA9"
    assert row["color_name"] == "Red"


def test_the_file_still_wins_when_it_does_carry_those_fields(tmp_path):
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "rep_win.db"))
    store.save_contract_checked(_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="Red",
                   fabric_item_no="OLD", contract_no="OLD-C")]))
    store.replace_contract(_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="Red",
                   fabric_item_no="NEW", contract_no="NEW-C")]))
    row = store.list_items(pc_nos=["PC1"]).iloc[0]
    assert (row["fabric_item_no"], row["contract_no"]) == ("NEW", "NEW-C")


def test_two_files_for_one_pc_only_replace_once(tmp_path):
    """Uploading two files that share a PC No. in replace mode must not have
    the second file's contract wipe the first file's."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "rep_two.db"))
    store.save_many_contracts_checked([
        _make_contract([_make_item(style="A", zalando_po="PO1", color_name="Red")]),
        _make_contract([_make_item(style="B", zalando_po="PO2", color_name="Blue")]),
    ], mode="replace")
    assert sorted(store.list_items(pc_nos=["PC1"])["style"]) == ["A", "B"]


def test_replace_on_a_pc_with_nothing_on_file_is_just_an_insert(tmp_path):
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "rep_new.db"))
    result = store.replace_contract(_make_contract([
        _make_item(style="A", zalando_po="PO1", color_name="Red")]))
    assert result["removed_items"] == []
    assert len(store.list_items(pc_nos=["PC1"])) == 1


def test_replace_reduces_the_real_hhppc053_pollution_to_six_rows(tmp_path):
    """End to end on the actual case: the 7-24 import, then the 7-30 import
    that duplicated it, then a replace with 7-30."""
    from po_extractor.store.sky_east_store import SkyEastStore
    store = SkyEastStore(str(tmp_path / "rep_053.db"))
    old = [_make_item(style=s, zalando_po=po, color_name=c)
           for s, po, c in [("ZLD060", "PO2360361C", "(dark grey)"),
                            ("DR5108", "PO2361469C", "(black)(off-white)"),
                            ("JS5013", "PO2338236C", "(dark blue)")]]
    new = [_make_item(style=s, zalando_po=po, color_name=c)
           for s, po, c in [("ZLD060", "PO2360361C", "Dark Grey"),
                            ("DR5108", "PO2361469C", "black off white"),
                            ("JS5013", "PO2338236C", "dark blue"),
                            ("TR3072", "PO2367024C", "black"),
                            ("DR5252", "PO2367104C", "blue"),
                            ("DR5252", "PO2367103C", "BURGUNDY")]]

    # Simulate the polluted DB this bug produced: raw-colour identity.
    store.save_contract_checked(_make_contract(old))
    for it in new:                       # force the pre-fix duplication
        with store._conn() as conn:
            store._insert_item(conn, it)
    assert len(store.list_items(pc_nos=["PC1"])) == 9

    result = store.replace_contract(_make_contract(new))
    df = store.list_items(pc_nos=["PC1"])
    assert len(df) == 6
    assert len(result["removed_items"]) == 3
    assert sorted(df["color_name"]) == sorted(
        ["Dark Grey", "black off white", "dark blue", "black", "blue", "BURGUNDY"])
