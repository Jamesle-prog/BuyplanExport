"""GIII extraction / processing pipeline functions (PDF + smart pipelines).

Excel-specific pipeline functions live in ui/giii/excel_extraction.py.
"""
from __future__ import annotations
import hashlib as _hl
import io
import os
import tempfile
import zipfile
import streamlit as st
import pandas as pd
from po_extractor.detectors import group_by_company
from po_extractor.exporters import (
    export_buyplan, export_color_plan, export_cross_check,
    export_csvs, export_po_summary,
)
from po_extractor.parsers import parse_pdf, parse_pdf_ai


# Friendly names for the detector's format ids, shown in the processing status.
_FORMAT_LABELS = {
    "infor_nexus":   "Infor Nexus PDF",
    "legacy_giii":   "Legacy G-III PDF",
    "vendor_fax":    "Vendor Fax",
    "tk_eu":         "TK EU Fax",
    "kl":            "KL Fax",
    "excel_zalando": "Zalando Excel",
    "sky_east":      "Sky East Excel",
    "unknown":       "Unknown format",
}


def _fmt_breakdown(items) -> str:
    """'Infor Nexus PDF ×17 · Vendor Fax ×2' — a per-format count for a group,
    so the processing status shows WHICH formats are being handled."""
    from collections import Counter
    counts = Counter((getattr(d, "format_id", "") or "unknown") for d in items)
    return " · ".join(f"{_FORMAT_LABELS.get(fmt, fmt)} ×{n}"
                      for fmt, n in counts.most_common())


def _regex_low_confidence(po) -> bool:
    """True when the fast regex parse didn't come back clean, so Auto mode
    should retry with AI. Mirrors the parsers' own 'valid' criterion."""
    m = po.metadata
    return (not po.size_rows) \
        or (getattr(m, "validation_status", "") != "valid") \
        or ((getattr(m, "parse_confidence", 0) or 0) < 70)


def _parse_pdf_by_method(path: str, method: str, api_key: str, model: str):
    """Return (POData, used_ai). ``method``:
    * ``regex``    — built-in parser only.
    * ``deepseek`` — AI for every file (regex fallback on API error).
    * ``auto``     — regex first; AI only when the regex parse is
                     low-confidence, unparsed, or raises (needs a key)."""
    if method == "deepseek" and api_key:
        return parse_pdf_ai(path, api_key=api_key, model=model), True
    if method == "auto":
        try:
            po = parse_pdf(path)
        except Exception:
            if api_key:
                return parse_pdf_ai(path, api_key=api_key, model=model), True
            raise
        if api_key and _regex_low_confidence(po):
            return parse_pdf_ai(path, api_key=api_key, model=model), True
        return po, False
    return parse_pdf(path), False
from po_extractor.ui_helpers import (
    format_save_results as _format_save_results,
    se_items_to_buyplan_dfs as _se_items_to_buyplan_dfs_impl,
)
from po_extractor.utils.price_mask import mask_prices_batch
from ui.i18n import t
from ui.session_keys import SK
from ui.shared import ProgressTracker, images_dir as _get_images_dir
from ui.stores import get_store
from ui.giii._shared import (
    _enrich_cn_color, _XLSX_MIME, _CSV_MIME, _ZIP_MIME,
    mask_ai_creds as _mask_ai_creds,
)

_ProgressTracker = ProgressTracker


def _run_extraction(uploaded_files, mask_prices: bool, company: str = ""):
    import shutil as _shutil
    tmpdir = tempfile.mkdtemp()
    out_dir = tempfile.mkdtemp()
    log = []

    n_files  = len(uploaded_files)
    # Steps: parse×n + save + csv + buyplan + color + summary + crosscheck [+ mask]
    n_steps  = n_files + 6 + (1 if mask_prices else 0)

    with st.status("Processing…", expanded=True) as status:
        tracker = _ProgressTracker(n_steps)

        # 1. Save uploads to disk
        pdf_paths = []
        for uf in uploaded_files:
            path = os.path.join(tmpdir, uf.name)
            with open(path, "wb") as f:
                f.write(uf.getbuffer())
            pdf_paths.append(path)

        # 2. Parse each PDF — deduplicate by file hash within this session
        seen_hashes: set[str] = set()
        pos = []
        for path in pdf_paths:
            name = os.path.basename(path)
            with open(path, "rb") as fh:
                file_hash = _hl.md5(fh.read()).hexdigest()
            if file_hash in seen_hashes:
                st.write(f"⚠️ {name} — identical file already in this batch, skipped")
                log.append(f'<span style="color:#b08800">⚠️ {name}</span> — duplicate file skipped')
                tracker.step(f"Skipped duplicate: {name}")
                continue
            seen_hashes.add(file_hash)
            tracker.step(f"Parsing {name}")
            try:
                po = parse_pdf(path)
                if company:
                    po.metadata.company = company
                po.metadata.processed_by = st.session_state.get(SK.USERNAME, "")
                po.metadata.source_file_hash = file_hash
                pos.append(po)
                n = len(po.size_rows)
                st.write(f"✅ {name} — {n} size row(s)")
                log.append(f'<span class="badge-ok">✅ {name}</span> — {n} size row(s)')
            except Exception as e:
                st.write(f"❌ {name}: {e}")
                log.append(f'<span class="badge-err">❌ {name}</span>: {e}')
                get_store().save_exception(
                    po_number="", file_name=name, company=company,
                    reason=str(e),
                    processed_by=st.session_state.get(SK.USERNAME, ""),
                )

        if not pos:
            status.update(label="No valid POs could be parsed.", state="error")
            st.session_state.parse_log = log
            return

        # 3. Save to persistent store with conflict detection
        tracker.step("Saving to history")
        st.write("Checking for duplicates / updates…")
        save_results = get_store().save_many_checked(pos)
        _log_save_results(save_results, log)

        # 4. Export CSVs + all Excel outputs
        tracker.step("Generating CSV exports")
        st.write("Generating CSV exports…")
        result = export_csvs(pos, out_dir)
        # Enrich size rows with Chinese color names and overwrite the by-size CSV
        result["df_size"] = _enrich_cn_color(result["df_size"], result["df_meta"])
        result["df_size"].to_csv(result["by_size_color"], index=False, encoding="utf-8-sig")

        tracker.step("Generating buy plan")
        st.write("Generating buy plan Excel…")
        buyplan_path = export_buyplan(result["df_size"], result["df_meta"], out_dir,
                                       images_dir=_get_images_dir("giii_images_dir"))

        tracker.step("Generating color plan")
        st.write("Generating color plan Excel…")
        color_plan_path = export_color_plan(result["df_size"], out_dir)

        tracker.step("Generating PO summary")
        st.write("Generating PO summary Excel…")
        po_summary_path = export_po_summary(result["df_size"], result["df_meta"], out_dir)

        tracker.step("Generating cross-check")
        st.write("Generating cross-check Excel…")
        cross_check_path = export_cross_check(
            result["df_size"], buyplan_path, color_plan_path, po_summary_path, out_dir,
        )

        # 5. Mask prices
        masked_paths = []
        if mask_prices:
            tracker.step(f"Masking prices in {len(pdf_paths)} PDF(s)")
            st.write(f"Masking prices in {len(pdf_paths)} PDF(s)…")
            _mask_errors: list[str] = []
            _ai_key, _ai_model = _mask_ai_creds()
            masked_paths = mask_prices_batch(pdf_paths, out_dir,
                                             errors=_mask_errors,
                                             api_key=_ai_key, model=_ai_model)
            for _me in _mask_errors:
                st.warning(f"Price-mask failed — {_me} (file NOT in masked output)")

        tracker.done()
        status.update(label="Done!", state="complete")

    # 5. Read outputs into memory for download buttons
    outputs = {}

    with open(buyplan_path, "rb") as f:
        outputs["buyplan_bytes"] = f.read()
    outputs["buyplan_name"] = os.path.basename(buyplan_path)

    with open(color_plan_path, "rb") as f:
        outputs["color_plan_bytes"] = f.read()
    outputs["color_plan_name"] = os.path.basename(color_plan_path)

    with open(po_summary_path, "rb") as f:
        outputs["po_summary_bytes"] = f.read()
    outputs["po_summary_name"] = os.path.basename(po_summary_path)

    with open(cross_check_path, "rb") as f:
        outputs["cross_check_bytes"] = f.read()
    outputs["cross_check_name"] = os.path.basename(cross_check_path)

    csv_buf = io.BytesIO()
    with zipfile.ZipFile(csv_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for key in ("by_size_color", "summary", "metadata"):
            p = result[key]
            zf.write(p, os.path.basename(p))
    outputs["csvs_zip"] = csv_buf.getvalue()

    if masked_paths:
        mask_buf = io.BytesIO()
        with zipfile.ZipFile(mask_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in masked_paths:
                zf.write(p, os.path.basename(p))
        outputs["masked_zip"] = mask_buf.getvalue()

    # PO requirements document (CPRS) — pulled automatically at upload time.
    _req = _build_requirements_doc(pos)
    if _req:
        outputs["requirements_bytes"], outputs["requirements_warns"] = _req

    st.session_state.results = outputs
    st.session_state.parse_log = log
    # All outputs are now in session_state — clean up temp dirs
    _shutil.rmtree(tmpdir,  ignore_errors=True)
    _shutil.rmtree(out_dir, ignore_errors=True)


def _build_requirements_doc(pos) -> tuple[bytes, list[str]] | None:
    """Resolve CPRS requirements for freshly-uploaded POs and build the
    requirements workbook. Returns (xlsx_bytes, warnings) or None when CPRS
    is unconfigured / nothing resolved. Never raises — a requirements-doc
    failure must not fail the upload."""
    try:
        from ui.stores import get_cprs_client
        cprs = get_cprs_client()
        if cprs is None:
            return None
        from po_extractor.ui_helpers.giii_requirements import resolve_po_requirements
        from po_extractor.exporters.giii_requirements_export import (
            export_giii_requirements,
        )
        contexts, warns = resolve_po_requirements(cprs, pos)
        if not contexts:
            # No document, but the WHY must still reach the results panel —
            # same discoverability rule as mask_failed (nothing rendered
            # inside st.status survives the next rerun).
            return (None, warns) if warns else None
        return export_giii_requirements(contexts, warns), warns
    except Exception as exc:
        from ui.i18n import t as _t
        st.warning(_t("Requirements document skipped") + f" — {exc}")
        return None


def _log_save_results(results: list[tuple], log: list) -> None:
    """Render save-status lines via Streamlit and append HTML entries to *log*."""
    formatted = _format_save_results(results)
    for line in formatted.lines:
        st.write(line.plain)
        log.append(line.html)
    # Persist exceptions for skipped POs
    if formatted.skipped_po_numbers:
        store = get_store()
        username = st.session_state.get(SK.USERNAME, "")
        for po_number in formatted.skipped_po_numbers:
            store.save_exception(
                po_number=po_number, file_name="", company="",
                reason="PO number missing — skipped by store",
                processed_by=username,
            )
    st.write(formatted.summary_plain)
    log.append(formatted.summary_html)


def _run_from_history(po_numbers: list[str], result_key: str = "history_results"):
    store = get_store()
    df_size = store.load_size_rows(po_numbers)
    # Use list_pos (includes all commercial fields) filtered to selected POs
    _all = store.list_pos()
    df_meta = _all[_all["po_number"].isin(po_numbers)].reset_index(drop=True) if not _all.empty else store.load_metadata(po_numbers)

    if df_size.empty:
        st.warning("No size data found for selected POs.")
        return

    df_size = _enrich_cn_color(df_size, df_meta)

    import shutil as _shutil2
    out_dir = tempfile.mkdtemp()
    _prod_bytes = None
    with st.status("Generating from history…", expanded=True) as status:
        # Legacy grid buy plan — cross-check totals source only.
        buyplan_path = export_buyplan(df_size, df_meta, out_dir,
                                       images_dir=_get_images_dir("giii_images_dir"))
        st.write("Building color plan…")
        color_plan_path = export_color_plan(df_size, out_dir)
        st.write("Building PO summary…")
        po_summary_path = export_po_summary(df_size, df_meta, out_dir)
        st.write("Building cross-check…")
        cross_check_path = export_cross_check(
            df_size, buyplan_path, color_plan_path, po_summary_path, out_dir,
        )
        # Buy Plan download = 生产计划单 (same shared builder as the upload flow
        # and Reports → Create Buy Plan).
        st.write("Building buy plan (生产计划单)…")
        from ui.giii._buyplan import build_giii_production_plan
        from ui.stores import get_cprs_client as _get_cprs_client
        try:
            _prod_bytes, _prod_warns, _ = build_giii_production_plan(
                po_numbers, store, cprs=_get_cprs_client())
        except Exception as _bp_exc:
            _prod_bytes = None
            st.warning(f"生产计划单 build failed — falling back to grid: {_bp_exc}")
        status.update(label="Done!", state="complete")

    outputs = {}
    for key, path in [
        ("color_plan", color_plan_path),
        ("po_summary", po_summary_path), ("cross_check", cross_check_path),
    ]:
        with open(path, "rb") as f:
            outputs[f"{key}_bytes"] = f.read()
        outputs[f"{key}_name"] = os.path.basename(path)
    if _prod_bytes:
        outputs["buyplan_bytes"] = _prod_bytes
        outputs["buyplan_name"] = "GIII_Production_Plan.xlsx"
    else:
        with open(buyplan_path, "rb") as f:
            outputs["buyplan_bytes"] = f.read()
        outputs["buyplan_name"] = os.path.basename(buyplan_path)

    # Build a style+color summary (total units per PO/Style/Color)
    df_summary = (
        df_size.groupby(["PO Number", "Style", "Color"], sort=False)["Units"]
        .sum()
        .reset_index()
        .rename(columns={"Units": "Total Units"})
    )

    csv_buf = io.BytesIO()
    with zipfile.ZipFile(csv_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("size_color_rows.csv",
                    df_size.to_csv(index=False, encoding="utf-8-sig"))
        zf.writestr("style_color_summary.csv",
                    df_summary.to_csv(index=False, encoding="utf-8-sig"))
        zf.writestr("metadata.csv",
                    df_meta.to_csv(index=False, encoding="utf-8-sig"))
    outputs["csvs_zip"] = csv_buf.getvalue()
    st.session_state[result_key] = outputs
    _shutil2.rmtree(out_dir, ignore_errors=True)


def _create_buyplan_bytes(po_numbers: list[str]) -> bytes:
    """Generate a buy plan xlsx for the given GIII PO numbers and return the raw bytes."""
    store = get_store()
    df_size = store.load_size_rows(po_numbers)
    df_meta = store.load_metadata(po_numbers)
    if df_size.empty:
        return b""
    import shutil as _shutil3
    df_size = _enrich_cn_color(df_size, df_meta)
    out_dir = tempfile.mkdtemp()
    try:
        path = export_buyplan(df_size, df_meta, out_dir,
                              images_dir=_get_images_dir("giii_images_dir"))
        with open(path, "rb") as f:
            return f.read()
    finally:
        _shutil3.rmtree(out_dir, ignore_errors=True)


def _se_items_to_buyplan_dfs(df_items: pd.DataFrame) -> tuple:
    return _se_items_to_buyplan_dfs_impl(df_items)


def _save_fabric_parts_from_df(df, source: str) -> int:
    """
    Extract FabricPart data from a Zalando-style DataFrame and persist it to
    the universal style_fabric_parts table in the shared POStore.

    Reads up to 4 fabric slots per style using the internal column names:
        fabricN_code       → hhn_no
        fabricN_body_part  → body_part
        fabricN            → composition
    where N = 1..4.

    One record per *unique style* is saved (fabric doesn't vary by color/PO).
    Returns total rows upserted.
    """
    from po_extractor.parsers.client_excel import extract_fabric_parts_from_row

    if df is None or df.empty:
        return 0

    style_col = "Main Supplier Config SKU"
    if style_col not in df.columns:
        return 0

    # Build {style: [FabricPart, ...]} — first row wins per style
    style_parts: dict = {}
    for _, row in df.iterrows():
        style = str(row.get(style_col) or "").strip()
        if not style or style in style_parts:
            continue
        parts = extract_fabric_parts_from_row(row.to_dict())
        if parts:
            style_parts[style] = parts

    if not style_parts:
        return 0

    return get_store().save_fabric_parts_batch(source, style_parts)


def _validate_giii_pos(pos: list, log: list[str], company: str = "") -> None:
    """Log warnings for common data quality issues found in freshly-parsed GIII POs.

    Checks
    ------
    1. Negative / zero units in size_rows
    2. Missing style or color in size_rows
    3. Missing PO number in metadata
    """
    n_neg     = 0
    n_missing = 0
    n_no_po   = 0

    prefix = f"[{company}] " if company else ""

    for po in pos:
        po_no = (po.metadata.po_number or "").strip()
        if not po_no:
            n_no_po += 1
            log.append(f"⚠️ {prefix}A PO has no PO number in metadata")

        for row in po.size_rows:
            # Missing style / color
            if not (getattr(row, "style", None) or "").strip():
                n_missing += 1
                log.append(
                    f"⚠️ {prefix}PO {po_no}: row missing style "
                    f"(size={row.size}, units={row.units})"
                )
            if not (getattr(row, "color", None) or "").strip():
                n_missing += 1
                log.append(
                    f"⚠️ {prefix}PO {po_no}: row missing color "
                    f"(style={row.style}, size={row.size})"
                )

            # Negative quantities
            units = getattr(row, "units", 0) or 0
            if units < 0:
                n_neg += 1
                log.append(
                    f"⚠️ {prefix}PO {po_no}: {row.style}/{row.color} "
                    f"size {row.size} — negative units ({units})"
                )

    total_issues = n_neg + n_missing + n_no_po
    if total_issues == 0:
        log.append(f"✅ {prefix}Import validation passed — no data quality issues found")
    else:
        parts = []
        if n_no_po:   parts.append(f"{n_no_po} PO(s) missing PO number")
        if n_missing: parts.append(f"{n_missing} row(s) missing style/color")
        if n_neg:     parts.append(f"{n_neg} row(s) with negative units")
        log.append(f"⚠️ {prefix}Import validation: " + " · ".join(parts))


def _process_pdf_group(company: str, paths: list[str], out_dir: str,
                       mask_prices: bool, log: list,
                       method: str = "regex",
                       deepseek_api_key: str = "",
                       deepseek_model: str = "deepseek-chat") -> dict | None:
    # De-dup by content hash first (preserving order), so identical files
    # aren't parsed — or AI-billed — twice.
    seen: set[str] = set()
    todo: list[tuple[str, str, str]] = []   # (path, name, hash)
    for path in paths:
        name = os.path.basename(path)
        with open(path, "rb") as fh:
            h = _hl.md5(fh.read()).hexdigest()
        if h in seen:
            log.append(f"♻️ {name} — duplicate skipped")
            continue
        seen.add(h)
        todo.append((path, name, h))

    username = st.session_state.get(SK.USERNAME, "")

    def _parse_one(item):
        path, name, h = item
        try:
            po, used_ai = _parse_pdf_by_method(
                path, method, deepseek_api_key, deepseek_model)
            return (name, h, po, "🤖" if used_ai else "✅", None)
        except Exception as exc:
            return (name, h, None, None, exc)

    # ── Live progress (count · current file · elapsed · ETA) ──────────────────
    import time as _time
    total = len(todo)
    _prog = st.progress(0.0) if total else None
    _ptext = st.empty()
    _t0 = _time.perf_counter()

    def _fmt_dur(sec: float) -> str:
        sec = max(0.0, sec)
        if sec < 10:
            return f"{sec:.1f}s"          # sub-second work reads as "0.2s", not "0:00"
        if sec < 60:
            return f"{int(sec)}s"
        return f"{int(sec) // 60}:{int(sec) % 60:02d}"

    def _tick(done: int, last_name: str):
        if not total:
            return
        el = _time.perf_counter() - _t0
        eta = (el / done) * (total - done) if done else 0.0
        if _prog:
            _prog.progress(done / total)
        _ptext.markdown(
            f"⏳ **{done}/{total}** {t('files')} — `{last_name}`  ·  "
            f"{t('elapsed')} {_fmt_dur(el)}  ·  {t('ETA')} {_fmt_dur(eta)}")

    # AI parsing is a slow (~30-60s) network call per file — run the batch
    # concurrently so N files take ~one call's time, not N×. Both deepseek and
    # auto (whose slow AI fallback fires per low-confidence file) benefit.
    # as_completed lets us update progress as each file finishes; results are
    # re-sorted to input order afterwards. Store writes + logging stay on the
    # main thread (below).
    parsed_by_name: dict[str, tuple] = {}
    if method in ("deepseek", "auto") and deepseek_api_key and total > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(6, total)) as _ex:
            _futs = {_ex.submit(_parse_one, item): item for item in todo}
            done = 0
            for _fut in as_completed(_futs):
                res = _fut.result()
                parsed_by_name[res[0]] = res
                done += 1
                _tick(done, res[0])
        parsed = [parsed_by_name[name] for _, name, _ in todo]
    else:
        parsed = []
        for done, item in enumerate(todo, start=1):
            res = _parse_one(item)
            parsed.append(res)
            _tick(done, res[0])

    _breakdown = ""
    if total:
        _ai_n = sum(1 for r in parsed if r[3] == "🤖")
        _rx_n = sum(1 for r in parsed if r[3] == "✅")
        _mix = []
        if _rx_n:
            _mix.append(f"{_rx_n} ✅ {t('by parser')}")
        if _ai_n:
            _mix.append(f"{_ai_n} 🤖 {t('by AI')}")
        _breakdown = f" ({' · '.join(_mix)})" if _mix else ""

    # Parsing is often the fast part (clean Infor Nexus files parse in <1s); the
    # slow tail is save → exports → price masking → CPRS requirements document.
    # Drive the SAME bar through those phases so it never sits full with a
    # spinning wheel looking stuck — and so a slow phase names itself.
    def _phase(frac: float, label: str) -> None:
        if _prog:
            _prog.progress(min(1.0, frac))
        _ptext.markdown(
            f"⚙ **{label}** ({int(min(1.0, frac) * 100)}%)  ·  "
            f"{t('elapsed')} {_fmt_dur(_time.perf_counter() - _t0)}")

    if _prog:
        _prog.progress(0.0)      # restart the bar for the build/export phase

    pos = []
    for name, h, po, tag, exc in parsed:
        if exc is not None:
            log.append(f'<span style="color:#dc3545">❌ {name}: {exc}</span>')
            get_store().save_exception(
                po_number="", file_name=name, company=company,
                reason=str(exc), processed_by=username,
            )
            continue
        po.metadata.company = company
        po.metadata.processed_by = username
        po.metadata.source_file_hash = h
        pos.append(po)
        log.append(f'<span style="color:#198754">{tag} {name}</span> — {len(po.size_rows)} rows')

    if not pos:
        return None

    # ── Validate imported POs before saving ───────────────────────────────────
    _phase(0.12, t("Saving records…"))
    _validate_giii_pos(pos, log, company)

    get_store().save_many_checked(pos)

    _phase(0.32, t("Building buy plan & summaries…"))
    result  = export_csvs(pos, out_dir)
    result["df_size"] = _enrich_cn_color(result["df_size"], result["df_meta"])
    result["df_size"].to_csv(result["by_size_color"], index=False, encoding="utf-8-sig")
    # Legacy grid buy plan — kept ONLY as the cross-check totals source; the
    # user-facing Buy Plan download is the 生产计划单 built below.
    bp      = export_buyplan(result["df_size"], result["df_meta"], out_dir,
                             images_dir=_get_images_dir("giii_images_dir"))
    cp      = export_color_plan(result["df_size"], out_dir)
    ps      = export_po_summary(result["df_size"], result["df_meta"], out_dir)
    cc      = export_cross_check(result["df_size"], bp, cp, ps, out_dir)

    # Buy Plan download = the enriched 生产计划单 — the SAME builder as
    # Reports → Create Buy Plan (one buy-plan code path).
    from ui.giii._buyplan import build_giii_production_plan
    from ui.stores import get_cprs_client as _get_cprs_client
    _bp_selected = [p.metadata.po_number for p in pos if p.metadata.po_number]
    try:
        _prod_bytes, _prod_warns, _ = build_giii_production_plan(
            _bp_selected, get_store(), cprs=_get_cprs_client())
    except Exception as _bp_exc:      # never let the buy plan fail the upload
        _prod_bytes = None
        log.append(f'<span style="color:#dc3545">⚠ 生产计划单 build failed: '
                   f'{_bp_exc}</span>')

    masked_paths = []
    if mask_prices:
        _phase(0.45, t("Masking prices…"))
        _mask_errors: list[str] = []
        _ai_key, _ai_model = _mask_ai_creds()

        def _mask_prog(done: int, tot: int) -> None:
            # masking occupies the 45–70% band of the overall bar
            frac = 0.45 + 0.25 * (done / tot if tot else 1)
            _phase(frac, f"{t('Masking prices…')} {done}/{tot}")

        masked_paths = mask_prices_batch(paths, out_dir, errors=_mask_errors,
                                         api_key=_ai_key, model=_ai_model,
                                         on_progress=_mask_prog)
        for _me in _mask_errors:
            st.warning(f"Price-mask failed — {_me} (file NOT in masked output)")

    out: dict = {}
    for key, path in [("color_plan", cp), ("po_summary", ps), ("cross_check", cc)]:
        with open(path, "rb") as f:
            out[f"{key}_bytes"] = f.read()
        out[f"{key}_name"] = os.path.basename(path)

    # Buy Plan = 生产计划单 bytes (fall back to the legacy grid only if the
    # production build failed, so the download is never empty).
    if _prod_bytes:
        out["buyplan_bytes"] = _prod_bytes
        out["buyplan_name"] = "GIII_Production_Plan.xlsx"
    else:
        with open(bp, "rb") as f:
            out["buyplan_bytes"] = f.read()
        out["buyplan_name"] = os.path.basename(bp)

    csv_buf = io.BytesIO()
    with zipfile.ZipFile(csv_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for k in ("by_size_color", "summary", "metadata"):
            zf.write(result[k], os.path.basename(result[k]))
    out["csvs_zip"] = csv_buf.getvalue()

    if masked_paths:
        mbuf = io.BytesIO()
        with zipfile.ZipFile(mbuf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in masked_paths:
                zf.write(p, os.path.basename(p))
        out["masked_zip"] = mbuf.getvalue()
    elif mask_prices:
        # Masking was requested but produced nothing — persist that fact so
        # the results panel can say WHY there is no masked download, instead
        # of the button silently not appearing (the per-file warnings above
        # scroll away with the processing status).
        out["mask_failed"] = _mask_errors or ["no files could be masked"]

    # PO requirements document (CPRS) — pulled automatically at upload time.
    # Often the slowest phase (a CPRS call per order context plus artwork
    # fetches), so it gets its own visible step.
    _phase(0.8, t("Resolving requirements (CPRS)…"))
    _req = _build_requirements_doc(pos)
    if _req:
        out["requirements_bytes"], out["requirements_warns"] = _req

    if total:
        if _prog:
            _prog.progress(1.0)
        _ptext.markdown(
            f"✅ {total} {t('files')}{_breakdown} — {t('done in')} "
            f"{_fmt_dur(_time.perf_counter() - _t0)}")

    out["pipeline"] = "pdf"
    return out


def _run_smart_processing(detections, saved_paths: dict[str, str],
                          mask_prices: bool,
                          method: str = "regex",
                          deepseek_api_key: str = "",
                          deepseek_model: str = "deepseek-chat"):
    from ui.shared import (
        load_photo_map_from_dir as _load_photo_map_from_dir,
        images_dir as _get_images_dir,
    )
    out_dir = tempfile.mkdtemp()
    log: list[str] = []

    # Load photos from the configured image folder
    photo_map: dict[str, bytes] = _load_photo_map_from_dir(
        _get_images_dir("giii_images_dir")
    )
    if photo_map:
        log.append(f"📷 {len(photo_map)} photo(s) loaded from image folder")

    # Group detections by company
    grouped = group_by_company(detections)

    outputs: dict = {}
    outputs["groups"] = {}   # company → per-group result dict

    with st.status("Processing files…", expanded=True) as status:

        # ── Summary ──────────────────────────────────────────────────────────
        summary_lines = []
        for co, items in grouped.items():
            summary_lines.append(
                f"**{co}**: {len(items)} file(s) — {_fmt_breakdown(items)}")
        st.write("Detected groups: " + " | ".join(summary_lines))

        # ── Process each company group ────────────────────────────────────────
        for company, d_list in grouped.items():
            st.write(f"\n--- Processing **{company}** "
                     f"({len(d_list)} file(s) — {_fmt_breakdown(d_list)}) ---")
            paths = [saved_paths[d.filename] for d in d_list if d.filename in saved_paths]
            fmt_ids = {d.format_id for d in d_list}

            # Determine pipeline type
            is_excel = any(d.file_type == "excel" for d in d_list)
            is_pdf   = any(d.file_type == "pdf"   for d in d_list)

            if is_excel and company != "Unknown":
                from ui.giii.excel_extraction import _process_excel_group
                grp_out = _process_excel_group(
                    company, paths, out_dir, photo_map, log,
                    mask_prices=mask_prices,
                )
            elif is_pdf and company != "Unknown":
                grp_out = _process_pdf_group(
                    company, paths, out_dir, mask_prices, log,
                    method=method, deepseek_api_key=deepseek_api_key,
                    deepseek_model=deepseek_model,
                )
            else:
                st.write(f"  ⚠️ {company} — no supported pipeline (format: {fmt_ids})")
                log.append(f"⚠️ {company}: skipped (unsupported format {fmt_ids})")
                continue

            if grp_out:
                outputs["groups"][company] = grp_out
                st.write(f"  ✅ {company} complete.")

        if not outputs["groups"]:
            status.update(label="No files could be processed.", state="error")
        else:
            status.update(label="Done!", state="complete")

    st.session_state.smart_results = outputs
    st.session_state.smart_log = log


