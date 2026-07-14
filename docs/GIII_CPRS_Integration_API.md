# GIII ⇄ CPRS Integration — API Design

**Status:** live on CPRS `/evaluate/po` (one-call decode + evaluate) as of
v2.72.x · buy-plan validation (`/production-submission/upload`) still staged
**Prereq reading:** `docs/GIII_BuyPlan_Field_Mapping.md` (field sources)

## Design principle — CPRS is the single source of truth (non-negotiable)

> **Never build a local gate on CPRS. Always render CPRS results directly.**

The app is a *renderer*, not a rules engine. Whatever `/evaluate/po` returns —
the decoded order context and the requirement results — is written into the buy
plan / requirements document verbatim. The app maps a field to a column and
does nothing more.

Concretely, the following are **forbidden** in this repo's GIII code:

- **No applicability gates.** Do not suppress, blank, or override a CPRS value
  with an app-side condition — not "prepack-only", not "warehouse == X", not
  "channel == wholesale", not anything. If a value should not apply, CPRS says
  so with a `not_applicable` status; the app renders that (→ 无需). The app
  never *decides* applicability.
- **No local derivation of decoded fields.** brand→client, ship-to→warehouse,
  buyer→account, channel, and COO are decoded by `/evaluate/po`. The app does
  not re-derive, fuzzy-match, or second-guess them.
- **No local business rules.** Pack ratios, pcs-per-carton, carton weights, red
  stickers, MSRP/RFID defaults — all come from the CPRS result set or the
  decoded `warehouseInfo`. The app never hardcodes or infers them.

The only app-side logic permitted is **status-aware rendering** (map
`not_applicable / pending_input / conflict / confirmed` to a display string)
and **PO-sourced facts that are not CPRS values** — e.g. the 是否预包 Y/N column
reflects the PO's own packing text, and the printed MSRP price on the PO wins
over CPRS's Y/N "required" flag. A PO is a source of truth *about itself*; that
is never an override of a CPRS requirement.

**Why:** the knowledge base changes without a code deploy. Every local gate is a
second, stale copy of a rule that already lives in CPRS — it silently discards
correct CPRS answers and drifts out of sync. Two real bugs came from exactly
this: the red sticker forced to 无需 for non-prepack orders, and 每箱件数 blanked
for non-prepack orders — both were CPRS-confirmed values thrown away by an
app-side prepack gate. The fix each time was to **delete the gate**, not to add
another condition.

## The architecture (one call, one direction)

```
┌──────────────────────────────────────────────────────────────┐
│  UI (ui/giii/reports_tab.py)                                  │
│  · get_cprs_client()  — session-cached client (ui/stores.py)  │
│  · shows resolution PREVIEW + WARNINGS before download        │
└──────────────────────────┬───────────────────────────────────┘
             resolve_requirements(cprs, brand, rows, …)  (buy plan)
             resolve_po_requirements(cprs, pos)          (requirements doc)
┌──────────────────────────▼───────────────────────────────────┐
│  Service (po_extractor/ui_helpers/giii_requirements.py)       │
│  · ONE cprs.evaluate_po(rawPO) per distinct order context     │
│  · reads decoded {warehouse, account, channel, region,        │
│    rfid_default, msrp_required_default} + evaluation.results   │
│  · maps result → column, status-aware.  NO GATES.             │
│  · every fallback / blank becomes a warning string            │
└──────────────────────────┬───────────────────────────────────┘
                           │ POST /evaluate/po (cached per raw PO)
┌──────────────────────────▼───────────────────────────────────┐
│  Client (po_extractor/utils/cprs_client.py)                   │
│  · transport + caching + graceful None on failure             │
│  · evaluate_po(raw) -> {decoded, evaluation} | None           │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼   CPRS decodes AND evaluates the raw PO
```

`/evaluate/po` replaced the earlier multi-call resolve (client → account →
warehouse → per-domain evaluate) precisely so the **decode** also happens in
CPRS, not here. The exporters (`giii_production_plan.py`,
`giii_buyplan_export.py`) consume the resolved `RowRequirements` and never talk
to CPRS themselves.

## Contracts

**Service → exporter/UI:** `resolve_requirements(...) -> ({id(row): RowRequirements}, warnings)`
with `RowRequirements = {warehouse, region, channel, account, red_sticker,
carton_mark, prepack_ratio, pcs_box, carton_weight, msrp, rfid, red_img,
mark_img}`. `resolve_po_requirements(...) -> ([context, …], warnings)` builds
the full upload-time requirements document (every domain, plus artwork bytes).

**Diagnostics rule:** any silent blank is a bug. Undecoded brand, unmatched
buyer, unreachable CPRS — each yields a warning the UI renders above the
download button, next to a per-PO resolution preview the operator verifies
before sending to the factory.

**Caching:** the client instance is cached in `ui/stores.py` per
(base_url, api_key). `evaluate_po` is cached per raw PO; the service also dedups
by decoded order context `(warehouseCode, shipTo, account, dim_code, coo)` so
POs sharing a context evaluate once. A supplied `dim_code` is part of both keys,
so operator input never returns a stale no-context result.

## How CPRS results become cells (rendering only — no gating)

`_cell_value(result, dim_code)` is the whole ruleset the app applies, and it is
purely a status → string map:

| CPRS status      | rendered as                                        |
|------------------|----------------------------------------------------|
| `not_applicable` | 无需                                                |
| `pending_input`  | the operator's `dim_code`, else 待定:\<field\>       |
| `conflict`       | 冲突                                                |
| `confirmed`      | resultJson `code`/`value`/`standard`, else 见要求    |

Field → column mapping (all values from the CPRS result set / decoded warehouse):

- **红色箱贴纸 / 主箱唛** — `carton` results (`red_carton_sticker`,
  `carton_marking`/`warehouse_diamond`), status-aware. Shown for whatever CPRS
  confirms; the operator's DIM code satisfies a `pending_input` red sticker.
- **预包比例 / 每箱件数** — from the `packaging`/`hangtag`/`carton` results
  (`pre_pack_ratio` ratio; pcs mined from structured keys or "N pcs/carton"
  wording). Rendered for **every** order — no prepack gate. If the order isn't a
  prepack, CPRS simply returns no ratio (or `not_applicable`).
- **箱重限制** — explicit carton-weight bounds from `carton`/`packaging` results.
- **MSRP / RFID** — the decoded `warehouseInfo` defaults
  (`msrp_required_default`, `rfid_default`). The PO's printed MSRP price wins
  over the Y/N flag (a PO fact about itself, not a CPRS override).

Every value above is taken verbatim from `/evaluate/po`; the app adds no
prepack, warehouse, or channel condition on top of it.

## Staged next phases

1. ~~**Carton images in cells**~~ — **DONE (v2.38.0)**: `red_img`/`mark_img`
   bytes embed into the 红色箱贴纸/主箱唛 cells (openpyxl anchor, ≤76px,
   row height bumped); text value stays underneath; bad bytes are skipped,
   never fail the export.
2. ~~**Per-row DIM codes**~~ — **DONE (v2.38.0)**: `manual["dim_codes"]`
   (PO → code) with `manual["dim_code"]` as global fallback; the resolution
   context key includes the effective code. UI: editable PO→DIM table in the
   requirement-inputs expander.
3. ~~**Requirements panel**~~ — **DONE (v2.38.0)**: 🔍 *Check requirements
   only* resolves + shows the preview without generating a workbook (assembly
   and resolution are now separate steps from export).
4. **Buy-plan validation** — **BLOCKED: key scope.** The current CPRS key is
   limited to read/evaluate endpoints; `POST /production-submission/upload`
   requires role admin/editor (verified live: 403 with explicit scope
   message). Needs a higher-privilege key from the CPRS admin, then: upload
   generated xlsx → `/compare` → show diff summary post-export.
5. **CPRS data hygiene** — ongoing: `conflict` results (e.g. two tier-1
   `pre_pack_ratio` rules) can only render 冲突 here; the fix belongs in the
   knowledge base, not in an app-side tie-breaker (that would be a local gate).
