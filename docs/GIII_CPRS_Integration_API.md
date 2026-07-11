# GIII ⇄ CPRS Integration — API Design

**Status:** layers 1–3 implemented (v2.37.0) · layers 4+ staged
**Prereq reading:** `docs/GIII_BuyPlan_Field_Mapping.md` (field sources)

## The architecture (three layers, one direction)

```
┌──────────────────────────────────────────────────────────────┐
│  UI (ui/giii/reports_tab.py)                                  │
│  · get_cprs_client()  — session-cached client (ui/stores.py)  │
│  · shows resolution PREVIEW + WARNINGS before download        │
└──────────────────────────┬───────────────────────────────────┘
                           │ resolve_requirements(cprs, brand, rows, …)
┌──────────────────────────▼───────────────────────────────────┐
│  Service (po_extractor/ui_helpers/giii_requirements.py)       │
│  · RowRequirements dataclass — the contract with the exporter │
│  · dedup by order context (warehouse|ship_to, buyer, prepack) │
│  · channel derived from account_type (not hardcoded)          │
│  · every fallback becomes a warning string                    │
└──────────────────────────┬───────────────────────────────────┘
                           │ typed calls, cached
┌──────────────────────────▼───────────────────────────────────┐
│  Client (po_extractor/utils/cprs_client.py)                   │
│  · transport + caching + graceful None/[] on failure          │
│  · knows REAL field names (account_code, rfid_default, …)     │
└──────────────────────────────────────────────────────────────┘
```

The exporter (`giii_buyplan_export.py`) consumes `requirements=` (the service's
output) and no longer talks to CPRS itself; `cprs=` remains as a convenience
that calls the service internally.

## Contracts

**Service → exporter/UI:** `resolve_requirements(...) -> (dict[id(row), RowRequirements], warnings)`
with `RowRequirements = {warehouse, channel, account, red_sticker, carton_mark,
prepack_ratio, pcs_box, msrp, rfid, red_img, mark_img}`.

**Diagnostics rule:** any silent blank is a bug. Unmatched buyer, unresolved
ship-to, missing prepack ratio, unconfigured CPRS — each yields a warning the
UI renders above the download button, next to a per-PO resolution preview
table the operator verifies before sending to the factory.

**Caching:** client instance is `functools.cache`d in `ui/stores.py` per
(base_url, api_key) → its internal caches survive Streamlit reruns. The
`evaluate` cache key includes nested `contextFields` (a supplied `dim_code`
must never return the stale no-context result).

## Business rules encoded (verified against live CPRS)

- Red sticker: **prepack-only** → 无需 otherwise; must show the pre-pack DIM
  code (operator input; also sent as `contextFields.dim_code`, which resolves
  the CPRS requirement pending→confirmed).
- Prepack ratio + PCs/box: per-account inside `pre_pack_ratio.structured_output
  .ratios` (evaluate reports conflict without account filtering) — read via
  `prepack_spec()`, prepack rows only; manual PCs/box overrides.
- MSRP/RFID: warehouse defaults (`rfid_default`, `msrp_required_default`).
- Status mapping: not_applicable→无需/blank · pending_input→待定:<field> ·
  conflict→冲突 · confirmed→value.

## Staged next phases

1. **Carton images in cells** — `red_img`/`mark_img` bytes are already fetched;
   embed into P/Q cells (openpyxl anchor, sized to row) for DISPIMG parity with
   the reference workbook.
2. **Per-row DIM codes** — today one DIM code applies to the whole generation;
   POs with different prepack codes need a small editable table (PO → code).
3. **Requirements panel** — resolve + preview CPRS requirements for selected
   POs *without* generating a workbook (same service call, read-only view).
4. **Buy-plan validation** — CPRS `POST /production-submission/upload` +
   `/compare` can diff a finished buy plan against the client's rules; natural
   post-export check.
5. **CPRS data hygiene** — surface `conflict` results (e.g. two tier-1
   `pre_pack_ratio` rules) to whoever curates the KB; the buy plan can only
   mark them 冲突.
