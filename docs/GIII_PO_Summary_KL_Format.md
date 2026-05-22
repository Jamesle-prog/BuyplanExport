# GIII Legacy PO — KL-Format Summary Specification

**Version:** 1.1  
**Last updated:** 2026-05-18  
**Reference file:** `LSKHHN_KL_POs.xlsx` (Desktop › GIII › Suits › PO › KL_PO)

---

## 1. Purpose

This document defines the requirements for generating a **KL-format PO Summary Excel workbook**
from G-III Apparel Group Legacy PDF purchase orders.  It covers:

- Which fields to extract from the PDF, and how
- Brand-specific extraction differences (DKNY / KL / CK)
- How each extracted value maps to an output column
- Derived / calculated values (Pack Ratio, Line Total, Ship To)
- Sheet layout and formatting rules

The specification is the single source of truth for:
- `po_extractor/parsers/legacy_giii.py` — extraction logic
- `po_extractor/ui_helpers/kl_format.py` — Excel generator
- `scripts/build_dkny_summary.py` — standalone batch script (DKNY)

---

## 2. Input Format

**Parser:** `legacy_giii` (FORMAT_LEGACY)  
**File type:** Multi-page PDF with reading-order text extraction (`pypdfium2`)  
**Characteristic keywords:** `PO NUMBER`, `STYLE#`, `LN#`

> All field labels in GIII Legacy PDFs are uppercase. Text is doubled by the PDF
> layout engine — i.e. each value appears twice on the same line. Patterns must use
> either non-greedy matching or backreference lookahead to strip the duplicate.

### 2.1 Brand variants

All three brands use the same `legacy_giii` format.  The brand code is detected from the
`ISSUED BY` line and drives brand-specific extraction rules.

| Brand | PO prefix | Brand code | Key differences |
|---|---|---|---|
| **DKNY** | `DUKHHA*` | *(none)* | No MSRP; no CPO line (default `TBA`); backreference description; "Hanger,unless…" line |
| **KL** | `LSKHHN*` | `KL` | Has MSRP; CUST PO field; W/TARIFF FOB; PPK explicit ratio; description from DESCRIPTION…HANGER line |
| **CK** | `CSKHHA*` | `CKSui` | No MSRP; CPO field (`TBD`); FOB with `$` prefix; PPK explicit ratio; apostrophe in description |

---

## 3. Extraction Rules

### 3.1 Brand detection

```python
BRAND_CODE_PATTERN = r'ISSUED BY\s+\S+\s+\d+\s+(\w+)\s+SHIP TO'
```

Returns `'KL'`, `'CKSui'`, or `None` (DKNY).  Drives all brand-specific branches below.

### 3.2 PO-level fields (one value per PDF)

| Field | PDF label / location | Pattern key | Brand notes |
|---|---|---|---|
| PO Number | `PO NUMBER DUKHHA057R` | `PO_NUMBER_PATTERN` | All brands |
| Style | `STYLE# UJ6TF105` | `STYLE_PATTERN` | All brands; first token only |
| PO Date | `PO DATE 5/15/26` | `PO_DATE_PATTERN` | All brands; stored as `issue_date` |
| ETD | Item line: `… 8/01/26` | `XPORT_DATE_PATTERN` | All brands; 2-digit year → 4-digit |
| Season | `SEASON V` | `SEASON_PATTERN` | All brands |
| Vendor Code | `VENDOR HHN` | `VENDOR_PATTERN` | All brands |
| Vendor Name | Date-prefixed line before `STYLE#` | `VENDOR_NAME_PATTERN` | All brands; stored as `seller` |
| Customer Name | After `PO NUMBER \w+`, backreference | `CUSTOMER_NAME_PATTERN` | All brands; stored as `customer` |
| Ship To | Constructed from customer + address lines | see §3.3 | All brands |
| Factory | `FACTORY 01423 - CHANGZHOU…` | `FACTORY_PATTERN` | All brands |
| Country of Origin | `CNTRY OF ORIGIN CHINA` | `CNTRY_OF_ORIGIN_PATTERN` | All brands |
| Incoterm | `INCO TERMS: FOB` + `PORT: SHANGHAI` | `INCOTERM_PATTERN` + `PORT_PATTERN` | All brands; joined |
| HTS# | `HTS SUMMARY PAGE` section | `HTS_PATTERN` | All brands |
| Fabric / Composition | `… HB-XXXXX TARIFF:` | `FABRIC_PATTERN` + `COMPOSITION_PATTERN` | All brands |
| Pack Type | `FLAT PACK TTL` | `PACK_PATTERN` | All brands; stored as `packaging` |
| Discount | `subject to a .75% discount` | `DISCOUNT_PATTERN` | All brands |
| Issued By | `ISSUED BY laniqua.mcmillian` | `ISSUED_BY_PATTERN` | All brands |

### 3.3 Brand-specific fields

| Field | DKNY | KL | CK |
|---|---|---|---|
| **FOB Price** | `FOB: 3.45` → `FOB_PRICE_PATTERN` | `FOB:$3.89/ $3.50 W/TARIFF` → `KL_FOB_PATTERN` (W/TARIFF value) | `FOB: $3.60` → `FOB_PRICE_PATTERN` (handles `$` prefix) |
| **MSRP** | None | `MSRP: $59` → `MSRP_PATTERN` | None |
| **CPO** | No line → default `'TBA'` | `CUST PO: TBA` → `CPO_PATTERN` | `CPO: TBD` → `CPO_PATTERN` |
| **Pack Ratio** | Computed from GCD of size units | `PPK ... (1-2-2-1)` → `PPK_PATTERN` | `PPK ... (1-2-2-1)` → `PPK_PATTERN` |
| **Hanger Info** | `Hanger,unless specified…` → `HANGER_PATTERN` | `DESCRIPTION … HANGER` line → `KL_HANGER_PATTERN` | `Hanger,unless specified…` → `HANGER_PATTERN` |
| **Description** | Backreference dedup: `DESCRIPTION DU5105 NOVEMBER 2026 DU5105…` → `GIII_DESCRIPTION_PATTERN` | Text between DESCRIPTION and HANGER → `KL_DESC_PATTERN` | Apostrophe-aware backreference (e.g. `WOMEN'S BLOU ROSS 25`) → `GIII_DESCRIPTION_PATTERN` |

### 3.4 Ship To construction

```python
CUSTOMER_NAME_PATTERN = r'PO NUMBER\s+\w+\s+([A-Z][A-Z ]+)(?=\s+\w+\s+\1)'
SHIP_ADDR1_PATTERN    = r'(\d{3,4}\s+[A-Z ]+?)\s+DISTRIBUTION CENTER'
SHIP_CITY_PATTERN     = r'([A-Z]+,\w{2}\s+\d{5})'
```

Assembled as:  
`{customer} / {addr_line1} / DISTRIBUTION CENTER / {city_state_zip}`

Example:  
`ROSS STORES / 3404 INDIAN AVE / DISTRIBUTION CENTER / PERRIS,CA 92571`

If address lines cannot be parsed, `ship_to` falls back to customer name alone.
The `kl_format.py` generator also checks `_KNOWN_SHIP_TO` as a fallback lookup.

### 3.5 Size rows (one row per PDF item line)

| Field | Source | Pattern |
|---|---|---|
| Color Code/Name | `COD/NAME` column in LN# table | `FULL_PATTERN` group 1 |
| Size | `SIZ` column | `FULL_PATTERN` group 2 |
| Units | `UNITS` column | `FULL_PATTERN` group 3 |
| UPC | `UPC#` column (12-digit) | `FULL_PATTERN` group 4 |

---

## 4. Output Workbook — KL Format

**File:** `{brand}_{season}_PO_Summary.xlsx`  
**Sheets:** `PO Detail` (tab 1) · `Summary` (tab 2)

### 4.1 PO Detail sheet

One row per **PO / Style / Color / Size** combination.

| # | Column | Source / Rule | Brand notes |
|---|---|---|---|
| 1 | PO Number | `po_number` | |
| 2 | Style | `style` | |
| 3 | Color | Full `color` value | |
| 4 | Size | `size` | |
| 5 | Units | `units` (integer) | |
| 6 | UPC | `upc` | |
| 7 | Unit Price (FOB) | `unit_cost` as float | KL: W/TARIFF price; CK: strips `$` prefix |
| 8 | MSRP | `msrp` from DB | KL: e.g. `59`; DKNY/CK: blank |
| 9 | Line Total ($) | `round(units × unit_cost, 2)` | |
| 10 | ETD | `xport_date` normalised to `M/D` | |
| 11 | PO Date | `issue_date` | |
| 12 | Ship Date | Same as PO Date | |
| 13 | Customer Name | `customer` | |
| 14 | Ship To | `ship_to` full address string | |
| 15 | Hanger Info | `hanger` | Brand-specific (see §3.3) |
| 16 | Pack Ratio | **Derived:** KL/CK: from PPK; DKNY: GCD of size units | |
| 17 | HTS# | `style_group` | |
| 18 | CPO | `cpo` from DB (default `TBA` if blank) | KL: `TBA`; CK: `TBD`; DKNY: `TBA` |
| 19 | Description | `description_code` | Brand-specific extraction (see §3.3) |
| 20 | Factory | `factory` | |
| 21 | Vendor | `seller` | |

**Grand Total row** (amber fill `FFC000`, bold): sums Units and Line Total columns only.

### 4.2 Summary sheet

**Part A — Pivot per PO:**  
Columns: `PO Number · Style · Description · Color · ETD · FOB Price · MSRP · [sizes…] · Total Units`  
One row per PO × Color combination. Grand Total row appended.

**Part B — Style rollup** (separated by a blank row + new header):  
Columns: `Style · Description · FOB Price · MSRP · Total Units · PO Count`  
One row per Style. Grand Total row appended.

### 4.3 Pack Ratio calculation

**DKNY** — computed from size rows:
```
gcd_val = GCD(unit_counts)
pack_ratio_string = '-'.join(str(units_for_size // gcd_val) for size in SIZE_ORDER if present)
```

**KL / CK** — extracted directly from PPK line in PDF:
```python
PPK_PATTERN = r'PPK[^(]*\((\d[\d-]+)\)'  # e.g. "PPK 6 (1-2-2-1)" → "1-2-2-1"
```

If PPK is not found, falls back to GCD calculation.

### 4.4 ETD normalisation

Input `xport_date` is stored as `M/DD/YYYY`.  
Output ETD: `M/D` (strip leading zeros) → `8/1`.

---

## 5. Formatting

| Element | Style |
|---|---|
| Header row fill | Blue `#366092`, white bold Calibri 10 |
| Alternate data rows | Light blue `#DCE6F1` on even rows |
| Grand Total rows | Amber `#FFC000`, bold |
| All cells | Thin grey border `#AAAAAA` |
| Numbers | Right-aligned |
| Text | Left-aligned |
| Row height (header) | 28 pt |
| Freeze panes | Row 1 on both sheets |

---

## 6. Sizing constants

```python
KL_SIZE_ORDER = [
    'PXS', 'PS', 'PM', 'PL', 'PXL', 'P1X', 'P2X', 'P3X',
    'XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL',
    '0X', '1X', '2X', '3X', '4X',
]
```

---

## 7. Known limitations / data quality notes

| Issue | Detail |
|---|---|
| Color name truncation | GIII PDF column width cuts names (e.g. `ESPRES` = `ESPRESSO`). Requires a separate color mapping table to recover full names. |
| MSRP | Only present in KL PDFs. Blank for DKNY and CK. |
| CPO | KL: `TBA`, CK: `TBD`, DKNY: `TBA` (no CPO line; default applied). |
| 2-digit year in PO Date | Stored as-is (e.g. `5/15/26`). Convert to 4-digit if needed downstream. |
| KL PPK not found | Falls back to GCD computation from size rows. |

---

## 8. Implementation entry points

| Component | Location |
|---|---|
| Regex patterns | `po_extractor/config.py` |
| PDF parser | `po_extractor/parsers/legacy_giii.py` |
| Data model | `po_extractor/models/po_data.py` — `POMetadata.description_code`, `.hanger`, `.msrp`, `.cpo` |
| DB schema | `po_extractor/store/_po_store_schema.py` — `hanger`, `description_code`, `msrp`, `cpo` columns |
| DB write | `po_extractor/store/_po_store_write.py` — 45-column INSERT |
| DB read | `po_extractor/store/_po_store_read.py` — `list_pos()` includes `msrp`, `cpo` |
| Excel generator | `po_extractor/ui_helpers/kl_format.py` — `generate_kl_format_excel()` |
| Streamlit UI | `ui/giii/reports_tab.py` — "📐 KL Format Summary" button |
| Batch script (DKNY) | `scripts/build_dkny_summary.py` |
