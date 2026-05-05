# PO Automation System — Implementation Guide

**Version:** GIII Edition v3 (with Zalando Excel Pipeline)  
**Last Updated:** 2026-04-19  
**Audience:** Developers implementing the system from scratch

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technology Stack](#2-technology-stack)
3. [Repository Structure](#3-repository-structure)
4. [Data Models](#4-data-models)
5. [Authentication & Company Registry](#5-authentication--company-registry)
6. [PDF Pipeline (GIII / DKNY)](#6-pdf-pipeline-giii--dkny)
7. [Excel Pipeline (Zalando)](#7-excel-pipeline-zalando)
8. [Universal File Detector](#8-universal-file-detector)
9. [Buy Plan Exporters](#9-buy-plan-exporters)
10. [PO Store (SQLite)](#10-po-store-sqlite)
11. [Streamlit Web UI](#11-streamlit-web-ui)
12. [Column Mapping Schema](#12-column-mapping-schema)
13. [Setup & Deployment](#13-setup--deployment)
14. [Adding a New Client](#14-adding-a-new-client)

---

## 1. System Overview

This system automates the extraction, normalisation, and export of Purchase Orders (POs) from multiple apparel clients into a standardised buy plan format used internally at the factory.

### Supported Clients

| Client | File Format | Detection Method |
|--------|-------------|-----------------|
| GIII (G-III Apparel Group) | PDF (Infor Nexus or Legacy) | Text keyword scan |
| DKNY (Donna Karan) | PDF (Infor Nexus) | Text keyword scan |
| Zalando | Excel (.xlsx/.xlsm) | Sheet name `1.1.PO_Client` |

### Key Concepts

- **Repeat Orders:** The same style/colour can appear across multiple PO numbers (e.g. re-orders within a season). These are preserved as separate rows — never merged.
- **Two-Row Header Pattern:** Zalando Excel files use Row 1 for the client's original column names and Row 2 for the factory's internal standardised names. Data starts at Row 3.
- **Buy Plan Output:** One Excel workbook with an Index sheet plus one sheet per style, optionally including embedded garment photos.
- **Template_P Output:** One workbook per fabric code, one sheet per style. Colour × Size pivot table. Used for fabric planning.
- **Cross-Comparison:** A verification sheet that confirms Template totals equal Template_P totals per style.

### System Flow

```
User uploads files (PDF / Excel / ZIP of photos)
        ↓
Universal File Detector assigns format_id + company
        ↓
User confirms or overrides company assignment
        ↓
                ┌──────────────────────┬───────────────────────┐
                │  PDF files           │  Excel files          │
                │  (GIII / DKNY)       │  (Zalando)            │
                │  ↓                   │  ↓                    │
                │  parse_pdf()         │  parse_client_excel_  │
                │  → SizeRow model     │  to_df()              │
                │  → POStore (SQLite)  │  → flat DataFrame     │
                └──────────────────────┴───────────────────────┘
                        ↓                        ↓
                  Export: GIII         Export: Zalando BuyPlan
                  buy plan             + Template_P workbooks
                                       + Cross-Comparison sheet
```

---

## 2. Technology Stack

### Runtime
- **Python 3.11+**
- **Streamlit 1.32+** — Web UI

### Core Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| `pymupdf` (fitz) | ≥1.23.0 | PDF text extraction |
| `openpyxl` | ≥3.1.0 | Excel read/write |
| `pandas` | ≥2.0.0 | DataFrame handling |
| `bcrypt` | ≥4.0.0 | Password hashing |

### Standard Library
- `sqlite3` — PO history store
- `json` — company registry persistence
- `dataclasses` — data models
- `zipfile` — photo ZIP extraction
- `os`, `pathlib` — file handling

### `requirements.txt`

```
pymupdf>=1.23.0
pandas>=2.0.0
openpyxl>=3.1.0
streamlit>=1.32.0
bcrypt>=4.0.0
```

---

## 3. Repository Structure

```
PO_Automation_GIII/
│
├── app.py                          # Streamlit entry point
├── requirements.txt
├── IMPLEMENTATION_GUIDE.md         # This file
│
├── auth/
│   ├── __init__.py
│   ├── users.py                    # User login, bcrypt, roles
│   ├── license.py                  # License validation stub
│   ├── companies.py                # Company registry (JSON-backed)
│   └── companies.json              # Auto-generated on first run
│
└── po_extractor/
    ├── __init__.py
    ├── config.py                   # SIZE_ORDER, global constants
    │
    ├── models/
    │   ├── __init__.py
    │   └── po_data.py              # SizeRow, POMetadata, POData dataclasses
    │
    ├── detectors/
    │   ├── __init__.py
    │   ├── format_detector.py      # Identify PDF format from text
    │   └── file_detector.py        # Universal detector → DetectionResult
    │
    ├── parsers/
    │   ├── __init__.py
    │   ├── infor_nexus.py          # PDF parser: Infor Nexus format
    │   ├── legacy_giii.py          # PDF parser: Legacy GIII format
    │   ├── client_excel.py         # Excel parser: two-row header format
    │   └── client_excel_multi.py   # Multi-file combiner with repeat order detection
    │
    ├── exporters/
    │   ├── __init__.py
    │   ├── hhp_buyplan_export.py   # Zalando buy plan workbook exporter
    │   └── hhp_template_p_export.py # Zalando Template_P exporter
    │
    ├── store/
    │   ├── __init__.py
    │   └── po_store.py             # SQLite PO history
    │
    └── utils/
        ├── __init__.py
        ├── pdf_reader.py           # PyMuPDF wrapper
        └── client_template.py      # Column mapping template generator
```

---

## 4. Data Models

**File:** `po_extractor/models/po_data.py`

### SizeRow

Normalised model — one record per (PO, style, colour, size).

```python
@dataclass
class SizeRow:
    po_number: str
    style:     str
    color:     str
    size:      str
    units:     int
    upc:       str
```

### POMetadata

```python
@dataclass
class POMetadata:
    po_number:         str
    style:             str
    po_date:           str
    vendor:            str
    factory:           str
    country_of_origin: str
    buyer:             str
    ship_to:           str
    division:          str
    division_code:     str
    division_name:     str
    season:            str
    factory_ship_date: str
    xport_date:        str
    source_format:     str   # "infor_nexus" | "legacy_giii" | "excel_zalando"
    file_name:         str
    file_path:         str
```

### POData

```python
@dataclass
class POData:
    metadata:  POMetadata
    size_rows: list[SizeRow]
```

### SIZE_ORDER (global)

**File:** `po_extractor/config.py`

```python
SIZE_ORDER = [
    'PXS','PS','PM','PL','PXL','P1X','P2X','P3X','P2XL','P3XL',
    'XXS','XS','S','M','L','XL','XXL','XXXL','0X','1X','2X','3X','4X'
]
```

---

## 5. Authentication & Company Registry

### 5.1 User Authentication

**File:** `auth/users.py`

Storage format (`auth/users.json`):

```json
{
  "admin": {
    "password": "<bcrypt_hash>",
    "role": "admin",
    "companies": []
  },
  "zalando_user": {
    "password": "<bcrypt_hash>",
    "role": "user",
    "companies": ["Zalando"]
  }
}
```

Rules:
- `role` is `"admin"` or `"user"`.
- For `"user"` role: `companies` is a whitelist — user can only see/process listed companies.
- For `"admin"` role: `companies: []` means unrestricted access to all companies.
- Passwords are stored as bcrypt hashes. Plain-text passwords are never stored.

Key functions:
```python
def verify_login(username: str, password: str) -> bool
def get_user(username: str) -> dict | None
def create_user(username: str, password: str, role: str, companies: list[str]) -> None
def update_password(username: str, new_password: str) -> None
def list_users() -> list[dict]
```

### 5.2 Company Registry

**File:** `auth/companies.py`  
**Persistence:** `auth/companies.json` (auto-created on first run)

#### Pre-seeded Companies

```python
_DEFAULTS = [
    {
        "name":         "GIII",
        "display_name": "G-III Apparel Group",
        "file_types":   ["pdf"],
        "formats":      ["infor_nexus", "legacy_giii"],
        "excel_sheet":  None,
        "color":        "#1f77b4",
        "active":       True,
    },
    {
        "name":         "DKNY",
        "display_name": "DKNY / Donna Karan",
        "file_types":   ["pdf"],
        "formats":      ["infor_nexus"],
        "excel_sheet":  None,
        "color":        "#ff7f0e",
        "active":       True,
    },
    {
        "name":         "Zalando",
        "display_name": "Zalando",
        "file_types":   ["excel"],
        "formats":      ["excel_zalando"],
        "excel_sheet":  "1.1.PO_Client",
        "color":        "#ff6900",
        "active":       True,
    },
]
```

#### Format-to-Company Reverse Map

```python
FORMAT_TO_COMPANIES = {
    "infor_nexus":   ["GIII", "DKNY"],
    "legacy_giii":   ["GIII"],
    "excel_zalando": ["Zalando"],
}
```

#### Public API

```python
def ensure_defaults_seeded() -> None          # Call at app startup
def list_companies(active_only=True) -> list[dict]
def list_company_names(active_only=True) -> list[str]
def get_company(name: str) -> dict | None
def upsert_company(name, display_name, file_types, formats,
                   excel_sheet, color, active) -> None
def deactivate_company(name: str) -> None
def delete_company(name: str) -> None
def companies_for_format(fmt: str) -> list[str]
```

#### Startup Call (in `app.py`)

```python
from auth.companies import ensure_defaults_seeded
ensure_defaults_seeded()
```

---

## 6. PDF Pipeline (GIII / DKNY)

### 6.1 Format Detection

**File:** `po_extractor/detectors/format_detector.py`

Function: `detect_format(text: str) -> str`

Returns one of: `"infor_nexus"`, `"legacy_giii"`, `"unknown"`

Logic:
- Look for known header strings in the extracted text.
- Infor Nexus files contain markers like `"Purchase Order"`, `"Infor Nexus"`.
- Legacy GIII files contain older header patterns.

### 6.2 PDF Text Extraction

**File:** `po_extractor/utils/pdf_reader.py`

```python
import fitz  # PyMuPDF

def read_pdf_text(path: str) -> str:
    doc = fitz.open(path)
    return "\n".join(page.get_text() for page in doc)
```

### 6.3 Parsers

#### Infor Nexus: `po_extractor/parsers/infor_nexus.py`

```python
def parse_pdf(path: str) -> list[POData]
```

- Opens PDF, extracts text per page.
- Identifies PO blocks by "Purchase Order #" markers.
- Extracts metadata fields using regex / line scanning.
- Parses size grid (sizes as column headers, units in cells).
- Returns one `POData` per PO number found in the file.

#### Legacy GIII: `po_extractor/parsers/legacy_giii.py`

Same interface: `parse_pdf(path: str) -> list[POData]`

Different parsing logic for the older GIII PDF format.

### 6.4 Routing

**File:** `app.py` → `_process_pdf_group()`

```python
from po_extractor.detectors.format_detector import detect_format
from po_extractor.utils.pdf_reader import read_pdf_text
from po_extractor.parsers import infor_nexus, legacy_giii

text = read_pdf_text(path)
fmt = detect_format(text)

if fmt == "infor_nexus":
    results = infor_nexus.parse_pdf(path)
elif fmt == "legacy_giii":
    results = legacy_giii.parse_pdf(path)
```

---

## 7. Excel Pipeline (Zalando)

### 7.1 Two-Row Header Convention

The Zalando Excel file (`1.1.PO_Client` sheet) uses a two-row header:

| Row | Purpose |
|-----|---------|
| 1 | Client's original column names (e.g. "Purchase Order Number") |
| 2 | Factory's internal standardised names (e.g. "PO番号") |
| 3+ | Data rows |

The parser reads Row 2 as the actual column header for internal processing.

### 7.2 Single-File Parser

**File:** `po_extractor/parsers/client_excel.py`

```python
SIZE_COLUMNS = ["XS", "S", "M", "L", "XL", "XXL"]
REQUIRED_COLUMNS = {"Purchase Order Number", "Main Supplier Config SKU"}

def parse_client_excel(path: str, sheet_name: str = "1.1.PO_Client") -> POData:
    """Parse a single Excel file → POData (normalised SizeRow model).
    Used for POStore insertion."""

def parse_client_excel_to_df(path: str, sheet_name: str = "1.1.PO_Client") -> pd.DataFrame:
    """Parse a single Excel file → flat DataFrame.
    One row per source row; size columns preserved as-is.
    Used for buy plan and Template_P export."""
```

**Internal logic for `parse_client_excel_to_df`:**

```python
wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
ws = wb[sheet_name]

rows = list(ws.iter_rows(values_only=True))
# Row index 0 = client headers (Row 1)
# Row index 1 = internal headers (Row 2)
# Row index 2+ = data

internal_headers = [str(c).strip() if c else "" for c in rows[1]]
data_rows = rows[2:]

df = pd.DataFrame(data_rows, columns=internal_headers)
df = df.dropna(how="all")
```

### 7.3 Multi-File Combiner

**File:** `po_extractor/parsers/client_excel_multi.py`

```python
@dataclass
class CombineResult:
    df:             pd.DataFrame
    repeat_orders:  dict[str, list[str]]  # style → list of PO numbers
    conflicts:      list[str]             # human-readable conflict descriptions
    source_files:   list[str]
    skipped_files:  list[str]

def combine_excel_files(
    paths: list[str],
    sheet_name: str = "1.1.PO_Client",
    prefer_latest: bool = True,
) -> CombineResult:
```

**Deduplication logic:**

- **Exact duplicate key:** `["Purchase Order Number", "Config SKU", "Main Supplier Color Description"]`
  - If the same (PO, SKU, Color) appears in two files, keep one (prefer latest file if `prefer_latest=True`).
- **Repeat order key:** `["Main Supplier Config SKU", "Config SKU", "Main Supplier Color Description"]`
  - Same style/colour under *different* PO numbers → these are repeat orders. Flag in `_repeat_order=True` column. Do NOT merge.

**Output columns added:**
- `_repeat_order`: `True` if this row is part of a repeat order group.
- `_source_file`: basename of the source Excel file.

**Usage:**

```python
from po_extractor.parsers.client_excel_multi import combine_excel_files

result = combine_excel_files(["/path/a.xlsx", "/path/b.xlsx"])
df = result.df
if result.repeat_orders:
    for style, po_list in result.repeat_orders.items():
        print(f"Style {style} appears in POs: {', '.join(po_list)}")
```

---

## 8. Universal File Detector

**File:** `po_extractor/detectors/file_detector.py`

### DetectionResult Dataclass

```python
@dataclass
class DetectionResult:
    filename:   str
    file_type:  str        # "pdf" | "excel" | "unknown"
    format_id:  str        # "infor_nexus" | "legacy_giii" | "excel_zalando" | "unknown"
    companies:  list[str]  # most-likely company first
    confidence: str        # "high" | "medium" | "low"
    detail:     str = ""   # human-readable reason
    error:      str = ""   # non-empty if detection failed
```

### Public Functions

```python
def detect_file(path: str) -> DetectionResult
def detect_files(paths: list[str]) -> list[DetectionResult]
def group_by_company(results: list[DetectionResult]) -> dict[str, list[DetectionResult]]
```

### Detection Logic

#### Excel Files
1. Open workbook with `openpyxl.load_workbook(read_only=True)`.
2. Check sheet names:
   - `"1.1.PO_Client"` → `format_id="excel_zalando"`, company=`["Zalando"]`, confidence=`"high"`
   - `"1.PO_Client"` → `format_id="excel_zalando"`, company=`["Zalando"]`, confidence=`"medium"`
   - No match → `format_id="excel_unknown"`, company=`[]`, confidence=`"low"`

#### PDF Files
1. Extract full text with `read_pdf_text()`.
2. Pass to `detect_format()` → `format_id`.
3. Look up companies via `companies_for_format(format_id)`.
4. Run `_narrow_pdf_company()` keyword scan:
   - DKNY keywords: `["DKNY", "DONNA KARAN", "DKI"]`
   - GIII keywords: `["G-III", "GIII", "G III APPAREL"]`
   - Winning company (most keyword hits) moves to front of list.
5. Return confidence=`"high"` if exactly one company matched, else `"medium"`.

### Confidence Badges (UI)

| Confidence | Badge |
|------------|-------|
| high | 🟢 |
| medium | 🟡 |
| low | 🔴 |

### group_by_company

```python
# Returns dict mapping company name → list of DetectionResults
# Files with no company go under key "Unknown"
groups = group_by_company(results)
for company, file_results in groups.items():
    print(company, [r.filename for r in file_results])
```

---

## 9. Buy Plan Exporters

### 9.1 Zalando Buy Plan (Template)

**File:** `po_extractor/exporters/hhp_buyplan_export.py`

```python
def export_hhp_buyplan(
    df: pd.DataFrame,
    output_dir: str,
    photo_map: dict[str, bytes] | None = None,
) -> str:
    """Generate Zalando_BuyPlan.xlsx. Returns the output file path."""
```

#### Layout Constants

```python
SIZES           = ["XS", "S", "M", "L", "XL", "XXL"]
HEADER_ROW      = 7          # Row where size labels are written
DATA_START_ROW  = 8          # First data row
SIZE_COL_START  = 10         # Column J (1-indexed)
TOTAL_LABEL_COL = 16         # Column P — label "Total"
TOTAL_FORMULA_COL = 17       # Column Q — SUM formula
FACTORY_DATE_COL  = 18       # Column R — factory date
GRAND_TOTAL_CELL  = "Q5"     # Grand total for the entire style sheet
```

#### Index Sheet

The first sheet is an Index with columns:

| Column | Content |
|--------|---------|
| A | Row number |
| B | 款号 (Style number, hyperlinked to style sheet) |
| C | 客户品号 (Client style number) |
| D | 面料_面料 (Fabric name) |
| E | 面料_面料_编号 (Fabric code) |
| F | 总数量合计 (Total units) |
| G | 入厂时间 (Factory arrival date) |
| H–R | Production planning columns (11 columns) |

#### Per-Style Sheet Layout

Each style gets its own sheet named by the style number.

```
Row 1:  L1 = factory date
Row 2–4: B2:E4 = fabric block (4 rows × 4 cols)
         J3:L5 = Photo1 (embedded image, 3×3 cell merge)
         M3:O5 = Photo2 (embedded image, 3×3 cell merge)
Row 5:  Q5 = grand total (SUM of all Q column data cells)
Row 7:  Size headers at columns J onwards (XS, S, M, L, XL, XXL, Total)
Row 8+: Data rows — one per (PO Number, Config SKU, Color)
```

#### Photo Resolution

Photos are resolved in this priority order:

1. `photo_map[style_key]` — bytes keyed by style number (from uploaded ZIP)
2. `photo_map[filename]` — filename match inside ZIP
3. Value in `Photo1` / `Photo2` column of DataFrame — local disk path (server-side only)

If no photo is found, the image cell is left blank (no error raised).

#### Repeat Orders on Style Sheets

Rows with `_repeat_order=True` are highlighted in yellow (`FFFF00`) to draw attention.

### 9.2 Zalando Template_P (Fabric Plan)

**File:** `po_extractor/exporters/hhp_template_p_export.py`

```python
def export_hhp_template_p(
    df: pd.DataFrame,
    output_dir: str,
) -> list[tuple[str, bytes]]:
    """Generate one workbook per fabric code.
    Returns list of (filename, bytes) tuples for download."""
```

#### Grouping Logic

- Group entire DataFrame by `面料_面料_编号` (Fabric1_Code).
- Styles with empty/null fabric code go into `"UNKNOWN"` group.
- One output file per group: `Zalando_面料_{fabric_key}.xlsx`

#### Per-Style Sheet Layout (within each fabric workbook)

```
Row 1:  Merged header: "Colour" | Size labels (XS, S, M, L, XL, XXL) | Total
Row 2:  Individual size column labels
Row 3+: One row per colour:  ColorDesc | qty per size | SUM formula
Last:   Total row — SUM of each size column
```

### 9.3 Cross-Comparison Sheet

After generating both Template and Template_P, a cross-comparison sheet is appended to the main buy plan workbook.

| Column | Content |
|--------|---------|
| A | Style number |
| B | Template total (from buy plan sheet) |
| C | Template_P total (sum across all fabric workbooks) |
| D | Match? (YES / NO, conditional formatting) |

---

## 10. PO Store (SQLite)

**File:** `po_extractor/store/po_store.py`

### Database Location

```python
DB_PATH = os.path.join(os.path.dirname(__file__), "po_history.db")
```

### Tables

#### `po_metadata`

| Column | Type | Notes |
|--------|------|-------|
| po_number | TEXT PRIMARY KEY | |
| style | TEXT | |
| po_date | TEXT | |
| vendor | TEXT | |
| factory | TEXT | |
| country_of_origin | TEXT | |
| buyer | TEXT | |
| ship_to | TEXT | |
| division | TEXT | |
| season | TEXT | |
| factory_ship_date | TEXT | |
| source_format | TEXT | "infor_nexus" / "legacy_giii" / "excel_zalando" |
| file_name | TEXT | |
| created_at | TEXT | ISO-8601 timestamp |
| company | TEXT | Company name |

#### `po_size_rows`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PRIMARY KEY | |
| po_number | TEXT | FK → po_metadata |
| style | TEXT | |
| color | TEXT | |
| size | TEXT | |
| units | INTEGER | |
| upc | TEXT | |

#### `po_version_history`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PRIMARY KEY | |
| po_number | TEXT | |
| version | TEXT | |
| total_units | INTEGER | |
| snapshot_json | TEXT | Full metadata JSON |
| archived_at | TEXT | ISO-8601 timestamp |

### Key Functions

```python
def save_many_checked(pos: list[POData]) -> list[tuple[str, str, str]]:
    """Save POs with conflict detection.
    Returns list of (po_number, status, diff) where
    status ∈ {"new", "duplicate", "updated", "skipped"}."""

def list_pos(companies: list[str] | None = None) -> list[dict]
def load_size_rows(po_numbers: list[str]) -> list[SizeRow]
def load_metadata(po_numbers: list[str]) -> list[POMetadata]
```

### Conflict Detection

When a PO number already exists in the store:
1. Compare `version` string (if available).
2. Compare total units.
3. If both match → `"duplicate"` (skip).
4. If different → `"updated"` (archive old record to `po_version_history`, save new).

---

## 11. Streamlit Web UI

**File:** `app.py`

### Startup

```python
import streamlit as st
from auth.companies import ensure_defaults_seeded

ensure_defaults_seeded()  # Must be called before any company lookups

st.set_page_config(page_title="PO Automation", layout="wide")
```

### Session State Keys

| Key | Type | Purpose |
|-----|------|---------|
| `authenticated` | bool | Login state |
| `username` | str | Current user |
| `role` | str | "admin" or "user" |
| `user_companies` | list[str] | Accessible companies |
| `detection_results` | list[DetectionResult] | Results from last upload scan |
| `confirmed_assignments` | dict[str, str] | filename → confirmed company |
| `processing_complete` | bool | Flag to show download section |
| `export_data` | dict | Company → export bytes |

### Main Navigation

```python
if not st.session_state.authenticated:
    _show_login()
else:
    tab_upload, tab_history = st.tabs(["📤 Upload & Process", "📚 PO History"])
    with tab_upload:
        _show_smart_upload_tab()
    with tab_history:
        _show_history_tab()

    if st.session_state.role == "admin":
        with st.expander("⚙️ Admin Panel"):
            admin_tab_users, admin_tab_companies = st.tabs(["Users", "Companies"])
            with admin_tab_users:
                _show_user_admin()
            with admin_tab_companies:
                _show_company_admin()
```

### Upload & Process Tab Flow

**Function:** `_show_smart_upload_tab()`

1. **Company filter dropdown**
   ```python
   from auth.companies import list_company_names
   company_options = ["All"] + list_company_names()
   selected_company = st.selectbox("Filter by company", company_options)
   ```

2. **File uploader**
   ```python
   uploaded_files = st.file_uploader(
       "Upload PO files",
       type=["pdf", "xlsx", "xlsm", "xls"],
       accept_multiple_files=True,
   )
   photo_zip = st.file_uploader("Upload photos (ZIP)", type=["zip"])
   ```

3. **Auto-detect button**  
   Save uploaded files to temp dir → call `detect_files(paths)` → display results table.

4. **Detection results table**
   ```
   | Filename | Type | Format | Detected Company | Confidence | Override |
   |----------|------|--------|------------------|------------|---------- |
   | a.xlsx   | Excel| excel_zalando | Zalando   | 🟢 High   | [dropdown] |
   | b.pdf    | PDF  | infor_nexus   | GIII      | 🟡 Medium | [dropdown] |
   ```

5. **Mismatch warning**  
   If user's selected company filter ≠ detected company:
   ```
   ⚠️ File "b.pdf" was detected as GIII but you selected DKNY.
   [Confirm DKNY] [Keep GIII] [Cancel]
   ```

6. **Process button**  
   Calls `_run_smart_processing()` with confirmed assignments.

### Processing Function

**Function:** `_run_smart_processing(files, confirmed_assignments, photo_zip)`

```python
groups = group_by_company(detection_results)

for company, file_results in groups.items():
    paths = [r.temp_path for r in file_results]
    if company in ("GIII", "DKNY"):
        _process_pdf_group(company, paths)
    elif company == "Zalando":
        _process_excel_group(paths, photo_zip)
```

**`_process_excel_group(paths, photo_zip)`:**

```python
from po_extractor.parsers.client_excel_multi import combine_excel_files
from po_extractor.exporters.hhp_buyplan_export import export_hhp_buyplan
from po_extractor.exporters.hhp_template_p_export import export_hhp_template_p

result = combine_excel_files(paths)
photo_map = _extract_photos(photo_zip)  # dict[name, bytes]

buyplan_path = export_hhp_buyplan(result.df, tmpdir, photo_map)
template_p_files = export_hhp_template_p(result.df, tmpdir)

if result.repeat_orders:
    st.warning(f"⚠️ Repeat orders detected for styles: "
               f"{', '.join(result.repeat_orders.keys())}")
```

### Download Section

**Function:** `_show_smart_downloads()`

For each processed company, show appropriate download buttons:

| Company | Download Buttons |
|---------|-----------------|
| GIII / DKNY | "Download Buy Plan", "Download Size Summary" |
| Zalando | "Download Buy Plan (Template)", "Download Fabric Plans (Template_P)", "Download Cross-Comparison" |

### Admin Panel — Companies Tab

**Function:** `_show_company_admin()`

- List all companies with active/inactive toggle.
- Edit form: display name, file types (multi-select), formats (text input), sheet name, colour picker, active flag.
- Add new company form.
- Delete button (with confirmation).

All changes call `upsert_company()` or `delete_company()` from `auth.companies`.

---

## 12. Column Mapping Schema

**File:** `po_extractor/utils/client_template.py`

The system uses 33 internal column names grouped into 5 categories.

### Schema Definition

```python
# Each tuple: (internal_header, example_client_header, group, notes)
SCHEMA = [
    # PO Group
    ("Purchase Order Number",         "PO番号",              "PO",    "Unique PO identifier"),
    ("PO Issue Date",                  "発行日",              "PO",    ""),
    ("Buyer",                          "バイヤー",             "PO",    ""),
    ("Ship To",                        "出荷先",               "PO",    ""),
    ("Season",                         "シーズン",             "PO",    ""),
    ("Division",                       "ディビジョン",          "PO",    ""),
    ("Factory Ship Date",              "工場出荷日",            "PO",    ""),
    ("Export Date",                    "輸出日",               "PO",    ""),

    # Size Group
    ("Main Supplier Config SKU",       "メインSKU",            "Size",  "Style number"),
    ("Config SKU",                     "ConfigSKU",           "Size",  "Full SKU with colour/size"),
    ("Main Supplier Color Description","カラー説明",            "Size",  ""),
    ("Color Code",                     "カラーコード",          "Size",  ""),
    ("XS",                             "XS",                  "Size",  "Units"),
    ("S",                              "S",                   "Size",  "Units"),
    ("M",                              "M",                   "Size",  "Units"),
    ("L",                              "L",                   "Size",  "Units"),
    ("XL",                             "XL",                  "Size",  "Units"),
    ("XXL",                            "XXL",                 "Size",  "Units"),
    ("Total Units",                    "合計数量",              "Size",  "SUM of sizes"),

    # Internal Group
    ("UPC",                            "UPC",                 "内部",  "Barcode"),
    ("Unit Price",                     "単価",                 "内部",  ""),
    ("Currency",                       "通貨",                 "内部",  ""),
    ("Country of Origin",              "原産国",               "内部",  ""),

    # Fabric Group
    ("面料_面料",                        "面料名称",             "面料",  "Fabric name"),
    ("面料_面料_编号",                    "面料コード",           "面料",  "Fabric code (groups Template_P)"),
    ("面料_供应商",                       "面料サプライヤー",      "面料",  ""),
    ("面料_成分",                        "面料成分",             "面料",  "Fabric composition"),
    ("面料_克重",                        "面料克重",             "面料",  "Fabric weight"),
    ("面料_门幅",                        "面料幅",               "面料",  "Fabric width"),

    # Photo Group
    ("Photo1",                         "写真1パス",            "Photo", "Local path or ZIP filename"),
    ("Photo2",                         "写真2パス",            "Photo", "Local path or ZIP filename"),
    ("Photo1_Caption",                 "写真1キャプション",     "Photo", ""),
    ("Photo2_Caption",                 "写真2キャプション",     "Photo", ""),
]
```

### Zalando Column Aliases

```python
CLIENT_ALIASES = {
    "Zalando": {
        "Purchase Order Number":          "Purchase Order Number",
        "Main Supplier Config SKU":       "Main Supplier Config SKU",
        "Main Supplier Color Description":"Main Supplier Color Description",
        "XS": "XS", "S": "S", "M": "M", "L": "L", "XL": "XL", "XXL": "XXL",
        "面料_面料":      "Fabric1",
        "面料_面料_编号": "Fabric1_Code",
        "面料_供应商":    "Fabric1_Supplier",
        "面料_成分":     "Fabric1_Content",
        "面料_克重":     "Fabric1_Weight",
        "面料_门幅":     "Fabric1_Width",
    }
}
```

### Template Generator CLI

```bash
# Generate blank mapping template
python -m po_extractor.utils.client_template --output template.xlsx

# Generate template pre-filled with Zalando column names
python -m po_extractor.utils.client_template --output zalando_template.xlsx --client Zalando

# Add mapping sheet to an existing workbook
python -m po_extractor.utils.client_template --inject existing_workbook.xlsx --client Zalando
```

The generated template has:
- Row 1: Internal header names (colour-coded by group)
- Row 2: Client-specific aliases (if `--client` specified) or blank for manual fill
- Row 3: Notes/descriptions
- Group colour coding: PO=blue, Size=green, 内部=grey, 面料=orange, Photo=purple

---

## 13. Setup & Deployment

### Prerequisites

- Python 3.11 or later
- Windows 10/11 or macOS/Linux
- ~200 MB disk space

### Installation

```bash
# Clone or copy the repository
cd PO_Automation_GIII

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### First Run

```bash
streamlit run app.py
```

On first run:
- `auth/users.json` is created with a default admin account (`admin` / `admin123`). **Change the password immediately.**
- `auth/companies.json` is seeded with GIII, DKNY, and Zalando.
- `po_extractor/store/po_history.db` is created (SQLite).

### Changing the Admin Password

Log in as `admin`, go to Admin Panel → Users → select `admin` → Change Password.

### Adding Users

Admin Panel → Users → Add User form:
- Username
- Password
- Role: `user` (restricted) or `admin` (full access)
- Companies: select from registry (empty = all, for admins)

### Production Deployment

For internal network deployment:

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Access at `http://<server-ip>:8501`

For HTTPS, place behind an nginx reverse proxy with an SSL certificate.

### Environment Variables (optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `PO_DB_PATH` | `po_extractor/store/po_history.db` | Override DB location |
| `PO_COMPANIES_FILE` | `auth/companies.json` | Override company registry location |
| `PO_USERS_FILE` | `auth/users.json` | Override users file location |

---

## 14. Adding a New Client

Follow these steps to add a new client to the system.

### Step 1 — Register the Company

```python
from auth.companies import upsert_company

upsert_company(
    name="NewClient",
    display_name="New Client Ltd",
    file_types=["excel"],          # or ["pdf"] or ["pdf", "excel"]
    formats=["excel_newclient"],   # new format_id you'll define
    excel_sheet="Sheet1",          # for Excel clients: sheet to detect
    color="#123456",
    active=True,
)
```

Or add to `_DEFAULTS` in `auth/companies.py` for permanent seeding.

### Step 2 — Add Format Detection

**For Excel clients** — add sheet name check to `_detect_excel()` in `po_extractor/detectors/file_detector.py`:

```python
if "YourSheetName" in sheet_set:
    return DetectionResult(
        filename=filename, file_type="excel", format_id="excel_newclient",
        companies=["NewClient"], confidence="high",
        detail="Found sheet 'YourSheetName' — NewClient format.",
    )
```

**For PDF clients** — add keyword to `_narrow_pdf_company()`:

```python
keywords["NewClient"] = ["NEW CLIENT", "NEWCO", "NCL"]
```

And add format to `FORMAT_TO_COMPANIES`:

```python
FORMAT_TO_COMPANIES["infor_nexus"] = ["GIII", "DKNY", "NewClient"]
```

### Step 3 — Build a Parser

If the client uses the two-row header Excel format:

```python
# Works out of the box — just pass sheet_name
from po_extractor.parsers.client_excel import parse_client_excel_to_df
df = parse_client_excel_to_df(path, sheet_name="YourSheetName")
```

If the client uses a different structure, create `po_extractor/parsers/newclient_excel.py` with:

```python
def parse_newclient_excel(path: str) -> pd.DataFrame:
    # Custom parsing logic
    ...
```

### Step 4 — Build an Exporter (if needed)

If the output format differs from Zalando's buy plan layout, create:

```
po_extractor/exporters/newclient_export.py

def export_newclient(df: pd.DataFrame, output_dir: str) -> str:
    # Build the output workbook
    ...
```

### Step 5 — Wire into the UI

In `app.py`, add routing in `_run_smart_processing()`:

```python
elif company == "NewClient":
    _process_newclient_group(paths)
```

And add download button in `_show_smart_downloads()`:

```python
if company == "NewClient":
    st.download_button("Download NewClient Report", data=..., file_name="...")
```

### Step 6 — Update Column Mapping Template

Add client aliases to `CLIENT_ALIASES` in `po_extractor/utils/client_template.py`:

```python
CLIENT_ALIASES["NewClient"] = {
    "Purchase Order Number": "PO Ref",
    "Main Supplier Config SKU": "Style Code",
    # ... rest of mappings
}
```

---

## Appendix A — VBA to Python Reference

The original VBA automation (`Production_M` module) maps to Python as follows:

| VBA Function | Python Equivalent |
|--------------|-------------------|
| `CreateBuyPlan_template2()` | `export_hhp_buyplan()` in `hhp_buyplan_export.py` |
| `ProcessSKU()` | Style-level loop in `export_hhp_buyplan()` |
| `PopulateFabricDetails()` | Fabric block writing in `export_hhp_buyplan()` |
| `InsertPhotos()` | Photo resolution + `add_image()` in `export_hhp_buyplan()` |
| `ProcessDataGrouping()` | `combine_excel_files()` in `client_excel_multi.py` |
| `CreateZalandoWorkbooks()` | `export_hhp_template_p()` in `hhp_template_p_export.py` |
| `CreateCrossComparisonSheet()` | Cross-comparison logic in `export_hhp_buyplan.py` |
| `GetColumnMapping()` | `_FIELD_MAP` dict in `client_excel.py` |
| `BuildDictionary()` | `parse_client_excel_to_df()` in `client_excel.py` |

**Key VBA constants and their Python equivalents:**

```
VBA: SOURCE_SHEET_NAME = "1.1.PO_Client"
Python: sheet_name="1.1.PO_Client" (default parameter)

VBA: HEADER_ROW = 1
VBA: DATA_START_ROW = HEADER_ROW + 2  ' = 3
Python: rows[1] = internal headers, rows[2:] = data

VBA: Array("XS","S","M","L","XL","XXL")
Python: SIZE_COLUMNS = ["XS", "S", "M", "L", "XL", "XXL"]
```

---

## Appendix B — Troubleshooting

### "openpyxl not installed"
```bash
pip install openpyxl
```

### "ModuleNotFoundError: No module named 'fitz'"
```bash
pip install pymupdf
```

### UnicodeDecodeError reading Python files
All source files must be saved as UTF-8. Open with `encoding='utf-8'` parameter.

### Excel file detected as "unknown"
Check that the sheet name exactly matches (case-sensitive). Open the file and verify the sheet tab name is `1.1.PO_Client`.

### Photos not appearing in buy plan
- Confirm the ZIP contains files named `{StyleNumber}.jpg` (or .png).
- Or populate the `Photo1` column in the Excel file with the filename (not full path) of the image in the ZIP.

### Streamlit shows blank screen after login
Clear Streamlit cache: `st.cache_data.clear()` or restart the app.

### SQLite "database is locked"
Only one Streamlit process should run at a time against the same DB file. Use `--server.port` to run multiple instances with different DB paths.

---

*End of Implementation Guide*
