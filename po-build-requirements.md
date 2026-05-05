# PO Extractor — Build Requirements Document

**Version:** 1.0  
**Date:** 2026-04-18  
**Author:** James / Claude  

---

## 1. Overview

Build a Python command-line tool that batch-extracts purchase order data from PDF files across two distinct PO formats, consolidates them into a unified data model, and exports the results to formatted Excel workbooks. The tool should auto-detect the PO format and apply the correct parser.

---

## 2. Supported PO Formats

### Format A — Infor Nexus (G-III / DKNY / Donna Karan)

**Identifier:** PDF text contains `"Powered by Infor Nexus"` and/or `"Order Number"` field in the header block.

**Structure:**
- Multi-page PDF, structured with labeled blocks: BUYER, SELLER, FACTORY, SHIP TO
- Header section with key-value pairs in a fixed layout
- Line items table with columns: Line #, Style, Color Code, Color Name, DIM, Size, UOM, Units, UPC, Cost P/U, Extended Cost, Ship Via, Orig X-Port Date, Last Confirmed Date
- Size breakdown per line item as a horizontal grid: Size / UOM / UPC / Qty (and optionally Ratio for assortments)
- PO Summary section at the end with size totals per line

**Fields to Extract:**

| Field | Source Location | Example |
|---|---|---|
| PO Number | `Order Number` or `PO Number` row | `DW843121N2` |
| Issue Date | `Issue Date` row | `2026-01-14` |
| Buyer | BUYER block, first line | `G-III LEATHER FASHIONS` or `G-III APPAREL GROUP LTD` |
| Seller | SELLER block | `HIGH HOPE NEWEST APPAREL CORP.,LTD` |
| Factory | FACTORY block, first line | `CHANGZHOU JINTAN XINZHUANGYUAN GARMENT CO.,LTD.` |
| Factory Code | FACTORY block, last line before country | `01423` |
| Ship To | SHIP TO block | `G-III C/O BLECKMANN (N2), Almelo, NETHERLANDS` |
| Destination Code | SHIP TO block, last line | `WRHN2`, `WRHPN`, `WRHUC`, `WRHDN`, `WRHCL` |
| Division Code | `Division Code` row | `0075 N75` |
| Division Name | `Division Name` row | `DW DKNY W/SPRTSWR` |
| Season | `Season` row | `251532 274183 V` |
| Incoterm | `Incoterm` row | `FOB ORIGIN` |
| Origin Port | `Origin Port` row | `Shanghai` |
| Payment Terms | `Payment Terms` row | `Supplier Damage Allow` |
| Country of Origin | `Country of Origin` row | `China` |
| Label/Hanger Discount | `Discount` row | `0.75%` |
| Approval Status | `Approval Status` row | `Y` or `N` |
| Special Instructions | `Special Instructions` row | `FA26 MILAN` (if present) |
| Issued By | `Issued By` row | `helen.cho` |

**Line-Level Fields:**

| Field | Source | Example |
|---|---|---|
| Line # | `Line #` column | `1`, `2`, ... `8` |
| Style | `Style` column | `P63E8END`, `P63F8ENF`, `P63E8ETA` |
| Color Code | `Color Code` column | `BLK`, `TVN` |
| Color Name | `Color Name` column | `BLACK`, `TRAVERTINE` |
| DIM | `DIM` column | `-` (standard) or `Y13`, `611`, `917` (assortment) |
| Packaging | `Packaging` row below line | `C` (carton) or `F` (flat pack) |
| Style Description | `Style Description` row | `L/S SOHO PONTE TECH`, `SOFT PONTE FIT AND F`, `SOHO PONTE ONE BUTTO` |
| Style Group | `Style Group` row | `KNIT JACKET`, `KNIT PANTS` |
| Customer | `Customer` row below line | `STOCK`, `G-III APPAREL SPAIN, S.L.`, `AM RETAIL GROUP (DKI)`, `MY MACY'S`, `MY MACY'S-OMNI CHANNEL`, `DILLARD'S` |
| Unit Cost | `Cost P/U` column | `17.10` or blank |
| Line Extended Cost | `Extended Cost` column | `1,077.30` or blank |
| Factory Ship Date | `Factory Ship by Date` row | `2026-04-17` |
| X-Port Date | `Orig X-Port Date` column | `2026-04-17` |

**Size-Level Fields (per line):**

| Field | Source | Example |
|---|---|---|
| Size | Size grid header | `XXS`, `XS`, `S`, `M`, `L`, `XL` |
| UPC | UPC row in size grid | `700948471565` |
| Ratio | Ratio row (assortment lines only) | `1`, `2`, `3` |
| Qty | Qty row in size grid | `11`, `17`, `15` |

**Edge Cases to Handle:**
- Multi-line POs: up to 8+ lines per PO (e.g., `DW843124UC` has 8 lines across 5 pages)
- Assortment lines (DIM ≠ `-`): include Ratio row per size
- Missing unit cost / extended cost: some lines have blank costs
- Variable size ranges: some lines include XXS, others start at XS
- Multi-color within one PO: BLK + TVN lines
- Customer varies per line within same PO

---

### Format B — Legacy G-III System

**Identifier:** PDF text contains `"PO NUMBER"`, `"STYLE#"`, `"LN#"`, and `"CNTRY OF ORIGIN"` but does NOT contain `"Infor Nexus"`.

**Structure:**
- Fixed-width columnar layout rendered as text
- Page header repeats on each page with style/factory info
- Data section starts after a line beginning with `LN#`
- Each size/color/UPC entry is on its own line
- Color is in `COLOR/DESCRIPTION` format (e.g., `BLK/BLACK`)
- TTL (total) line marks end of a color block
- MSRP details at the end of the document

**Fields to Extract (Metadata — from combined text of all pages):**

| Field | Regex Pattern | Example |
|---|---|---|
| PO Number | `PO NUMBER\s+(\w+)` | `CKHHP2598` |
| Style | `STYLE#\s+(.+)` | `UH6TL772` |
| Vendor | `VENDOR\s+(\w+)` | vendor code |
| Issued By | `ISSUED BY\s+([a-zA-Z0-9.]+)` | `helen.cho` |
| PO Date | `PO DATE\s+(\d{1,2}/\d{1,2}/\d{2,4})` | `3/05/26` |
| Vendor Country | `VEND CNTRY\s+(\w+(?:\s*-\s*\w+)?)` | `CHINA - CN` |
| Factory | `FACTORY\s+(\d+)\s*-\s*([A-Z]+(?:\s[A-Z]+)*)` | `01423 - JINTAN XINZHUAN` |
| Country of Origin | `CNTRY OF ORIGIN\s+(\w+)` | `CHINA`, `VIETNAM` |
| Hanger | Text after `HANGER` keyword | hanger info |
| Price Type | `PRICE TYPE:\s+(\w+)` | `FOB` |
| Port | `PORT:\s+(.+)` | `SHANGHAI - CHINA`, `HAIPHONG - VIETNAM` |
| Inco Terms | `INCO TERMS:\s+(\w+)` | `FOB` |
| Ship Location | `SHIP LOCATION:\s+(\w+)` | `ORIGIN` |
| MSRP | `(\w+)\s+(BLK|CAT|...)\s+MSRP\s+\$(\d+\.\d{2})` | `UH6TL772 CAT MSRP $59.00` |

**Line-Level Data (from lines after `LN#`):**

Each data line follows the pattern:
```
COLOR/DESCRIPTION  SIZE  UNITS  UPC(12-digit)  [PRICE]  [other fields]
```

**Extraction Logic (port from existing Python):**

```
FULL_PATTERN = r'(COLOR_PATTERN)\s+(SIZE_PATTERN)\s+(\d+)\s+(\d{12})'
```

Where:
- `COLOR_PATTERN = r'(\w+(?:/\w+)+|\w+/\w+(?:\s\w+)?)'` — captures `BLK/BLACK`, `CAT/CAMEL`
- `SIZE_PATTERN = r'(PS|PM|PL|PXL|XXS|XS|S|M|L|XL|1X|2X|3X)'`
- Units = integer before the 12-digit UPC
- UPC = 12-digit barcode

**Fallback Logic:**
- If `FULL_PATTERN` doesn't match but `SIZE_PATTERN` + `UNITS_PATTERN` match on the same line, use `current_color` (carried from previous match)
- `TTL` line marks end of a color block; text before `TTL` contains hanger info

**Edge Cases:**
- Color carries forward: if a line has size/units/UPC but no color, use the last matched color
- `REVISION` marker: some POs are revisions (header says `* * * * * * R E V I S I O N * * * * * *`)
- Multi-page: metadata is on page 1; data spans pages 1-3; T&C and MSRP on last page
- Text extraction quality: PyMuPDF (`fitz`) extracts cleaner text than browser-based PDF readers

---

## 3. Unified Data Model

All extracted data (both formats) should normalize into these two tables:

### 3.1 Data Table (one row per PO / Style / Color / Size)

| Column | Type | Description |
|---|---|---|
| PO Number | str | e.g., `DW843121N2` or `CKHHP2598` |
| Style | str | e.g., `P63E8END` or `UH6TL772` |
| Color | str | e.g., `BLK` or `BLK/BLACK` |
| Size | str | e.g., `M`, `XL`, `PS` |
| Units | int | quantity for this size |
| UPC | str | 12-digit barcode |
| Source Format | str | `infor_nexus` or `legacy` |

### 3.2 Metadata Table (one row per PO)

| Column | Type | Description |
|---|---|---|
| PO Number | str | primary key |
| Style | str | |
| PO Date / Issue Date | str | |
| Vendor | str | |
| Issued By | str | |
| Factory | str | |
| Country of Origin | str | |
| Vendor Country | str | |
| Hanger | str | |
| Source Format | str | `infor_nexus` or `legacy` |
| File Name | str | source PDF filename |
| File Path | str | full path |

**Infor Nexus Extended Metadata** (additional columns, blank for legacy):

| Column | Type |
|---|---|
| Buyer | str |
| Ship To | str |
| Destination Code | str |
| Division | str |
| Season | str |
| Incoterm | str |
| Origin Port | str |
| Payment Terms | str |
| Discount | str |
| Approval Status | str |
| Customer | str |
| DIM / Pack | str |
| Packaging | str |
| Style Description | str |
| Style Group | str |
| Unit Cost | str |
| Line Extended Cost | str |
| Factory Ship Date | str |
| X-Port Date | str |
| Ratio | str |

---

## 4. Output Formats

### 4.1 CSV Intermediate Files (for data portability)

Three CSV files, matching the existing script outputs:

**a) `all_extracted_data_by_size_color.csv`**  
One row per PO / Style / Color / Size:  
`PO Number | Style | Color | Size | Units | UPC`

**b) `all_extracted_data_summary.csv`**  
One row per PO / Style / Color (with hanger info):  
`PO Number | Style | Color | Hanger`

**c) `all_extracted_metadata.csv`**  
One row per PO file:  
`PO Number | Style | Vendor | Issued By | PO Date | Vendor Country | Factory | Country of Origin | File Path | File Name | Hanger | Source Format`

For Infor Nexus POs, additional metadata columns:  
`Buyer | Ship To | Destination Code | Division | Season | Incoterm | Origin Port | Customer | Style Description | Style Group | Unit Cost | Ship Date | X-Port Date`

All CSV files use auto-versioning (`_v1`, `_v2`, ...) to avoid overwriting.

### 4.2 Buy Plan Excel — Primary Output (matches `CreateBuyPlan.py`)

This is the main deliverable. One `.xlsx` workbook with **one sheet per style**.

**Sheet layout (per style):**

```
Row 1:  A1="工厂信息："   B1=[Factory name]           J1="创建时间："  K1=[YYYY-MM-DD HH:MM:SS]
Row 2:  A2="款号："       B2=[Style number]
Row 3:  A3="面料信息："   B3=(blank — filled manually)
Row 4:  (blank)
Row 5:  Headers →  PO Number | Style | Color | [size columns] | Total
Row 6+: Data rows (one per PO/Style/Color combo, pivoted)
Last:   Total row (sum of all rows above)
```

**Pivot logic (from `transform_data()`):**
- Group by `[PO Number, Style, Color]`
- Pivot `Size` into columns, values = `Units`, aggfunc = `sum`, fill_value = `0`
- Drop any size column where all values are 0
- Reorder size columns per `SIZE_ORDER`: `PS | PM | PL | PXL | XXS | XS | S | M | L | XL | 1X | 2X | 3X`
- Add `Total` column = row sum of all size columns
- Add `Total` row at bottom = column sum of all data rows

**Excel formatting (from `format_table()`):**

| Element | Fill | Font | Border | Number Format |
|---|---|---|---|---|
| Header row (row 5) | Black `#000000` | White, bold | Thin black all sides | — |
| Data cells (row 6 to last-1, col 4+) | None | Default | Thin black all sides | `#,##0` |
| Total row (last row) | Yellow `#FFFF00` | Black, bold | Thin black all sides | `#,##0` |
| Total column (last col, rows 6 to last-1) | Yellow `#FFFF00` | Black, bold | Thin black all sides | `#,##0` |
| All cells | — | — | — | Center-aligned H+V, wrap text |

**Column widths:** Auto-fit to content + 2 chars padding.

**Sheet name:** First 31 characters of style number (Excel limit).

**File naming:** `transformed_data_by_style_filtered_with_totals_and_metadata.xlsx` with auto-versioning (`_v2`, `_v3`, ...).

---

## 5. Program Architecture

```
po_extractor/
├── main.py                  # CLI entry point
├── config.py                # Constants, regex patterns, size order
├── detectors/
│   └── format_detector.py   # Auto-detect PDF format
├── parsers/
│   ├── infor_nexus.py       # Format A parser
│   └── legacy_giii.py       # Format B parser (port of existing scripts)
├── models/
│   └── po_data.py           # Unified data classes
├── exporters/
│   ├── flat_export.py       # Format A output
│   ├── pivot_export.py      # Format B output
│   └── buyplan_export.py    # Format C output (formatted Excel)
└── utils/
    ├── pdf_reader.py        # PyMuPDF wrapper
    └── file_utils.py        # Folder scanning, versioned filenames
```

### 5.1 CLI Interface

```bash
# Basic usage — scan folder, auto-detect, export all formats
python main.py --input ./po_folder --output ./output

# Specify output format
python main.py --input ./po_folder --output ./output --format flat
python main.py --input ./po_folder --output ./output --format pivot
python main.py --input ./po_folder --output ./output --format buyplan
python main.py --input ./po_folder --output ./output --format all

# Single file
python main.py --input ./po_folder/DW843121N2.pdf --output ./output

# Recursive scan
python main.py --input ./po_folder --output ./output --recursive
```

### 5.2 Format Detection Logic

```python
def detect_format(text: str) -> str:
    if "Infor Nexus" in text or "Order Number" in text:
        return "infor_nexus"
    elif "PO NUMBER" in text and "STYLE#" in text and "LN#" in text:
        return "legacy"
    else:
        return "unknown"
```

---

## 6. Dependencies

```
pymupdf (fitz)     >= 1.23.0   # PDF text extraction
pandas             >= 2.0.0    # Data manipulation
openpyxl           >= 3.1.0    # Excel writing with formatting
```

---

## 7. Size Order Reference

Standard size order for column sorting in pivot/buyplan outputs:

```python
SIZE_ORDER = ['PS', 'PM', 'PL', 'PXL', 'XXS', 'XS', 'S', 'M', 'L', 'XL', '1X', '2X', '3X']
```

---

## 8. Test Data Summary

### Infor Nexus POs (18 files uploaded)

| PO Number | Style | Colors | Lines | Total Qty | Notes |
|---|---|---|---|---|---|
| DW843120DN | P63E8END | BLK | 1 | 100 | EU ship (Bleckmann DN) |
| DW843121N2 | P63E8END | BLK | 1 | 63 | EU ship (Bleckmann N2), includes XXS |
| DW843122PN | P63E8END | BLK | 1 | 354 | EU ship (Bleckmann PN) |
| DW843123UC | P63E8END | BLK, TVN | 2 | 775 | US ship, 2 colors |
| DW843124UC | P63E8END | BLK, TVN | 8 | 692 | US ship, assortments (Y13/611/917), 5 pages |
| DW843125UC | P63E8END | BLK | 1 | 260 | Macy's |
| DW843126UC | P63E8END | BLK | 1 | 100 | Macy's Omni Channel |
| DW843140CL | P63F8ENF | BLK, TVN | 2 | 60 | HK ship (Dynamic), XS-M only |
| DW843141DN | P63F8ENF | BLK | 1 | 150 | EU ship (Bleckmann DN) |
| DW843142N2 | P63F8ENF | BLK | 1 | 69 | EU ship (Bleckmann N2), includes XXS |
| DW843143PN | P63F8ENF | BLK | 1 | 371 | EU ship (Bleckmann PN), includes XXS |
| DW843144UC | P63F8ENF | BLK, TVN | 2 | 815 | US ship, 2 colors |
| DW843145UC | P63F8ENF | BLK, TVN | 7 | 690 | US ship, assortments, 5 pages |
| DW843146UC | P63F8ENF | BLK | 1 | 260 | Macy's |
| DW843147UC | P63F8ENF | BLK | 1 | 100 | Macy's Omni Channel |
| DW845380UC | P63E8ETA | BLK | 1 | 477 | Stock |
| DW845381UC | P63E8ETA | BLK | 1 | 727 | Dillard's |

**Styles covered:** P63E8END (Knit Jacket), P63F8ENF (Knit Pants), P63E8ETA (Knit Jacket)

### Legacy POs (6 files uploaded, partially readable)

| Style | Origin | Port | Notes |
|---|---|---|---|
| UH6TL772 | China | Shanghai | Revision, MSRP $59.00 |
| UH6TL772 | China | Shanghai | Revision, MSRP $59.00 (duplicate?) |
| UH6TL772 | Vietnam | Haiphong | New PO, MSRP $59.00 |
| UH6TL772 | Vietnam | Haiphong | New PO, MSRP $69.00 |
| UH6TL773 | China | Shanghai | Revision, 2 colors, MSRP $79.00 |
| UH6TL773 | China | Shanghai | Revision, Omni Channel, 2 colors, MSRP $79.00 |

---

## 9. Migration Notes

### From Existing Python Scripts

The following scripts should be consolidated into this tool:

| Script | Function | Status |
|---|---|---|
| `PO_Extract.py` | Basic legacy extractor (v1) | → Replace with `parsers/legacy_giii.py` |
| `PO_V3.py` | Enhanced legacy extractor with metadata | → Replace with `parsers/legacy_giii.py` |
| `PO_Scan_Output_GIII_Combined.py` | Combined extract + buy plan output | → Replace entirely |
| `CreateBuyPlan.py` | Buy plan Excel formatter | → Port to `exporters/buyplan_export.py` |
| `Mask_PO_Price.py` | Price masking utility | → Keep separate (optional feature) |

### Key Improvements Over Existing Scripts

1. **Auto-detect format** — no need to run separate scripts for Infor Nexus vs legacy
2. **Infor Nexus parser** — new capability (existing scripts only handle legacy)
3. **Unified data model** — both formats normalize to same schema
4. **Multiple export formats** — flat, pivot, and buy plan in one run
5. **CLI interface** — folder scanning with `--recursive`, output format selection
6. **Better error handling** — per-file error logging, continue on failure
7. **Versioned output files** — auto-increment filenames to avoid overwrites

---

## 10. Future Considerations

- **Odoo integration**: Export data directly into Odoo purchase order module via XML-RPC
- **Additional PO formats**: Calvin Klein, Tommy Hilfiger, or other clients with different layouts
- **Price masking**: Integrate `Mask_PO_Price.py` functionality as `--mask-prices` flag
- **Web UI**: Optional Flask/Streamlit frontend for non-technical users
- **Database storage**: Write extracted data to PostgreSQL (HHP-NAS) for the garment ERP system
