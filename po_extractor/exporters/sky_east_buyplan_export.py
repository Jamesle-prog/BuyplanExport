"""Sky East buy-plan export — Python port of VBA CreateBuyPlan_template2.

Two public entry points
-----------------------
export_sky_east_buyplan(df_items, cn_lookup, output_dir)
    → one Excel file, one sheet per style (Sky_East.xlsx template)
    → includes fabric-header cells (B2:E4), Q5 style total, Index sheet

export_sky_east_nukuryou(df_items, cn_lookup, output_dir)
    → list of Excel files, one per distinct fabric_item_no
      (Sky_East_P.xlsx template; one sheet per style within each workbook)

Both mirror the VBA subs:
    CreateBuyPlan_template2 / ProcessSKU / ProcessDataGrouping
    CreateZalando核料Workbooks

Data-row column layout (1-based, matching the Template sheet):
    A=合同号  B=Style  C=Brand  D=Article  E=PO  F=ConfigSKU
    G=ColorEN  H=ColorCN  I=主标色
    J=XS  K=S  L=M  M=L  N=XL  O=XXL
    P=船样要求 (blank — not in data model)
    Q=Total  R=EX-FTY

Fabric-header rows (rows 2-5, above data):
    B=大身 (body part)  C=HHN code  D=面料成分  E=综合标识Key
"""
from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from ._sky_east_helpers import *  # noqa: F401,F403
from ..utils.file_utils import versioned_path
from ..store.color_translation_store import _normalize_color_name as _nz_color
from auth.companies import COMPANY_SKY_EAST


def _apply_sky_east_compact_layout(ws, *, last_row: int) -> None:
    """User-requested compact layout overrides applied after data is filled.

      • Every populated cell uses font size 10 (preserves bold/colour).
      • Columns A–I and P–R = width 20.
      • Columns J–O (sizes) = width 6.
      • Every row 1..last_row+1 = height 28pt.
    """
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter as _gcl

    SIZE_COLS = set(range(10, 16))   # J-O
    for row in ws.iter_rows(min_row=1, max_row=last_row + 1, min_col=1, max_col=18):
        for cell in row:
            f = cell.font
            try:
                cell.font = Font(
                    name=f.name, size=10, bold=f.bold, italic=f.italic,
                    vertAlign=f.vertAlign, underline=f.underline,
                    strike=f.strike, color=f.color,
                )
            except Exception:
                pass

    for col_idx in range(1, 19):    # A..R
        letter = _gcl(col_idx)
        ws.column_dimensions[letter].width = 6 if col_idx in SIZE_COLS else 20

    for r in range(1, max(last_row + 2, 14)):
        ws.row_dimensions[r].height = 28


# ---------------------------------------------------------------------------
# Main buy plan  (Template sheet → one sheet per style)
# ---------------------------------------------------------------------------

def export_sky_east_buyplan(
    df_items: pd.DataFrame,
    cn_lookup: dict,
    output_dir: str,
    fabric_parts_by_style: dict | None = None,
    style_image_map: dict | None = None,
    label_lookup: dict | None = None,
) -> str:
    """Generate the main Sky East buy plan.

    Parameters
    ----------
    df_items             : ``SkyEastStore.list_items()`` result
    cn_lookup            : ``ColorTranslationStore.build_lookup_dict()`` result
                           — ``{(client, brand, en_color): cn_color}``.
    output_dir           : directory to write the output file
    fabric_parts_by_style: optional ``{style: [FabricPart, ...]}`` mapping from
                           ``POStore.load_fabric_parts_for_styles()``.  When
                           provided, writes the 综合标识Key (display_key) to
                           column E of each fabric-slot row in the style sheet.
                           Falls back to the single ``fabric_item_no`` field from
                           ``df_items`` when absent.
    style_image_map      : optional ``{style_name: image_bytes}`` — when provided,
                           a "图片" thumbnail column is added to the Index sheet
                           next to "款号".
    label_lookup         : optional ``{(client, brand, en_color): label_color}``
                           returned by
                           ``ColorTranslationStore.build_label_lookup_dict()``.
                           When None, the exporter fetches it from the canonical
                           DB itself.  Pass an explicit empty dict to disable
                           DB-driven label lookup entirely.

    Returns
    -------
    Absolute path of the saved .xlsx file.
    """
    # Auto-fetch label_lookup from the canonical store when not provided.
    # Single source of truth: the same DB as cn_lookup.
    if label_lookup is None:
        try:
            from ..store import get_color_translation_store
            label_lookup = get_color_translation_store().build_label_lookup_dict()
        except Exception as exc:
            import warnings as _w
            _w.warn(f"[sky_east buyplan] label_color lookup failed: {exc!r}")
            label_lookup = {}
    if not _SE_TEMPLATE.exists():
        raise FileNotFoundError(f"Sky East template not found: {_SE_TEMPLATE}")

    path       = versioned_path(output_dir, "Sky_East_BuyPlan", ".xlsx")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tpl_wb = load_workbook(str(_SE_TEMPLATE))
    tpl_ws = tpl_wb.worksheets[0]

    # ── Detect column layout and data start row from the template ─────────
    col, data_row = _detect_buyplan_layout(tpl_ws)
    fabric_rows   = _detect_fabric_rows(tpl_ws, max_row=data_row - 1)

    # ── Apply user-configured overrides (Sky_East_config.json) ─────────────
    # Configured values win over auto-detection, so admins can override the
    # template scan without rebuilding the .xlsx.
    col, data_row, fabric_rows = _apply_config_overrides(
        "sky_east_buyplan", col, data_row, fabric_rows,
    )

    # Compute the column letter for the style-total anchor cell (row 5)
    from openpyxl.utils import get_column_letter as _gcl
    total_col_letter = _gcl(col["total"])
    total_anchor     = f"{total_col_letter}5"   # e.g. "Q5"

    # Style totals for cross-comparison: {style: int}
    style_totals: dict[str, int] = {}

    # ── Pre-fetch 船样要求 for all brands in one batch ────────────────────────
    _BOAT_SAMPLE_COL = 16   # column P
    bsr_cache: dict[str, str] = {}
    try:
        if "brand" in df_items.columns:
            all_brands = [
                str(b).strip() for b in df_items["brand"].dropna().unique() if b
            ]
            if all_brands:
                from ..store import get_boat_sample_store
                bsr_cache = get_boat_sample_store().get_batch(
                    COMPANY_SKY_EAST, all_brands
                ) or {}
    except Exception as exc:
        import warnings as _w
        _w.warn(f"[sky_east buyplan] boat_sample lookup failed: {exc!r}")
        bsr_cache = {}

    # ── Pre-fetch fabric_master display_key for all HHN codes in one batch ─
    fm_cache: dict = {}
    try:
        all_hhns: set = set()
        if fabric_parts_by_style:
            for _parts in fabric_parts_by_style.values():
                for fp in _parts or []:
                    h = str(getattr(fp, "hhn_no", "") or "").strip()
                    if h:
                        all_hhns.add(h)
        # Also include fallback fabric_item_no values from df_items
        if "fabric_item_no" in df_items.columns:
            for v in df_items["fabric_item_no"].dropna().astype(str):
                v = v.strip()
                if v:
                    all_hhns.add(v)
        if all_hhns:
            from ..store import get_fabric_master_store
            fm_cache = get_fabric_master_store().get_batch_enrichment(
                list(all_hhns)
            ) or {}
    except Exception as exc:
        # Silent failures here have masked real bugs in the past — make
        # the cause visible (the buyplan still proceeds with an empty cache).
        import warnings as _w
        _w.warn(f"[sky_east buyplan] fabric_master lookup failed: {exc!r}")
        fm_cache = {}

    # Build a normalised case-insensitive index over the cache so HHN codes
    # with stray whitespace / case differences still match.
    _fm_cache_lc: dict[str, dict] = {
        str(k).strip().lower(): v
        for k, v in (fm_cache or {}).items()
        if isinstance(k, str)
    }
    _fm_misses: set[str] = set()

    def _display_key_for(hhn: str,
                         fallback_composition: str = "",
                         fallback_gsm=None,
                         fallback_width=None) -> str:
        """Return 综合标识Key for *hhn* (format: ``quality_no|composition|gsm|width``).

        DB-first resolution:
          1. Always read from the pre-fetched fabric master cache when the
             HHN exists there, even partially — so the value reflects the
             current DB state, not stale data the caller may have passed in.
             • If ``display_key`` is populated, use it verbatim.
             • Otherwise rebuild ``quality_no|composition|gsm|width`` from
               the DB columns.  Caller fallbacks are *only* consulted for
               fields that are NULL/0 in the DB record.
          2. When the HHN is not in the DB at all, fall back to the caller's
             values (FabricPart / item-row) so the user still sees something
             useful — and the HHN is recorded as a "miss" for diagnostics.

        Lookup is whitespace-insensitive and case-insensitive.
        Returns empty string only when *hhn* itself is empty.
        """
        if not hhn:
            return ""
        h = str(hhn).strip()
        rec = fm_cache.get(h) or _fm_cache_lc.get(h.lower())

        if rec is not None:
            dk = str(rec.get("display_key") or "").strip()
            if dk:
                return dk
            qno   = str(rec.get("quality_no")     or h).strip()
            db_comp  = str(rec.get("composition_en") or "").strip()
            db_gsm   = rec.get("weight_gsm")
            db_width = rec.get("cuttable_width_cm")
            comp     = db_comp     or str(fallback_composition or "").strip()
            gsm      = db_gsm      or fallback_gsm
            width    = db_width    or fallback_width
            gsm_s   = str(int(gsm))   if gsm   else ""
            width_s = str(int(width)) if width else ""
            return f"{qno}|{comp}|{gsm_s}|{width_s}"

        # HHN not in fabric master — record the miss for the diagnostic
        # warning and build a best-effort partial key from caller fallbacks.
        _fm_misses.add(h)
        comp    = str(fallback_composition or "").strip()
        gsm_s   = str(int(fallback_gsm))   if fallback_gsm   else ""
        width_s = str(int(fallback_width)) if fallback_width else ""
        if comp or gsm_s or width_s:
            return f"{h}|{comp}|{gsm_s}|{width_s}"
        return h


    # Each (style, fabric-part) combination gets its own sheet.
    # A style with N fabric parts in fabric_parts_by_style produces N sheets,
    # each carrying exactly one fabric in the header row.
    # Styles with no fabric mapping produce one sheet using the fallback
    # fabric_item_no from df_items (existing behaviour).
    # Seed the uniqueness set with sheets already in the workbook (notably
    # the master template, e.g. "ZLD060_S24DTR003_HHN-DB-YS24078").
    # Otherwise the first style whose cleaned name happens to match the
    # template's name triggers a silent auto-rename inside copy_worksheet
    # → the recorded sheet_meta points at a non-existent sheet → the
    # Index row's hyperlink and total formula both break.
    _used_sheet_names: set[str] = set(tpl_wb.sheetnames)
    _sheet_meta_list:  list[dict] = []

    for style, style_df in df_items.groupby("style", sort=False):
        style = str(style or "").strip()
        if not style:
            continue

        first = style_df.iloc[0]
        parts = (fabric_parts_by_style or {}).get(style, []) if fabric_parts_by_style else []

        # Group fabric parts by combo_idx → {0: [fp, fp], 1: [fp, fp], …}
        # Each combination becomes one sheet.  Styles without mapping get one
        # pass with an empty combo (None sentinel) — falls back to df_items.
        combos: dict[int, list] = {}
        for _fp in parts:
            combos.setdefault(_fp.combo_idx, []).append(_fp)
        # Produce ordered list of combos; use [None] sentinel when none exist.
        combo_list: list = [combos[k] for k in sorted(combos)] if combos else [None]

        for combo_parts in combo_list:
            # ── Unique sheet name ─────────────────────────────────────────
            # Name after style + first HHN in this combination (most informative).
            if combo_parts is not None:
                _first_hhn = next(
                    (str(fp.hhn_no or "") for fp in combo_parts if fp.hhn_no), ""
                )
                _base_sn = _clean_sheet_name(
                    f"{style}_{_first_hhn}" if _first_hhn else style
                )
            else:
                _base_sn = _clean_sheet_name(style)
            _sn, _sfx = _base_sn, 2
            while _sn in _used_sheet_names:
                _suffix = f"_{_sfx}"
                # Trim base to leave room for suffix so the clipped name is unique.
                _trimmed = _base_sn[:31 - len(_suffix)]
                _sn = _clean_sheet_name(f"{_trimmed}{_suffix}")
                _sfx += 1
            sheet_title = _sn
            _used_sheet_names.add(sheet_title)

            ws = tpl_wb.copy_worksheet(tpl_ws)
            ws.title = sheet_title
            # Defensive: openpyxl may auto-suffix when the title collides
            # with an existing sheet (e.g. the master template).  Always
            # use the *actual* title for downstream metadata so Index
            # hyperlinks and total formulas resolve correctly.
            sheet_title = ws.title

            # ── Fill {{placeholders}} in template header ──────────────────
            _replace_placeholders(ws, {
                "created_at": created_at,
                "style":      style,
            })

            # ── Always-on date cells ──────────────────────────────────────
            # The template doesn't ship with a {{created_at}} placeholder; the
            # 制单日期 / 修改日期 labels live in J1 / J2 with the value cells
            # K-O on the same row.  Merge K..O so the date is visible across
            # the highlighted rectangle even when J-O columns are narrow,
            # then write the value to K (top-left of the merge).
            for rng in ("K1:O1", "K2:O2"):
                if rng not in (str(m) for m in ws.merged_cells.ranges):
                    try:
                        ws.merge_cells(rng)
                    except Exception:
                        pass
            ws["K1"] = created_at
            ws["K2"] = created_at

            # ── Embed Photo1 (front) and Photo2 (back) from style_image_map ──
            # Always call _embed_style_photos so placeholder text is cleared even
            # when no image is available for this style.
            _imgs  = (style_image_map or {}).get(style) or [] if style_image_map is not None else []
            _front = _imgs[0] if len(_imgs) > 0 else None
            _back  = _imgs[1] if len(_imgs) > 1 else None
            _embed_style_photos(ws, _front, _back)

            # ── Fabric header — all fabrics in this combination ───────────
            # Each combo_part maps to one fabric-slot row (slot 0 = row 2, etc.).
            # Layout: B=body part  C=HHN code  D=composition  E=综合标识Key
            # The 综合标识Key encodes quality_no|composition_en|gsm|width.
            # fabrication from df_items is used as a composition fallback when
            # the FabricPart has no composition and the HHN is not in fabric master.
            _fabrication_fb = str(first.get("fabrication", "") or "")

            if combo_parts is not None:
                for slot_idx, fp in enumerate(combo_parts[:len(fabric_rows)]):
                    frow, body_c, hhn_c, _comp_c, dk_c = fabric_rows[slot_idx]
                    _hhn = str(getattr(fp, "hhn_no", "") or "")
                    _comp_fb = (str(getattr(fp, "composition", "") or "")
                                or _fabrication_fb)
                    ws.cell(frow, body_c).value = str(getattr(fp, "body_part", "") or "")
                    ws.cell(frow, hhn_c).value  = None           # cleared — HHN already in 综合标识Key
                    ws.cell(frow, dk_c).value   = _display_key_for(
                        _hhn,
                        fallback_composition=_comp_fb,
                        fallback_gsm  =getattr(fp, "weight_gsm", None) or None,
                        fallback_width=getattr(fp, "width_cm",  None) or None,
                    )
                    # Defensive: clear column E in case an older config put the
                    # display key there.  The value belongs in D (under the
                    # template's "面料编号|成分|克重|有效门幅" header).
                    if dk_c != 5:
                        ws.cell(frow, 5).value = None
            else:
                # Fallback: populate first slot from sky_east_items columns
                if fabric_rows:
                    frow, _body_c, hhn_c, _comp_c, dk_c = fabric_rows[0]
                    hhn_fb = str(first.get("fabric_item_no", "") or "")
                    ws.cell(frow, hhn_c).value = None            # cleared — HHN already in 综合标识Key
                    ws.cell(frow, dk_c).value  = _display_key_for(
                        hhn_fb,
                        fallback_composition=_fabrication_fb,
                    )
                    if dk_c != 5:
                        ws.cell(frow, 5).value = None

            # ── Clear data area ───────────────────────────────────────────
            _clear_data_area(ws, data_row)

            # ── Group by (PONo | ConfigSKU | ColorDesc) — mirrors VBA grpKey ─
            grp_cols = [c for c in ["zalando_po", "config_sku", "color_name"]
                        if c in style_df.columns]
            groups = list(style_df.groupby(grp_cols, sort=False))

            out_row     = data_row
            style_total = 0

            for _key, grp_df in groups:
                g = grp_df.iloc[0]

                color_en = str(g.get("color_name", "") or "")
                brand    = str(g.get("brand",       "") or "")
                color_cn = _cn_color(cn_lookup, brand, color_en)

                xs  = int(grp_df["xs"].sum()  if "xs"  in grp_df.columns else 0)
                s   = int(grp_df["s"].sum()   if "s"   in grp_df.columns else 0)
                m   = int(grp_df["m"].sum()   if "m"   in grp_df.columns else 0)
                l   = int(grp_df["l"].sum()   if "l"   in grp_df.columns else 0)
                xl  = int(grp_df["xl"].sum()  if "xl"  in grp_df.columns else 0)
                xxl = int(grp_df["xxl"].sum() if "xxl" in grp_df.columns else 0)
                row_total = xs + s + m + l + xl + xxl
                style_total += row_total

                _style_data(ws.cell(out_row, col["contract"]),  str(g.get("contract_no",  "") or ""))
                _style_data(ws.cell(out_row, col["style"]),     style)
                _style_data(ws.cell(out_row, col["brand"]),     brand)
                _style_data(ws.cell(out_row, col["article"]),   str(g.get("article_name", "") or ""))
                _style_data(ws.cell(out_row, col["po"]),        str(g.get("zalando_po",   "") or ""))
                _style_data(ws.cell(out_row, col["config"]),    str(g.get("config_sku",   "") or ""))
                _style_data(ws.cell(out_row, col["color_en"]),  color_en)
                _style_data(ws.cell(out_row, col["color_cn"]),  color_cn)
                # 主标颜色 resolution order (single source of truth):
                #   1. ColorTranslationStore.label_color for (client, brand, en)
                #   2. Brand-agnostic fallback in the same store
                #   3. Auto-derive from the English body colour
                #      (light → 黑色, dark → 白色)
                _label_clr = ""
                if label_lookup:
                    # Same normalisation as build_label_lookup_dict() — case-insensitive.
                    _norm_en = _nz_color(color_en)
                    _label_clr = (
                        label_lookup.get((COMPANY_SKY_EAST, brand, _norm_en))
                        or label_lookup.get((COMPANY_SKY_EAST, "", _norm_en))
                        or ""
                    )
                if not _label_clr:
                    _label_clr = derive_main_label_color(color_en)
                _style_data(ws.cell(out_row, col["label_clr"]), _label_clr)
                _style_data(ws.cell(out_row, col["xs"]),  xs)
                _style_data(ws.cell(out_row, col["s"]),   s)
                _style_data(ws.cell(out_row, col["m"]),   m)
                _style_data(ws.cell(out_row, col["l"]),   l)
                _style_data(ws.cell(out_row, col["xl"]),  xl)
                _style_data(ws.cell(out_row, col["xxl"]), xxl)
                # col P = 船样要求 — inject from BoatSampleStore if available
                _boat_req = bsr_cache.get(brand, "")
                if _boat_req:
                    _style_data(ws.cell(out_row, _BOAT_SAMPLE_COL), _boat_req)
                _style_data(ws.cell(out_row, col["total"]),  row_total)
                _style_data(ws.cell(out_row, col["ex_fty"]),
                            str(g.get("ex_fty_date", "") or ""))

                out_row += 1

            # Grand-total row (only when >1 data rows, matching VBA logic)
            if len(groups) > 1:
                _style_total(ws.cell(out_row, col["style"]), "Total")
                _style_total(ws.cell(out_row, col["total"]), style_total)

            # Style-total anchor cell (detected dynamically, e.g. "Q5")
            ws[total_anchor] = style_total
            style_totals[style] = style_total   # same total for all fabric sheets

            # ── Apply dynamic column widths & row heights ─────────────────
            _set_sheet_column_widths(ws, col, data_start_row=data_row)

            # ── User-requested compact layout overrides ───────────────────
            # font 10 / width 20 (sizes 6) / row height 20.
            _apply_sky_east_compact_layout(ws, last_row=out_row)

            # ── Collect metadata for Index sheet ─────────────────────────
            # Show the first fabric in the combination as the representative entry.
            _idx_fp = combo_parts[0] if combo_parts else None
            _sheet_meta_list.append({
                "style":       style,
                "sheet_name":  sheet_title,
                "brand":       str(first.get("brand",       "") or ""),
                "body_part":   str(getattr(_idx_fp, "body_part", "") or "") if _idx_fp else "",
                "hhn_no":      (str(getattr(_idx_fp, "hhn_no", "") or "") if _idx_fp
                                else str(first.get("fabric_item_no", "") or "")),
                "ex_fty_date": str(first.get("ex_fty_date", "") or ""),
            })

    # ── Remove master template sheet ─────────────────────────────────────
    if tpl_ws in tpl_wb.worksheets:
        tpl_wb.remove(tpl_ws)

    # ── Index sheet (VBA CreateIndexSheet) ───────────────────────────────
    _create_index_sheet(tpl_wb, df_items, total_anchor=total_anchor,
                        style_image_map=style_image_map,
                        sheet_meta_list=_sheet_meta_list)

    if not tpl_wb.sheetnames:
        tpl_wb.create_sheet("Empty")

    tpl_wb.save(str(path))

    # ── 综合key diagnostic — surface HHNs missing from fabric_master ──────
    # The buyplan reads the 综合key directly from the fabric_master DB.
    # When some HHNs aren't there yet, the produced key only has whatever
    # the caller could supply (often weight + width are blank → trailing
    # ``||``).  Warn loudly so the user knows to import those fabrics.
    if _fm_misses:
        import warnings as _w
        preview = ", ".join(sorted(_fm_misses)[:8])
        if len(_fm_misses) > 8:
            preview += f" … +{len(_fm_misses) - 8} more"
        _w.warn(
            f"[sky_east buyplan] 综合key partial — {len(_fm_misses)} HHN code(s) "
            f"not in fabric_master DB: {preview}"
        )
    return str(path), style_totals


# ---------------------------------------------------------------------------
# 核料 workbooks  (Template_P sheet → one workbook per fabric)
# ---------------------------------------------------------------------------

def check_nukuryou_ready(df_items: pd.DataFrame) -> str | None:
    """Return None if 核料 workbooks can be generated, or a human-readable reason string.

    Checks three conditions in order:
    1. Template_P file exists on disk
    2. ``fabric_item_no`` column is present in ``df_items``
    3. At least one row has a non-empty ``fabric_item_no``
    """
    if not _SE_TEMPLATE_P.exists():
        return (
            f"Template_P (Sky_East_P.xlsx) not found at:\n{_SE_TEMPLATE_P}\n"
            "Upload it via Admin → Templates → Sky East Template_P."
        )
    fabric_col = "fabric_item_no"
    if fabric_col not in df_items.columns:
        return "fabric_item_no column is missing from items data — please re-import the Sky East contracts."
    has_fabric = df_items[fabric_col].fillna("").astype(str).str.strip().ne("").any()
    if not has_fabric:
        return (
            "No styles have a fabric HHN code filled in.\n"
            "Open the Sky East → Items tab, fill in the 面料编号 (HHN No.) for each style, "
            "then regenerate."
        )
    return None


def export_sky_east_nukuryou(
    df_items: pd.DataFrame,
    cn_lookup: dict,
    output_dir: str,
) -> list[str]:
    """Generate 核料 (material-allocation) workbooks — one per distinct fabric.

    Each workbook:
      • one sheet per style that uses that fabric
      • Row 2 = size headers (B-G → XS-XXL)
      • Row 3+ = one row per color (col A = color name, B-G = XS-XXL quantities)

    Returns list of saved file paths (empty if Template_P not found or no fabric codes).
    """
    if not _SE_TEMPLATE_P.exists():
        return []

    fabric_col = "fabric_item_no"
    if fabric_col not in df_items.columns:
        return []

    output_paths: list[str] = []

    for fabric_no, fabric_df in df_items.groupby(fabric_col, sort=False):
        fabric_no = str(fabric_no or "").strip()
        if not fabric_no:
            continue

        tpl_wb = load_workbook(str(_SE_TEMPLATE_P))
        tpl_ws = tpl_wb.worksheets[0]

        # ── Detect layout from the nukuryou template ──────────────────────
        color_col, size_col_map, nuk_data_row = _detect_nukuryou_layout(tpl_ws)
        # Apply user-configured overrides (Sky_East_P_config.json)
        try:
            from . import template_config as _tc
            _nuk_cfg = _tc.load_config("sky_east_nukuryou")
            for sz, raw in (_nuk_cfg.get("size_column_map") or {}).items():
                k = str(sz).strip().lower()
                k = "xxl" if k in ("2xl", "xxl") else k
                if k in {"xs", "s", "m", "l", "xl", "xxl"}:
                    try:
                        size_col_map[k] = _tc.column_letter_to_int(raw)
                    except Exception:
                        pass
            cm = _nuk_cfg.get("column_map") or {}
            for k_raw, raw in cm.items():
                if str(k_raw).strip().lower() in {"color", "color name", "colordesc", "颜色"}:
                    try:
                        color_col = _tc.column_letter_to_int(raw)
                    except Exception:
                        pass
            if _nuk_cfg.get("data_start_row"):
                try:
                    nuk_data_row = int(_nuk_cfg["data_start_row"])
                except (TypeError, ValueError):
                    pass
        except Exception:
            pass
        nuk_header_row = nuk_data_row - 1   # row where size headers are written

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _replace_placeholders(tpl_ws, {"created_at": created_at, "fabric": fabric_no})

        for style, style_df in fabric_df.groupby("style", sort=False):
            style = str(style or "").strip()
            if not style:
                continue

            ws = tpl_wb.copy_worksheet(tpl_ws)
            ws.title = _clean_sheet_name(style)

            # Clear data area (keep template header rows intact)
            _clear_data_area(ws, nuk_data_row)

            # Write size headers at the detected header row
            for sz_key, sz_col in size_col_map.items():
                ws.cell(nuk_header_row, sz_col).value = sz_key.upper().replace("XXL", "2XL")

            # Aggregate sizes by color
            color_totals: dict[str, dict[str, int]] = {}
            for _, item in style_df.iterrows():
                color_en = str(item.get("color_name", "") or "")
                brand    = str(item.get("brand",       "") or "")
                color_cn = _cn_color(cn_lookup, brand, color_en)
                display  = f"{color_en}({color_cn})" if color_cn else color_en

                if display not in color_totals:
                    color_totals[display] = {sz: 0 for sz in _SIZES_LC}
                for sz in _SIZES_LC:
                    color_totals[display][sz] += int(item.get(sz, 0) or 0)

            # Write color rows starting at the detected data row
            out_row = nuk_data_row
            for color_display, sizes in color_totals.items():
                ws.cell(out_row, color_col).value = color_display
                for sz_key, sz_col in size_col_map.items():
                    ws.cell(out_row, sz_col).value = sizes.get(sz_key, 0)
                out_row += 1

        # Remove master template sheet
        if tpl_ws in tpl_wb.worksheets:
            tpl_wb.remove(tpl_ws)

        if not tpl_wb.sheetnames:
            tpl_wb.create_sheet("Empty")

        safe = re.sub(r'[<>:"/\\|?*\s]+', "_", fabric_no).strip("_") or "unknown"
        save_path = versioned_path(output_dir, f"Sky_East_核料_{safe}", ".xlsx")
        tpl_wb.save(str(save_path))
        output_paths.append(str(save_path))

    return output_paths


# ---------------------------------------------------------------------------
# Cross-comparison (mirrors VBA CreateCrossComparisonSheet)
# ---------------------------------------------------------------------------

def build_cross_comparison(
    style_totals_buyplan: dict[str, int],
    df_items: pd.DataFrame,
) -> pd.DataFrame:
    """Compare style totals between buy plan and 核料 data.

    Parameters
    ----------
    style_totals_buyplan : {style: total_units} from export_sky_east_buyplan
    df_items             : raw items DataFrame (used to recompute 核料 totals)

    Returns
    -------
    DataFrame with columns:
        Style | Total (Buy Plan) | Total (核料) | Match
    """
    # Compute 核料 totals directly from df_items
    nukuryou_totals: dict[str, int] = {}
    for style, grp in df_items.groupby("style", sort=False):
        total = sum(
            int(grp[sz].sum()) for sz in _SIZES_LC if sz in grp.columns
        )
        nukuryou_totals[str(style)] = total

    all_styles = sorted(
        set(style_totals_buyplan) | set(nukuryou_totals)
    )
    rows = []
    for style in all_styles:
        bp  = style_totals_buyplan.get(style, 0)
        nk  = nukuryou_totals.get(style, 0)
        rows.append({
            "Style":            style,
            "Total (Buy Plan)": bp,
            "Total (核料)":     nk,
            "Match":            "✅ OK" if bp == nk else "❌ Mismatch",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Public template-management API for Admin UI
# ---------------------------------------------------------------------------

# Configuration file that holds Sky East column-header overrides.
SE_CONFIG_PATH = _TEMPLATES_DIR / "Sky_East_config.json"

# Catalog of Sky East templates managed by the Admin UI.
# Each entry: kind → (path, human-friendly label, description)
SE_TEMPLATE_CATALOG = {
    "main": (
        _SE_TEMPLATE,
        "Main buy plan (Template)",
        "Per-style sheet workbook with fabric header rows, size totals, and Index sheet.",
    ),
    "nukuryou": (
        _SE_TEMPLATE_P,
        "核料 workbooks (Template_P)",
        "One workbook per fabric — Color × Size pivot per style.",
    ),
}


def list_sky_east_templates() -> list[dict]:
    """Return metadata for each managed Sky East template (and the config file)."""
    result: list[dict] = []
    for kind, (path, label, desc) in SE_TEMPLATE_CATALOG.items():
        exists = path.exists()
        result.append({
            "kind":        kind,
            "label":       label,
            "description": desc,
            "file":        path.name,
            "path":        str(path),
            "exists":      exists,
            "size_bytes":  path.stat().st_size if exists else 0,
            "modified":    (datetime.fromtimestamp(path.stat().st_mtime)
                            .strftime("%Y-%m-%d %H:%M:%S") if exists else ""),
        })
    return result


def read_sky_east_template(kind: str) -> bytes:
    """Return the raw bytes of the named Sky East template ('main' or 'nukuryou')."""
    if kind not in SE_TEMPLATE_CATALOG:
        raise ValueError(f"Unknown Sky East template kind: {kind!r}")
    path = SE_TEMPLATE_CATALOG[kind][0]
    if not path.exists():
        raise FileNotFoundError(f"Sky East template not found: {path}")
    return path.read_bytes()


def replace_sky_east_template(kind: str, xlsx_bytes: bytes) -> Path:
    """Overwrite the named Sky East template file with *xlsx_bytes*. Returns its path."""
    if kind not in SE_TEMPLATE_CATALOG:
        raise ValueError(f"Unknown Sky East template kind: {kind!r}")
    if not xlsx_bytes or xlsx_bytes[:2] != b"PK":
        raise ValueError("Uploaded data does not look like a valid .xlsx file (missing PK header).")
    path = SE_TEMPLATE_CATALOG[kind][0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(xlsx_bytes)
    return path


def read_sky_east_config_text() -> str:
    """Return the Sky_East_config.json contents as text (or empty string if absent)."""
    if not SE_CONFIG_PATH.exists():
        return ""
    return SE_CONFIG_PATH.read_text(encoding="utf-8")


def write_sky_east_config_text(text: str) -> Path:
    """Write *text* to Sky_East_config.json after verifying it parses as JSON."""
    import json as _json
    # Empty text → delete the config (revert to template defaults)
    if not text.strip():
        if SE_CONFIG_PATH.exists():
            SE_CONFIG_PATH.unlink()
        return SE_CONFIG_PATH
    # Validate JSON before writing so we never persist a broken config
    _json.loads(text)
    SE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SE_CONFIG_PATH.write_text(text, encoding="utf-8")
    return SE_CONFIG_PATH
