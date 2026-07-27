"""Sky East processing pipeline and missing-fields computation."""
from __future__ import annotations

import html
import io
import os
import tempfile
import zipfile

import streamlit as st

from auth.companies import COMPANY_SKY_EAST, SOURCE_SKY_EAST
from po_extractor.utils.price_mask import mask_prices_excel_batch
from ui.session_keys import SK
from ui.shared import ProgressTracker, save_images_to_disk, EXTRACTED_IMAGES_DIR
from ui.stores import get_store, get_sky_east_store, get_boat_sample_store
from ui.sky_east._shared import _parse_fabric_mapping_file, live_label
from ui.sky_east._validators import _se_report_sku_conflicts, _se_validate_contracts
from ui.sky_east._missing_compute import _compute_se_missing_df  # noqa: F401 (re-export)


# ---------------------------------------------------------------------------
# Sky East processing helpers
# ---------------------------------------------------------------------------

def _se_build_style_pid_map(contracts) -> dict[str, list[str]]:
    """Build {style -> [front_pid, back_pid]} map across all parsed contracts."""
    style_pid_map: dict[str, list[str]] = {}
    for c in contracts:
        for itm in (c.items or []):
            s   = (itm.style or "").strip()
            pid = (itm.picture_id or "").strip()
            if s and pid:
                lst = style_pid_map.setdefault(s, [])
                if pid not in lst and len(lst) < 2:
                    lst.append(pid)
    return style_pid_map


def _se_distinct_brands(contracts) -> list[str]:
    """Distinct, order-preserved brand names across all parsed contracts'
    items -- the same raw item.brand field _prefetch_boat_sample_cache reads
    at buy-plan generation time (never the progress-table override)."""
    seen: set[str] = set()
    brands: list[str] = []
    for c in contracts:
        for itm in (c.items or []):
            b = (itm.brand or "").strip()
            if b and b not in seen:
                seen.add(b)
                brands.append(b)
    return brands


def _enrich_fabric_parts_from_cache(style_parts_map: dict) -> None:
    """Fill missing composition/weight/width on FabricParts from the HHN cache (in-place)."""
    all_hhns = {p.hhn_no for parts in style_parts_map.values() for p in parts if p.hhn_no}
    if not all_hhns:
        return
    with get_store()._conn() as conn:
        ph = ",".join("?" * len(all_hhns))
        rows = conn.execute(
            f"SELECT hhn_no, composition, weight_gsm, width_cm FROM fabric_hhn_cache WHERE hhn_no IN ({ph})",
            list(all_hhns),
        ).fetchall()
    cache = {r["hhn_no"]: dict(r) for r in rows}
    for parts in style_parts_map.values():
        for p in parts:
            if p.hhn_no and p.hhn_no in cache:
                d = cache[p.hhn_no]
                if not p.composition:
                    p.composition = d.get("composition", "") or ""
                if not p.weight_gsm:
                    p.weight_gsm = d.get("weight_gsm", 0) or 0
                if not p.width_cm:
                    p.width_cm = d.get("width_cm", 0) or 0


def _se_init_lookups(ref_info: dict, tracker, log: list[str]):
    """Build Config-SKU / Fabric / Progress lookups from uploaded reference files."""
    config_sku_lookup = None
    fabric_lookup     = None
    progress_lookup   = None

    if "ean" in ref_info:
        tracker.step("Building Config SKU lookup")
        from po_extractor.lookups import ConfigSKULookup
        try:
            config_sku_lookup = ConfigSKULookup(ref_info["ean"])
            n = len(config_sku_lookup)
            st.write(f"  Config SKU lookup ready ({n} combination(s))")
            log.append(f"Config SKU lookup: {html.escape(str(n))} combinations loaded")
        except Exception as exc:
            st.write(f"  Config SKU lookup error: {exc}")
            log.append(f"Config SKU lookup error: {html.escape(str(exc))}")

    if "fabric" in ref_info:
        tracker.step("Building Fabric lookup")
        try:
            style_parts_map = _parse_fabric_mapping_file(ref_info["fabric"])
            if style_parts_map:
                n_saved = get_store().save_fabric_parts_batch(SOURCE_SKY_EAST, style_parts_map)
                _enrich_fabric_parts_from_cache(style_parts_map)
                fabric_lookup = style_parts_map
                st.session_state[SK.SE_FABRIC_LOOKUP] = fabric_lookup
                n_styles = len(style_parts_map)
                n_parts  = sum(len(v) for v in style_parts_map.values())
                st.write(f"  Fabric mapping ready ({n_styles} style(s), {n_parts} fabric code(s) saved)")
                log.append(f"Fabric mapping: {html.escape(str(n_styles))} styles, {html.escape(str(n_parts))} fabric codes saved to DB")
            else:
                st.write("  Fabric mapping file parsed -- no valid style rows found")
                log.append("Fabric mapping: no valid rows found")
        except Exception as exc:
            st.write(f"  Fabric mapping error: {exc}")
            log.append(f"Fabric mapping error: {html.escape(str(exc))}")

    if "progress" in ref_info:
        tracker.step("Building Progress lookup")
        from po_extractor.lookups import ProgressLookup
        try:
            progress_lookup = ProgressLookup(ref_info["progress"])
            st.session_state[SK.SE_PROGRESS_LKUP] = progress_lookup
            st.write(f"  Progress lookup ready ({len(progress_lookup)} records)")
            log.append(f"Progress lookup: {html.escape(str(len(progress_lookup)))} records")
        except Exception as exc:
            log.append(f"Progress lookup error: {html.escape(str(exc))}")
    else:
        # No file uploaded for this run — fall back to the saved
        # progress-records DB (uploaded once via Fabric Mapping → HHN
        # Contract Progress), so 大货进度表 doesn't need re-uploading here.
        from ui.sky_east._shared import get_progress_lookup
        progress_lookup = get_progress_lookup(SOURCE_SKY_EAST)
        if progress_lookup is not None:
            st.write(f"  Progress lookup: using {len(progress_lookup)} saved record(s)")
            log.append(
                f"Progress lookup: using {html.escape(str(len(progress_lookup)))} saved record(s) "
                "from the database (no file uploaded this run)"
            )

    return config_sku_lookup, fabric_lookup, progress_lookup


def _se_log_color_cleanups(contracts, log: list[str]) -> None:
    """Show one cleanup line per unique colour value before contract lookup."""
    from po_extractor.lookups.progress_lookup import clean_color_for_lookup

    seen: set[str] = set()
    cleanup_lines: list[str] = []
    for contract in contracts:
        for item in contract.items:
            raw = str(item.color_name or "")
            if not raw or raw in seen:
                continue
            seen.add(raw)
            cleaned, steps = clean_color_for_lookup(raw)
            if steps and cleaned != raw:
                cleanup_lines.append(
                    f"  '{raw}' -> '{cleaned}'  ({'; '.join(steps)})"
                )
    if cleanup_lines:
        st.write(f"Color cleanup ({len(cleanup_lines)} value(s)):")
        for line in cleanup_lines:
            st.write(line)
        log.append(f"Color cleanup ({html.escape(str(len(cleanup_lines)))} value(s)):")
        log.extend(cleanup_lines)


def _se_enrich_items(contracts, config_sku_lookup, fabric_lookup, progress_lookup,
                     log: list[str] | None = None) -> None:
    """Fill missing item fields from the three lookup tables (in-place)."""
    if not (config_sku_lookup or progress_lookup or fabric_lookup):
        return
    if progress_lookup and log is not None:
        _se_log_color_cleanups(contracts, log)
    for contract in contracts:
        for item in contract.items:
            if config_sku_lookup:
                found = config_sku_lookup.enrich_item(item)
                if found:
                    item.config_sku = found
            if progress_lookup:
                if not item.picture_id:
                    img_id = progress_lookup.get_image_id(
                        item.style, item.color_name, item.zalando_po,
                        pc_no=item.pc_no)
                    if img_id:
                        item.picture_id = img_id
                if not item.contract_no:
                    cno = progress_lookup.get_contract_no(
                        item.style, item.color_name, item.zalando_po,
                        pc_no=item.pc_no)
                    if cno:
                        item.contract_no = cno
            if fabric_lookup:
                if isinstance(fabric_lookup, dict):
                    fp_list = fabric_lookup.get(item.style or "")
                    if fp_list:
                        primary = fp_list[0]
                        if not item.fabric_item_no:
                            item.fabric_item_no = primary.hhn_no or ""
                        if not item.fabrication:
                            item.fabrication = primary.composition or ""
                        item.fabric_parts = fp_list
                else:
                    if not item.fabrication:
                        comp = fabric_lookup.get_composition(item.style)
                        if comp:
                            item.fabrication = comp
                    if not item.fabric_item_no:
                        parts = fabric_lookup.get_fabric_parts(item.style)
                        if parts:
                            item.fabric_item_no = parts[0][1]


def _se_mask_order_files(order_paths, log: list[str]) -> bytes | None:
    """Run Excel price masking on order files; return zip bytes or None."""
    if not order_paths:
        return None
    st.write("Masking prices in source files...")
    import shutil as _shutil2
    mask_out_dir = tempfile.mkdtemp()
    try:
        _mask_errors: list[str] = []
        from ui.giii._shared import mask_ai_creds as _mask_ai_creds
        _ai_key, _ai_model = _mask_ai_creds()
        masked_files = mask_prices_excel_batch(
            [p for _, p in order_paths], mask_out_dir, errors=_mask_errors,
            api_key=_ai_key, model=_ai_model,
        )
        for _me in _mask_errors:
            st.warning(f"Price-mask failed — {_me} (file NOT in masked zip)")
            log.append(f"⚠️ price-mask failed — {html.escape(str(_me))}")
        if not masked_files:
            return None
        mbuf = io.BytesIO()
        with zipfile.ZipFile(mbuf, "w", zipfile.ZIP_DEFLATED) as zf:
            for mp in masked_files:
                zf.write(mp, os.path.basename(mp))
        st.write(f"  {len(masked_files)} masked file(s) ready for download")
        log.append(f"{html.escape(str(len(masked_files)))} price-masked file(s) created")
        return mbuf.getvalue()
    finally:
        _shutil2.rmtree(mask_out_dir, ignore_errors=True)


def _se_patch_contract_numbers(store, contracts, progress_lookup, log: list[str]) -> None:
    """Patch HHN Contract No. on all stored items (even duplicates)."""
    if not progress_lookup:
        return
    patched = 0
    for contract in contracts:
        for item in contract.items:
            cno = progress_lookup.get_contract_no(
                item.style, item.color_name, item.zalando_po,
                pc_no=item.pc_no)
            if cno:
                # BUG-35 fix: was update_item_fields with empty fabric_item_no,
                # which wiped existing fabric_item_no values in the DB.
                ok = store.update_contract_no(
                    item.pc_no, item.style, item.color_name,
                    item.zalando_po,
                    cno,
                )
                if ok:
                    patched += 1
    if patched:
        st.write(f"  Patched HHN Contract No. for {patched} item(s)")
        log.append(f"HHN Contract No. patched for {html.escape(str(patched))} item(s)")


def _se_save_fabric_parts_universal(contracts, fabric_lookup, log: list[str]) -> None:
    """Persist fabric parts into the universal style_fabric_parts table."""
    sfp_store = get_store()
    style_parts_map: dict = {}
    for contract in contracts:
        for item in contract.items:
            if item.fabric_parts and item.style:
                if item.style not in style_parts_map:
                    style_parts_map[item.style] = item.fabric_parts
    if not style_parts_map:
        return
    enrich_arg = fabric_lookup if not isinstance(fabric_lookup, dict) else None
    n_fp = sfp_store.save_fabric_parts_batch(
        SOURCE_SKY_EAST, style_parts_map, enrich_from_lookup=enrich_arg,
    )
    st.write(f"  {n_fp} fabric part(s) saved to universal fabric table")
    log.append(f"{html.escape(str(n_fp))} fabric part(s) saved ({html.escape(str(SOURCE_SKY_EAST))})")


def _run_sky_east_processing(order_files, ean_file, progress_file,
                             mask_prices: bool = False):
    """Parse, validate, and save Sky East contracts; populate lookup caches.

    Fabric mapping is no longer accepted here — upload it independently via
    the 🧵 Fabric Mapping section in the Contract History tab.
    """
    from po_extractor.parsers import parse_sky_east_order as se_parse
    from po_extractor.utils.image_extractor import ImageCache

    import shutil as _shutil
    tmpdir = tempfile.mkdtemp()
    log: list[str] = []
    contracts = []
    image_cache = ImageCache()
    try:

        n_order  = len(order_files)
        n_refs   = sum(1 for f in [ean_file, progress_file] if f is not None)
        n_steps  = n_order + n_refs + n_refs + 3

        with st.status("Processing Sky East files...", expanded=True) as status:
            tracker = ProgressTracker(n_steps)

            order_paths = []
            for uf in order_files:
                p = os.path.join(tmpdir, os.path.basename(uf.name))
                with open(p, "wb") as f:
                    f.write(uf.getbuffer())
                order_paths.append((uf.name, p))

            for fname, path in order_paths:
                tracker.step(f"Parsing {fname}")
                st.write(f"Parsing {fname}...")
                try:
                    contract = se_parse(path,
                                        processed_by=st.session_state.get(SK.USERNAME, ""))
                    contracts.append(contract)
                    pc = contract.pc_no or "(no PC No.)"
                    n  = len(contract.items)
                    st.write(f"  {fname} -> PC {pc}, {n} item(s)")
                    log.append(
                        f'<span style="color:#198754">{html.escape(str(fname))}</span> '
                        f'-> PC <b>{html.escape(str(pc))}</b>, {html.escape(str(n))} item(s)'
                    )
                    added = image_cache.add_file(path)
                    if added:
                        st.write(f"  {added} image(s) extracted from {fname}")
                        log.append(f"{html.escape(str(added))} image(s) from {html.escape(str(fname))}")
                    if contract.skipped_zero_qty:
                        n_skip = len(contract.skipped_zero_qty)
                        st.write(f"  ⚠️ {n_skip} zero-unit row(s) ignored in {fname}")
                        for s in contract.skipped_zero_qty:
                            log.append(
                                f'<span style="color:#fd7e14">⚠️ Ignored (0 units)</span> '
                                f'{html.escape(str(fname))} row {html.escape(str(s["row"]))}: style <b>{html.escape(str(s["style"] or "—"))}</b>'
                                + (f", PO {html.escape(str(s['po']))}" if s["po"] else "")
                            )
                except Exception as exc:
                    st.write(f"  {fname}: {exc}")
                    log.append(f'<span style="color:#dc3545">{html.escape(str(fname))}</span>: {html.escape(str(exc))}')
                    # Persist to the shared exception queue (same destination
                    # GIII parse failures go to) so the failure survives the
                    # session instead of living only in this log panel.
                    try:
                        get_store().save_exception(
                            po_number="", file_name=fname,
                            company=COMPANY_SKY_EAST,
                            reason=f"Sky East parse failed: {exc}",
                            processed_by=st.session_state.get(SK.USERNAME, ""),
                        )
                    except Exception:
                        pass  # queueing must never mask the original error

            if not contracts:
                status.update(label="No valid contracts could be parsed.", state="error")
                st.session_state.se_log = log
                return

            ref_info: dict[str, str] = {}
            for label, uf, key in [
                ("Config SKU", ean_file,      "ean"),
                ("Progress",   progress_file, "progress"),
            ]:
                if uf is not None:
                    tracker.step(f"Loading {label} file")
                    rpath = os.path.join(tmpdir, os.path.basename(uf.name))
                    with open(rpath, "wb") as f:
                        f.write(uf.getbuffer())
                    ref_info[key] = rpath
                    added = image_cache.add_file(rpath)
                    st.write(f"  {label} reference loaded ({uf.name})"
                             + (f", {added} image(s)" if added else ""))
                    log.append(f"{html.escape(str(label))} file loaded: {html.escape(str(uf.name))}"
                               + (f" -- {html.escape(str(added))} image(s)" if added else ""))

            config_sku_lookup, fabric_lookup, progress_lookup = _se_init_lookups(
                ref_info, tracker, log
            )

            tracker.step("Enriching items")
            _se_enrich_items(contracts, config_sku_lookup, fabric_lookup, progress_lookup, log)

            _se_report_sku_conflicts(config_sku_lookup, log)

            tracker.step("Validating import data")
            st.write("Validating import data...")
            _se_validate_contracts(contracts, log)

            tracker.step("Saving to database")
            st.write("Saving to database...")
            store   = get_sky_east_store()
            results = store.save_many_contracts_checked(contracts)
            from ui.sky_east._missing_compute import _compute_se_missing_df
            from ui.sky_east.history import _se_buyplan_fabric_preflight
            _compute_se_missing_df.clear()
            _se_buyplan_fabric_preflight.clear()

            total_new  = sum(len(r["new_items"])       for r in results)
            total_upd  = sum(len(r["updated_items"])   for r in results)
            total_dup  = sum(len(r["duplicate_items"]) for r in results)
            total_pend = sum(len(r["pending_return_label"]) for r in results)
            st.write(
                f"  {total_new} new, {total_upd} updated, "
                f"{total_dup} duplicate(s) skipped"
                + (f", {total_pend} Return Label conflict(s) held for review" if total_pend else "")
            )
            log.append(
                f"Stored: {html.escape(str(total_new))} new, {html.escape(str(total_upd))} updated, "
                f"{html.escape(str(total_dup))} duplicates skipped"
                + (f", {html.escape(str(total_pend))} Return Label conflict(s) held for review" if total_pend else "")
            )

            if total_pend:
                # Dedupe by (pc_no, style, color, po) -- a newer parse of the
                # same item replaces an older still-unresolved pending entry
                # rather than piling up a duplicate review row for it.
                pending = {
                    (p["pc_no"], p["style"], p["color_name"], p["zalando_po"]): p
                    for p in st.session_state.get(SK.SE_RL_PENDING, [])
                }
                for r in results:
                    for p in r["pending_return_label"]:
                        pending[(p["pc_no"], p["style"], p["color_name"], p["zalando_po"])] = p
                st.session_state[SK.SE_RL_PENDING] = list(pending.values())

            # New brands (never seen in 船样要求/shipping-sample requirements
            # before) -- held for an upload-time prompt rather than silently
            # left blank until someone notices at buy-plan generation time.
            # Best-effort: the contracts are already saved by this point, so a
            # lookup failure must not crash the rest of the upload flow (same
            # principle as the image-save fallback above).
            try:
                _new_brands = _se_distinct_brands(contracts)
                if _new_brands:
                    _bsr_store = get_boat_sample_store()
                    _known = _bsr_store.list_known_brands(COMPANY_SKY_EAST)
                    _unseen = [b for b in _new_brands if b not in _known]
                    if _unseen:
                        _pending_brands = list(st.session_state.get(SK.SE_NEW_BRAND_PENDING, []))
                        for b in _unseen:
                            if b not in _pending_brands:
                                _pending_brands.append(b)
                        st.session_state[SK.SE_NEW_BRAND_PENDING] = _pending_brands
                        st.write(f"  {len(_unseen)} new brand(s) need a shipping sample requirement")
                        log.append(f"{html.escape(str(len(_unseen)))} new brand(s) need a shipping sample requirement")
            except Exception as _brand_exc:
                log.append(f"⚠️ New-brand shipping-sample check skipped: {html.escape(str(_brand_exc))}")

            _se_save_fabric_parts_universal(contracts, fabric_lookup, log)
            _se_patch_contract_numbers(store, contracts, progress_lookup, log)

            masked_zip_bytes = _se_mask_order_files(order_paths, log) if mask_prices else None

            tracker.done()
            status.update(label="Done!", state="complete")

        st.session_state.se_results    = results
        st.session_state.se_log        = log
        st.session_state.se_contracts  = contracts
        st.session_state.se_masked_zip = masked_zip_bytes
        st.session_state.se_image_cache = {
            img_id: image_cache.get(img_id)
            for img_id in image_cache.all_ids()
            if image_cache.get(img_id)
        }
        _style_pid_map = _se_build_style_pid_map(contracts)
        # Save to the user's configured image folder (existing behaviour) …
        save_images_to_disk(
            st.session_state.se_image_cache,
            _style_pid_map,
        )
        # … and ALWAYS to the persistent extracted-images fallback, so a later
        # buy-plan run can still find them after a restart or a changed folder.
        save_images_to_disk(
            st.session_state.se_image_cache,
            _style_pid_map,
            img_dir=EXTRACTED_IMAGES_DIR,
        )
        # Keep memory + the extracted-images folder bounded (best-effort).
        try:
            from ui.memory import prune_extracted_images, trim_image_cache
            prune_extracted_images()
            trim_image_cache()
        except Exception:
            pass
    except Exception as exc:
        # Per-file parse errors are handled inside the loop; this catches a
        # failure in the post-loop steps (validation, save, image write) so the
        # user sees a clean message instead of a raw Streamlit traceback. Clear
        # any half-built results so the UI never renders a partial batch.
        from ui.i18n import t
        log.append(f"❌ {html.escape(str(exc))}")
        # Mirror the success path's exact keys (se_log / se_results) so the
        # results view reads this failure state, not a stale prior batch.
        st.session_state.se_log = log
        st.session_state.se_results = None
        st.error(f"{t('Sky East processing failed:')} {exc}")
    finally:
        # Clean up temp directory — all data is now in memory / DB / disk images
        _shutil.rmtree(tmpdir, ignore_errors=True)
