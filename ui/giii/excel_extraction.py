"""GIII Excel-pipeline processing functions (Zalando / HHP client Excel files)."""
from __future__ import annotations

import io
import os
import tempfile
import zipfile

import streamlit as st

from po_extractor.exporters import export_hhp_buyplan, export_hhp_template_p
from po_extractor.parsers.client_excel_multi import combine_excel_files, repeat_order_summary
from po_extractor.utils.price_mask import mask_prices_excel_batch
from auth.companies import get_company
from ui.stores import get_store
from ui.giii.extraction import _save_fabric_parts_from_df


def _log_photo_matches(df, photo_map: dict, log: list) -> None:
    """Run the same photo lookup as the exporter and write the result both
    to the live Streamlit page and to the on-page activity ``log`` list.

    The diagnostic shows: total photos in folder, total styles in this run,
    how many got matched, and which styles missed (with a hint on the
    expected filename patterns).
    """
    if not photo_map:
        st.warning(
            "📷 No photos loaded — the configured image folder is empty or "
            "doesn't contain any .png/.jpg files."
        )
        log.append("📷 No photos loaded from image folder")
        return

    if "Main Supplier Config SKU" not in df.columns:
        return

    from po_extractor.exporters._photo_utils import resolve_photo_pair

    unique_styles = (
        df["Main Supplier Config SKU"].dropna().astype(str).str.strip().unique()
    )
    matched: list[tuple[str, bool, bool]] = []   # (style, has_front, has_back)
    for s in unique_styles:
        if not s:
            continue
        first_row = df[
            df["Main Supplier Config SKU"].astype(str).str.strip() == s
        ].iloc[0]
        f, b = resolve_photo_pair(s, first_row, photo_map)
        matched.append((s, f is not None, b is not None))

    n_total = len(matched)
    n_with  = sum(1 for _, f, _ in matched if f)
    misses  = [s for s, f, b in matched if not f and not b]

    summary = (
        f"📷 Image folder: {len(photo_map)} file(s) · "
        f"matched front photo for **{n_with}/{n_total}** style(s)"
    )
    if misses:
        st.warning(summary)
        st.caption(
            f"Styles with **no photo found**: " + ", ".join(misses[:10])
            + (f" … +{len(misses) - 10} more" if len(misses) > 10 else "") + ". "
            "Filename patterns accepted: `{style}_front.png` / `{style}_back.png` / "
            "`{style}-front.png` / `{style}_F.png` / `{style}_1.png` / `{style}.png` "
            "(case-insensitive, .png/.jpg/.jpeg). Slashes in style names are "
            "normalised to underscores."
        )
    else:
        st.success(summary)
    log.append(summary)
    if misses:
        log.append("⚠️ no photo: " + ", ".join(misses[:10]))


def _process_excel_group(company: str, paths: list[str], out_dir: str,
                         photo_map: dict, log: list,
                         mask_prices: bool = False) -> dict | None:
    co_info = get_company(company) or {}
    sheet_name = co_info.get("excel_sheet") or "1.1.PO_Client"

    result = combine_excel_files(paths, sheet_name=sheet_name)
    for skipped in result.skipped_files:
        log.append(f'<span style="color:#dc3545">❌ {skipped}</span>')
    for src in result.source_files:
        n = len(result.df[result.df["_source_file"] == src]) if "_source_file" in result.df.columns else "?"
        log.append(f'<span style="color:#198754">✅ {src}</span> — {n} rows')

    if result.df.empty:
        log.append(f"⚠️ {company}: no data found.")
        return None

    for conflict in result.conflicts:
        log.append(f'<span style="color:#b08800">⚠️ {conflict}</span>')

    repeats = repeat_order_summary(result)
    for line in repeats:
        log.append(f"↩ {line}")

    _save_fabric_parts_from_df(result.df, source=company.lower().replace(" ", "_"))

    # Photo-match diagnostic — visible to the user via the log on the page
    _log_photo_matches(result.df, photo_map, log)

    bp  = export_hhp_buyplan(result.df, out_dir, photo_map=photo_map)
    tps = export_hhp_template_p(result.df, out_dir)

    out: dict = {}
    with open(bp, "rb") as f:
        out["buyplan_bytes"] = f.read()
    out["buyplan_name"] = os.path.basename(bp)

    tp_buf = io.BytesIO()
    with zipfile.ZipFile(tp_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, fbytes in tps:
            zf.writestr(fname, fbytes)
    out["template_p_zip"]   = tp_buf.getvalue()
    out["template_p_count"] = len(tps)
    out["repeat_orders"]    = result.repeat_orders
    out["conflicts"]        = result.conflicts
    out["pipeline"]         = "excel"

    if mask_prices and paths:
        mask_out_dir = tempfile.mkdtemp()
        masked_files = mask_prices_excel_batch(paths, mask_out_dir)
        if masked_files:
            mbuf = io.BytesIO()
            with zipfile.ZipFile(mbuf, "w", zipfile.ZIP_DEFLATED) as zf:
                for mp in masked_files:
                    zf.write(mp, os.path.basename(mp))
            out["masked_zip"] = mbuf.getvalue()
            log.append(f"🔒 {len(masked_files)} price-masked file(s) created for {company}")

    return out


def _run_excel_extraction(uploaded_excels, sheet_name: str,
                          mask_prices: bool = False):
    from ui.shared import (
        load_photo_map_from_dir as _load_photo_map_from_dir,
        images_dir as _get_images_dir,
    )
    tmpdir  = tempfile.mkdtemp()
    out_dir = tempfile.mkdtemp()
    log: list[str] = []

    with st.status("Processing Excel files…", expanded=True) as status:

        # 1. Save uploads to disk
        excel_paths = []
        for uf in uploaded_excels:
            path = os.path.join(tmpdir, uf.name)
            with open(path, "wb") as f:
                f.write(uf.getbuffer())
            excel_paths.append(path)

        # 2. Load photos from configured image folder
        photo_map: dict[str, bytes] = _load_photo_map_from_dir(
            _get_images_dir("excel_images_dir")
        )
        if photo_map:
            st.write(f"  📷 {len(photo_map)} photo(s) loaded from image folder")
            log.append(f"📷 {len(photo_map)} photo(s) loaded from image folder")

        # 3. Combine all Excel files
        st.write(f"Merging {len(excel_paths)} Excel file(s)…")
        result = combine_excel_files(excel_paths, sheet_name=sheet_name)

        for skipped in result.skipped_files:
            st.write(f"  ❌ {skipped}")
            log.append(f'<span style="color:#dc3545">❌ {skipped}</span>')

        for src in result.source_files:
            n_rows = (len(result.df[result.df["_source_file"] == src])
                      if "_source_file" in result.df.columns else "?")
            st.write(f"  ✅ {src} — {n_rows} row(s)")
            log.append(f'<span style="color:#198754">✅ {src}</span> — {n_rows} rows')

        if result.df.empty:
            status.update(label="No data found in the uploaded files.", state="error")
            st.session_state.excel_log = log
            return

        # 4. Conflict warnings
        for conflict in result.conflicts:
            st.warning(conflict)
            log.append(f'<span style="color:#b08800">⚠️ {conflict}</span>')

        # 5. Repeat-order summary
        repeat_lines = repeat_order_summary(result)
        if repeat_lines:
            st.info(
                f"**{len(repeat_lines)} repeat order group(s) detected** — "
                "same style/color in multiple POs. Each PO row is kept separately."
            )
            for line in repeat_lines:
                st.caption(f"  ↩ {line}")
                log.append(f"↩ {line}")

        total_styles = (result.df["Main Supplier Config SKU"].nunique()
                        if "Main Supplier Config SKU" in result.df.columns else 0)
        total_rows = len(result.df)
        st.write(f"Combined: {total_rows} row(s), {total_styles} style(s)")

        # 6. Save fabric parts to universal table
        _save_fabric_parts_from_df(result.df, source="zalando")

        # 7. Generate buy plan
        st.write("Generating Zalando buy plan…")

        # Photo-match diagnostic — visible on the page
        _log_photo_matches(result.df, photo_map, log)

        buyplan_path = export_hhp_buyplan(result.df, out_dir, photo_map=photo_map)
        st.write(f"  → {os.path.basename(buyplan_path)}")

        # 8. Generate Template_P workbooks
        st.write("Generating Template_P (color plan) workbooks…")
        template_p_files = export_hhp_template_p(result.df, out_dir)
        st.write(f"  → {len(template_p_files)} workbook(s)")

        # 9. Mask prices (optional)
        masked_excel_zip = None
        if mask_prices and excel_paths:
            st.write("Masking prices in source files…")
            mask_out_dir = tempfile.mkdtemp()
            masked_files = mask_prices_excel_batch(excel_paths, mask_out_dir)
            if masked_files:
                mbuf = io.BytesIO()
                with zipfile.ZipFile(mbuf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for mp in masked_files:
                        zf.write(mp, os.path.basename(mp))
                masked_excel_zip = mbuf.getvalue()
                st.write(f"  🔒 {len(masked_files)} masked file(s) ready for download")
                log.append(f"🔒 {len(masked_files)} price-masked file(s) created")

        status.update(label="Done!", state="complete")

    # Pack outputs
    outputs: dict = {}

    with open(buyplan_path, "rb") as f:
        outputs["buyplan_bytes"] = f.read()
    outputs["buyplan_name"] = os.path.basename(buyplan_path)

    tp_buf = io.BytesIO()
    with zipfile.ZipFile(tp_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, fbytes in template_p_files:
            zf.writestr(fname, fbytes)
    outputs["template_p_zip"]   = tp_buf.getvalue()
    outputs["template_p_count"] = len(template_p_files)

    if masked_excel_zip:
        outputs["masked_zip"] = masked_excel_zip

    # Repeat-order report as CSV
    if result.repeat_orders:
        import csv as _csv
        rows = []
        for style, pos in result.repeat_orders.items():
            for po in pos:
                rows.append({"Style": style, "PO Number": po})
        rep_buf = io.StringIO()
        w = _csv.DictWriter(rep_buf, fieldnames=["Style", "PO Number"])
        w.writeheader()
        w.writerows(rows)
        outputs["repeat_csv"] = rep_buf.getvalue().encode()

    outputs["conflict_count"] = len(result.conflicts)
    outputs["repeat_count"]   = len(result.repeat_orders)

    st.session_state.excel_results = outputs
    st.session_state.excel_log = log
