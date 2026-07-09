# GIII Buy Plan — Field Mapping Spec

**Status:** Draft for review · **Purpose:** de-risk the GIII buy-plan exporter build
by mapping every cell of the canonical GIII buy-plan format to its data source
before writing exporter code.

The reference document is the real GIII buy plan
(`DKNY Sportswear Hol26 BUY PLAN 26502-DS3012 P6KH8FXB.xlsx`). **GIII** is the
client/vendor; **DKNY** is one brand under it — this format applies to **all GIII
POs** regardless of brand. Sizes shown are XS–XL (5), but the layout carries
whatever sizes the order uses.

Three data sources feed the sheet:

1. **PO** — extracted PO record (`POMetadata` + `SizeRow`, from the InforNexus /
   KL / MSG-fax parsers).
2. **进度表** — the stored HHN 大货进度表 progress records
   (`load_progress_records`), matched to the PO by PO#/style.
3. **CPRS** — the Client PO Requirements System knowledge base, via its REST API
   (`http://<host>:3100/api/v1`, `x-api-key`). Drives the two carton-image
   columns and can drive packaging notes.

---

## 1. CPRS resolution chain (app-side logic = fuzzy match only)

Per PO row-group, the exporter resolves the CPRS `evaluate` inputs entirely from
CPRS reference data — no lookup table maintained in this app:

| Need | How | Endpoint |
|---|---|---|
| `clientId` (brand) | brand name (file/PO) → match | `GET /clients` |
| `warehouseCode` | PO ship-to address → resolve | `GET /warehouse-lookup/resolve?ship_to=&client_id=` |
| `accountCode` | buyer text (`MY MACY'S OMNI CHANNEL`) → fuzzy-match onto the brand's account catalog (`MACYS`) | `GET /clients/{id}/accounts` |
| `channel`, `coo`, `garmentCategory` | account type / PO COO / style category | (carried in the evaluate body) |

Then one call resolves the requirement set:

```
POST /evaluate
{ clientId, channel, warehouseCode, accountCode, coo, garmentCategory, contextFields }
→ results[] grouped by domain; we read domain == "carton"
```

**The only app-side logic** is the fuzzy match of buyer text onto the returned
account catalog; everything else is CPRS-sourced. Calls are cached per
`(clientId, warehouseCode, accountCode)` — a 7-row buy plan makes a handful of
calls, not one per row.

---

## 2. Header block (rows 1–6)

| Cell(s) | Label | Source | Notes |
|---|---|---|---|
| A1 | 江苏新万新服饰有限公司 | **template constant** | manufacturer name — part of the template file |
| A2 | 生产计划单（buy plan） | **template constant** | title |
| A4 / B4 | 供应商名称 | **PO** `vendor` (fallback `factory`) | supplier |
| Q4 / R4 | 日期 | **generated** | export timestamp |
| A5 / B5 | 面料/FIBER | **进度表** `fabric_detail` (fallback style-fabric mapping) | e.g. `HB-XD6786 94%rayon 6%span liquid jersey 200gsm 有效170cm` |
| Q5 / R5 | 更新日期 | **generated** | last-update timestamp |
| A6 / C6 | 品名/Description | **PO** `style_description` | e.g. 针织女套头衫 |
| Q6 | 2ND更新日期 | **generated** | optional 2nd-update timestamp |

---

## 3. Data columns (row 8–9 headers, data from row 10)

Grain: one row per **PO × Color**; contract/style span-merge across their rows.

| Col | Header (中文 / EN) | Source | Field | Notes |
|:--:|---|:--:|---|---|
| A | 合同号 / Contract No. | 进度表 | `contract_no` | matched to PO by PO#→style; blank if no 进度表 row |
| B | 款号 / Style | PO | `style` | span-merged per style |
| C | PO号 / PO No. | PO | `po_number` | |
| D | CPO# | PO | `cpo` | |
| E | 仓库代码 / Warehouse | **CPRS** | — | PO `ship_to`/`destination_code` → `/warehouse-lookup/resolve` |
| F | 买家 / Buyer | PO | `buyer` (fallback `customer`) | also feeds CPRS `accountCode` |
| G | 颜色(英文) / Color EN | PO | `SizeRow.color` | |
| H | 颜色(中文) / Color CN | color-translation | — | `get_color_translation_store()`; fallback 进度表 `color_cn` |
| I–M | XS · S · M · L · XL | PO | `SizeRow.units` | by size; only sizes present in the order |
| N | 总数量 / Total | PO | derived | sum of I–M |
| O | 离厂时间 / X-FTY | 进度表 → PO | `ex_fty` → `xport_date` | 进度表 first, PO fallback |
| **P** | **红色箱贴纸 / Red Box Sticker** | **CPRS** | — | see §4 |
| **Q** | **主箱唛 / Main Carton Mark** | **CPRS** | — | see §4 |
| R | 备注 / Remarks | PO | `packaging` / `hanger` | e.g. 平装+衣架 (flat pack + hanger) — **PO-sourced** (not CPRS) |

---

## 4. The two CPRS-driven columns (P, Q)

Both come from the same `/evaluate` call, `domain == "carton"` results:

### P — 红色箱贴纸 (Red Box Sticker)

- **CPRS subtype:** `carton/red_carton_sticker`
- **Value:** the customer's 2-letter red-sticker code (e.g. Macy's) from the
  result content; **artwork** from `GET /manual-images/:id/file` embedded as the
  cell image.
- **"无需" rule:** when the result `status == not_applicable` → write **无需**.
  Confirmed by the KB's own red-sticker table: *STOCK orders and the CL (HK) /
  DN (Holland/EU) warehouses need no red sticker* — which is exactly why the
  reference file shows 无需 on the `DN`/Bleckmann and `STOCK` rows.

### Q — 主箱唛 (Main Carton Mark)

- **CPRS subtypes:** `carton/carton_marking` (CTN# + net weight) plus
  `carton/warehouse_diamond` (required diamond markings) and
  `carton/shipping_consignee` as applicable.
- **Value:** artwork from `/manual-images/:id/file` embedded as the cell image
  (the reference file uses a shared carton-mark image across most rows).

**Image embedding:** the reference file uses WPS `=DISPIMG(...)` formulas.
The exporter will embed the CPRS image bytes the same way the Sky East exporter
handles DISPIMG-style images (openpyxl image anchor into the cell), so the output
opens identically in Excel/WPS.

---

## 5. Footer & subtotals

| Rows | Content | Source |
|---|---|---|
| 17 | 订单要求 · TTL total (N17) | derived (grand total) |
| 18–21 | 溢短装 · 包装 · 样衣 · 主箱唛 notes | **template constants** (optionally CPRS packaging/sample rules) |
| 22–23… | **per-color subtotals** (藏青 600 / 泥粉 600) | derived — aggregate size breakdown grouped by color EN/CN |

Per-color subtotals and DISPIMG images are **Sky-East-exporter features**
(`color_totals`, image embedding) — the current default GIII exporter has
neither. This is why the build is a Sky-East-class exporter, not a template swap.

---

## 6. Gap flags (confirm before build)

- **合同号 coverage** — depends on the 大货进度表 being uploaded for the brand;
  no 进度表 row → blank contract number. (Same resolution the All Orders view
  already uses.)
- **仓库代码 / 买家 → CPRS** — relies on PO `ship_to` being clean enough for
  `/warehouse-lookup/resolve`, and buyer text matching the account catalog.
  Unmatched → leave code blank + log; never fail the export.
- **`contextFields` gates** — `/evaluate` may return `pending_input` for gated
  requirements (e.g. `has_belt`, `is_lined`). For carton subtypes these rarely
  gate, but the exporter should pass through known garment attributes and treat
  `pending_input` like `confirmed` for display (with a log note).
- **CPRS availability** — if the KB is unreachable or no API key is configured,
  P/Q fall back to blank/无需 with a warning; the buy plan still generates.
- **备注 (R)** — **RESOLVED: PO-sourced** (`packaging`/`hanger`, e.g. 平装+衣架).
  Not a CPRS lookup.

---

## 7. Build outline (Step 2, for reference)

1. `po_extractor/utils/cprs_client.py` — REST client (base URL + `x-api-key`
   from Admin → Settings), methods `resolve_client`, `resolve_warehouse`,
   `list_accounts`, `evaluate`, `manual_image`; per-key caching; `/health` probe.
2. GIII buy-plan exporter modeled on `sky_east_buyplan_export.py` (grouping,
   `color_totals` subtotals, DISPIMG image embedding), reading `GIII.xlsx` +
   `GIII_config.json` as the template.
3. Register `GIII.xlsx` in `data/buyplan_templates/` so GIII POs route to it
   (per-client lookup falls back to `default.xlsx` only when absent).
4. Admin → Settings: CPRS section (base URL, API key, Test-connection button).
5. Graceful degradation everywhere CPRS is called.

*Not built yet — this document is the spec that precedes the build.*
