"""Tests for the Cutting Plan module: the Optitex-export parser, the standard
layout exporter (round-trip), the store (plans, PO links, demand comparison)
and the module-permission wiring.

The sample plans these fixtures mirror are real Optitex exports: one where the
markers hit the ordered quantity exactly (single Solution row per colour) and
one where they overcut (Solution splits into 'Order' / 'Real' sub-rows).
"""
from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from po_extractor.exporters.cutting_plan_export import (
    build_standard_cut_plan, plan_header_from_parsed, today_header,
)
from po_extractor.parsers.cutting_plan import (
    CuttingPlanParseError, achieved_rows, parse_cut_plan, parse_cut_plan_grid,
)
from po_extractor.store.cutting_plan_store import (
    CuttingPlanStore, summarise_plan,
)


# ── Fixtures: hand-built grids matching the real export layout ──────────────

def _exact_grid() -> list[list]:
    """Two styles, one colour, one material, demand met exactly."""
    return [
        ["Date", "July 27 - 2026", None, "Time", "18:04"],
        ["Order name", "003_060_20260723_JH"],
        ["Style file 1", r"D:\x\S24DTR003.PDS"],
        ["Style name 1", "S24DTR003"],
        ["Style file 2", r"D:\x\ZLD060.PDS"],
        ["Style name 2", "ZLD060"],
        ["Cut plan operator", "JL"],
        ["Client", "ZR"],
        [],
        ["Output folder path", r"D:\x\20260723"],
        [],
        [None, "Order demands"],
        [None, "Colors", "Sizes"],
        [None, None, "S24DTR003", None, "ZLD060"],
        [None, None, "S", "M", "S", "M"],
        [None, "Wine", 300, 200, 300, 200],
        [None, "Sum", 300, 200, 300, 200],
        [],
        ["Marker Definition"],
        ["Material", "N Markers", "Spreading", "Width, cm", "Length, cm",
         "Min Plies", "Max Plies", "Waste Limits, cm"],
        [],
        ["A", 1, "Single", 157, 600, 1, 200, "0, 0, 0, 0"],
        [],
        ["Marker Ratio"],
        ["Marker", "File Name", "Sizes"],
        [None, None, "S24DTR003", None, "ZLD060"],
        [None, None, "S", "M", "S", "M"],
        [1, r"D:\x\A1.mrk", 3, 2, 3, 2],
        [],
        ["Spreading Plies"],
        ["Marker 1", r"D:\x\A1.mrk", "Sizes", None, None, None,
         "Fabric Length,m", "Efficiency,%", "Cut Length,m",
         "Marker Length,cm", "Material Cost,CNY"],
        ["Colors", "Plies number", "S24DTR003", None, "ZLD060"],
        [None, None, "S", "M", "S", "M"],
        ["Wine", 100, 300, 200, 300, 200, 512.5, 87.5, 110.6, 512.5, 512.5],
        ["Sum", 100, 300, 200, 300, 200, 512.5],
        [],
        ["Solution"],
        [None, "Colors", "Sizes", None, None, None,
         "Total Quantity", "Fabric Length,m"],
        [None, None, "S24DTR003", None, "ZLD060"],
        [None, None, "S", "M", "S", "M"],
        [None, "Wine", 300, 200, 300, 200, 1000, 512.5],
        [],
        ["Total Efficiency", 87.5, "%"],
        ["Total Cost", 512.5, "CNY"],
        ["Total cut length", 110.6, "m"],
        ["Total Tables", 1],
        ["Average Length", 0.95, "m"],
    ]


def _overcut_grid() -> list[list]:
    """One style, one material, markers overcut the order (Order/Real rows)."""
    return [
        ["Date", "July 03 - 2026", None, "Time", "16:29"],
        ["Order name", "003_060_20260703"],
        ["Style name 1", "S24DTR003"],
        ["Cut plan operator", "JL"],
        ["Client", "ZR"],
        [],
        [None, "Order demands"],
        [None, "Colors", "Sizes"],
        [None, None, "S24DTR003"],
        [None, None, "S", "M"],
        [None, "Black", 599, 347],
        [None, "Sum", 599, 347],
        [],
        ["Marker Definition"],
        ["Material", "N Markers", "Spreading", "Width, cm", "Length, cm",
         "Min Plies", "Max Plies", "Waste Limits, cm"],
        [],
        ["A", 1, "Single", 157, 600, 1, 200, "0, 0, 0, 0"],
        [],
        ["Marker Ratio"],
        ["Marker", "File Name", "Sizes"],
        [None, None, "S24DTR003"],
        [None, None, "S", "M"],
        [1, r"D:\x\A1.mrk", 2, 1],
        [],
        ["Spreading Plies"],
        ["Marker 1", r"D:\x\A1.mrk", "Sizes", None,
         "Fabric Length,m", "Efficiency,%", "Cut Length,m",
         "Marker Length,cm", "Material Cost,CNY"],
        ["Colors", "Plies number", "S24DTR003"],
        [None, None, "S", "M"],
        ["Black", 350, 600, 350, 875.0, 86.8, 583.9, 583.9, 875.0],
        ["Sum", 350, 600, 350, 875.0],
        [],
        ["Solution"],
        [None, "Colors", "Quantity", "Sizes", None,
         "Total Quantity", "Fabric Length,m"],
        [None, None, None, "S24DTR003"],
        [None, None, None, "S", "M"],
        [None, "Black", "Order", 599, 347, 946],
        [None, None, "Real", 600, 350, 950, 875.0],
        [],
        ["Total Efficiency", 86.8, "%"],
        ["Total Cost", 875.0, "CNY"],
        ["Total cut length", 583.9, "m"],
        ["Total Tables", 3],
        ["Average Length", 0.06, "m"],
        [],
        ["Total Tables", 3],
    ]


@pytest.fixture
def exact():
    return parse_cut_plan_grid(_exact_grid())


@pytest.fixture
def overcut():
    return parse_cut_plan_grid(_overcut_grid())


@pytest.fixture
def store(tmp_path):
    CuttingPlanStore._checked_paths.clear()
    return CuttingPlanStore(str(tmp_path / "po_history.db"))


# ── Parser ──────────────────────────────────────────────────────────────────

def test_header_fields(exact):
    assert exact["order_name"] == "003_060_20260723_JH"
    assert exact["operator"] == "JL"
    assert exact["client"] == "ZR"
    assert exact["plan_date"] == "July 27 - 2026"
    assert exact["output_folder"] == r"D:\x\20260723"
    assert [s["name"] for s in exact["styles"]] == ["S24DTR003", "ZLD060"]


def test_demands_parsed_per_style_and_size(exact):
    demands = {(d["style"], d["size"]): d["qty"] for d in exact["demands"]}
    assert demands[("S24DTR003", "S")] == 300
    assert demands[("ZLD060", "M")] == 200
    assert exact["colors"] == ["Wine"]


def test_order_qty_is_per_style_not_summed(exact):
    # The same garment is cut from two style files; summing both groups would
    # double the order.
    assert exact["style_totals"] == {"S24DTR003": 500, "ZLD060": 500}
    assert exact["total_qty"] == 500


def test_marker_definition_and_ratio(exact):
    mat = exact["materials"][0]
    assert mat["material"] == "A"
    assert mat["width_cm"] == 157
    assert mat["max_plies"] == 200
    ratio = {(c["style"], c["size"]): c["qty"]
             for c in mat["markers"][0]["ratio"]}
    assert ratio[("S24DTR003", "S")] == 3
    assert ratio[("ZLD060", "M")] == 2


def test_spreading_plies_rows_and_metrics(exact):
    spread = exact["materials"][0]["spreads"][0]
    assert spread["marker_no"] == 1
    row = spread["rows"][0]
    assert row["color"] == "Wine"
    assert row["plies"] == 100
    assert row["fabric_length_m"] == 512.5
    assert row["efficiency_pct"] == 87.5
    assert row["marker_length_cm"] == 512.5
    assert sum(p["qty"] for p in row["pieces"]) == 1000


def test_material_totals(exact):
    mat = exact["materials"][0]
    assert mat["total_tables"] == 1
    assert mat["total_efficiency_pct"] == 87.5
    assert mat["total_cut_length_m"] == 110.6
    assert mat["cut_qty"] == 1000


def test_overcut_solution_splits_order_and_real(overcut):
    sol = overcut["materials"][0]["solution"]
    assert [s["kind"] for s in sol] == ["order", "real"]
    # The colour label appears only on the first sub-row but carries down.
    assert {s["color"] for s in sol} == {"Black"}
    real = achieved_rows(sol)
    assert len(real) == 1 and real[0]["total_qty"] == 950
    assert real[0]["fabric_length_m"] == 875.0


def test_overcut_cut_qty_uses_real_row(overcut):
    assert overcut["materials"][0]["cut_qty"] == 950
    assert overcut["total_qty"] == 946          # ordered
    assert summarise_plan(overcut)["cut_qty"] == 950


def test_trailing_grand_total_does_not_overwrite_material_tables(overcut):
    # 'Total Tables' appears twice at the end of a one-material plan; the
    # material's own count must survive.
    assert overcut["materials"][0]["total_tables"] == 3
    assert overcut["total_tables"] == 3


def test_non_cut_plan_workbook_is_rejected():
    with pytest.raises(CuttingPlanParseError):
        parse_cut_plan_grid([["Invoice"], ["Item", "Qty"], ["Shirt", 10]])


def test_empty_grid_is_rejected():
    with pytest.raises(CuttingPlanParseError):
        parse_cut_plan_grid([])


# ── Summary ─────────────────────────────────────────────────────────────────

def test_summarise_plan_efficiency_is_fabric_weighted():
    plan = {
        "style_totals": {"S": 100},
        "materials": [
            {"material": "A", "n_markers": 2, "fabric_length_m": 900.0,
             "total_efficiency_pct": 90.0, "total_tables": 2, "solution": []},
            {"material": "L", "n_markers": 1, "fabric_length_m": 100.0,
             "total_efficiency_pct": 50.0, "total_tables": 1, "solution": []},
        ],
        "total_tables": 3,
    }
    s = summarise_plan(plan)
    assert s["fabric_length_m"] == 1000.0
    assert s["efficiency_pct"] == pytest.approx(86.0)   # not the 70.0 mean
    assert s["total_markers"] == 3


def test_summarise_plan_cut_qty_not_multiplied_by_materials(exact):
    # Shell and lining each cut the same garments; cut qty must not double.
    two_materials = dict(exact)
    two_materials["materials"] = exact["materials"] + exact["materials"]
    assert summarise_plan(two_materials)["cut_qty"] == 500


# ── Exporter round-trip ─────────────────────────────────────────────────────

def _groups_and_qty(plan):
    groups: dict[str, list[str]] = {}
    qty: dict[tuple[str, str, str], int] = {}
    colors: list[str] = []
    for d in plan["demands"]:
        groups.setdefault(d["style"], [])
        if d["size"] not in groups[d["style"]]:
            groups[d["style"]].append(d["size"])
        if d["color"] not in colors:
            colors.append(d["color"])
        qty[(d["style"], d["color"], d["size"])] = d["qty"]
    return list(groups.items()), colors, qty


@pytest.mark.parametrize("fixture_name", ["exact", "overcut"])
def test_standard_export_round_trips(fixture_name, request):
    plan = request.getfixturevalue(fixture_name)
    groups, colors, qty = _groups_and_qty(plan)
    data = build_standard_cut_plan(
        header=plan_header_from_parsed(plan), groups=groups, colors=colors,
        demand_qty=qty, materials=plan["materials"])
    again = parse_cut_plan(io.BytesIO(data))

    assert again["order_name"] == plan["order_name"]
    assert again["style_totals"] == plan["style_totals"]
    assert again["total_tables"] == plan["total_tables"]
    assert len(again["materials"]) == len(plan["materials"])
    for before, after in zip(plan["materials"], again["materials"]):
        assert after["material"] == before["material"]
        assert after["n_markers"] == before["n_markers"]
        assert after["total_tables"] == before["total_tables"]
        assert after["cut_qty"] == before["cut_qty"]
        assert len(after["markers"]) == len(before["markers"])
        assert ([len(s["rows"]) for s in after["spreads"]]
                == [len(s["rows"]) for s in before["spreads"]])


def test_export_without_materials_writes_blank_scaffold():
    data = build_standard_cut_plan(
        header=today_header("PC-1", client="ZR",
                            styles=[{"name": "STY1", "file": ""}]),
        groups=[("STY1", ["S", "M"])], colors=["Black"],
        demand_qty={("STY1", "Black", "S"): 10, ("STY1", "Black", "M"): 20},
        materials=[])
    ws = load_workbook(io.BytesIO(data)).worksheets[0]
    labels = {str(c.value).strip() for row in ws.iter_rows()
              for c in row if c.value}
    # The standard sections are present even with nothing to put in them.
    for section in ("Order demands", "Marker Definition", "Marker Ratio",
                    "Spreading Plies", "Solution", "Total Tables"):
        assert section in labels
    # And the PO quantities made it in.
    assert 10 in {c.value for row in ws.iter_rows() for c in row}


def test_parser_records_each_materials_column_order(exact):
    assert exact["materials"][0]["groups"] == [
        ("S24DTR003", ["S", "M"]), ("ZLD060", ["S", "M"])]


def test_material_size_order_survives_unrelated_po_style_codes(exact):
    """The PO uses the client's style codes, the plan uses the CAD style
    names, so the demand matrix can't order the plan's sizes — the material's
    own recorded order must be used instead of the cell-encounter order."""
    data = build_standard_cut_plan(
        header=plan_header_from_parsed(exact),
        groups=[("TP5016", ["S", "M"])],          # PO style code, not the plan's
        colors=["Wine"],
        demand_qty={("TP5016", "Wine", "S"): 10, ("TP5016", "Wine", "M"): 20},
        materials=exact["materials"])
    again = parse_cut_plan(io.BytesIO(data))
    assert again["materials"][0]["groups"] == [
        ("S24DTR003", ["S", "M"]), ("ZLD060", ["S", "M"])]
    ratio = {(c["style"], c["size"]): c["qty"]
             for c in again["materials"][0]["markers"][0]["ratio"]}
    assert ratio == {("S24DTR003", "S"): 3, ("S24DTR003", "M"): 2,
                     ("ZLD060", "S"): 3, ("ZLD060", "M"): 2}


def test_material_groups_fall_back_to_canonical_size_order():
    """A plan stored before the column order was recorded still exports with
    sizes in a sane order rather than whichever marker was read first."""
    from po_extractor.exporters.cutting_plan_export import _material_groups
    mat = {
        "markers": [{"marker_no": 1, "ratio": [
            {"style": "STY", "size": "XL", "qty": 1},
            {"style": "STY", "size": "S", "qty": 1},
            {"style": "STY", "size": "M", "qty": 1},
        ]}],
        "spreads": [], "solution": [],
    }
    assert _material_groups(mat, fallback=[("OTHER", ["S", "M"])]) == [
        ("STY", ["S", "M", "XL"])]


def test_export_demands_come_from_the_po_not_the_plan(exact):
    """The whole point of standardising: the sheet shows what was ordered."""
    data = build_standard_cut_plan(
        header=plan_header_from_parsed(exact),
        groups=[("S24DTR003", ["S"])], colors=["Wine"],
        demand_qty={("S24DTR003", "Wine", "S"): 999},
        materials=exact["materials"])
    again = parse_cut_plan(io.BytesIO(data))
    assert again["demands"] == [
        {"style": "S24DTR003", "color": "Wine", "size": "S", "qty": 999}]


# ── Store ───────────────────────────────────────────────────────────────────

def test_save_and_get_plan(store, exact):
    pid = store.save_plan(exact, source_file="plan.xlsx", file_bytes=b"xyz",
                          uploaded_by="jl", notes="first run",
                          links=[{"pc_no": "PC1", "po_no": "PO1"}])
    rec = store.get_plan(pid)
    assert rec["plan_name"] == "003_060_20260723_JH"
    assert rec["order_qty"] == 500
    assert rec["notes"] == "first run"
    assert rec["parsed"]["materials"][0]["material"] == "A"
    assert rec["links"] == [
        {"source": "sky_east", "pc_no": "PC1", "po_no": "PO1",
         "linked_at": rec["links"][0]["linked_at"], "linked_by": "jl"}]


def test_list_plans_counts_links(store, exact):
    store.save_plan(exact, source_file="a.xlsx", links=[
        {"pc_no": "PC1", "po_no": "PO1"}, {"pc_no": "PC1", "po_no": "PO2"}])
    df = store.list_plans()
    assert len(df) == 1
    assert int(df.iloc[0]["linked_pos"]) == 2


def test_one_plan_links_to_many_pos_and_lookup_works_either_way(store, exact):
    pid = store.save_plan(exact, source_file="a.xlsx", links=[
        {"pc_no": "PC1", "po_no": "PO1"},
        {"pc_no": "PC2", "po_no": "PO2"},
    ])
    by_pc = store.plans_for_pos(pc_nos=["PC2"])
    by_po = store.plans_for_pos(po_nos=["PO1"])
    assert by_pc.iloc[0]["plan_id"] == pid
    assert by_po.iloc[0]["plan_id"] == pid
    assert store.plans_for_pos(pc_nos=["NOPE"]).empty


def test_set_links_replaces_previous_links(store, exact):
    pid = store.save_plan(exact, source_file="a.xlsx",
                          links=[{"pc_no": "PC1", "po_no": "PO1"}])
    store.set_links(pid, [{"pc_no": "PC9", "po_no": "PO9"}], "jl")
    links = store.get_plan(pid)["links"]
    assert [(l["pc_no"], l["po_no"]) for l in links] == [("PC9", "PO9")]


def test_duplicate_links_are_collapsed(store, exact):
    pid = store.save_plan(exact, source_file="a.xlsx", links=[
        {"pc_no": "PC1", "po_no": "PO1"},
        {"pc_no": "PC1", "po_no": "PO1"},
    ])
    assert len(store.get_plan(pid)["links"]) == 1


def test_demands_table_records_ordered_and_cut(store, overcut):
    pid = store.save_plan(overcut, source_file="a.xlsx")
    df = store.list_demands(pid)
    row = df[(df["style"] == "S24DTR003") & (df["size"] == "M")].iloc[0]
    assert int(row["qty"]) == 347        # ordered
    assert int(row["cut_qty"]) == 350    # cut


def test_original_file_round_trips(store, exact):
    pid = store.save_plan(exact, source_file="plan.xlsx", file_bytes=b"binary")
    assert store.get_plan_file(pid) == ("plan.xlsx", b"binary")


def test_find_by_hash_flags_a_re_upload(store, exact):
    store.save_plan(exact, source_file="plan.xlsx", file_bytes=b"binary",
                    uploaded_by="jl")
    hit = store.find_by_hash(b"binary")
    assert hit and hit["uploaded_by"] == "jl"
    assert store.find_by_hash(b"other") is None


def test_delete_plan_removes_links_and_demands(store, exact):
    pid = store.save_plan(exact, source_file="a.xlsx",
                          links=[{"pc_no": "PC1", "po_no": "PO1"}])
    assert store.delete_plan(pid) is True
    assert store.get_plan(pid) is None
    assert store.list_demands(pid).empty
    assert store.plans_for_pos(pc_nos=["PC1"]).empty
    assert store.count() == 0


# ── Permissions ─────────────────────────────────────────────────────────────

def test_cutting_plan_is_its_own_module():
    from auth.users import (
        ALL_MODULES, MODULE_CUTTING_PLAN, MODULE_LABELS, MODULE_SKY_EAST,
        MODULE_SKY_EAST_BUYPLAN,
    )
    assert MODULE_CUTTING_PLAN in ALL_MODULES
    assert MODULE_CUTTING_PLAN in MODULE_LABELS
    assert MODULE_CUTTING_PLAN not in (MODULE_SKY_EAST, MODULE_SKY_EAST_BUYPLAN)


def test_sky_east_modules_do_not_grant_cutting_plan():
    """A Buy Plan user must not see cut plans (marker cost/efficiency)."""
    from auth.users import (
        MODULE_CUTTING_PLAN, MODULE_SKY_EAST, MODULE_SKY_EAST_BUYPLAN,
    )

    def allowed(module_key: str, user_modules: list[str]) -> bool:
        # Mirrors app.py's _allowed().
        if not user_modules:
            return True
        if module_key == "sky_east":
            return (MODULE_SKY_EAST in user_modules
                    or MODULE_SKY_EAST_BUYPLAN in user_modules)
        return module_key in user_modules

    buyplan_user = [MODULE_SKY_EAST_BUYPLAN]
    assert allowed("sky_east", buyplan_user) is True
    assert allowed(MODULE_CUTTING_PLAN, buyplan_user) is False

    full_se_user = [MODULE_SKY_EAST]
    assert allowed(MODULE_CUTTING_PLAN, full_se_user) is False

    granted = [MODULE_SKY_EAST_BUYPLAN, MODULE_CUTTING_PLAN]
    assert allowed(MODULE_CUTTING_PLAN, granted) is True
