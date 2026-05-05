# PO Extractor — Setup & Run Guide

## Requirements

- Python 3.10 or later
- pip

## Installation

```bash
pip install -r requirements.txt
```

## First-time setup: create user accounts

Run the setup script once before starting the app:

```bash
python setup_users.py
```

Follow the prompts to create up to 3 user accounts (username + password).  
Accounts are stored in `auth/users.json` with bcrypt-hashed passwords.

You can re-run `setup_users.py` at any time to add or reset a user.

## Running the app

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501** in your browser.

## Usage

1. **Sign in** with a username and password created in the setup step.
2. **Upload** one or more PO PDF files (Infor Nexus or Legacy G-III format).
3. *(Optional)* Check **Mask prices in PDFs** to generate price-redacted copies.
4. Click **Extract & Generate Buy Plan**.
5. Download outputs:
   - **Buy Plan (.xlsx)** — pivoted size/color table per style
   - **Extracted Data (.zip)** — 3 CSVs (by size/color, summary, metadata)
   - **Masked PDFs (.zip)** — price-redacted PDF copies (if option was checked)

## File structure

```
PO_Automation_GIII/
├── app.py                   # Streamlit UI
├── setup_users.py           # User account creation script
├── requirements.txt
├── auth/
│   ├── users.py             # bcrypt user management
│   ├── license.py           # License stub (machine lock pending)
│   └── users.json           # Created on first run of setup_users.py
└── po_extractor/
    ├── parsers/             # Infor Nexus + Legacy G-III parsers
    ├── exporters/           # Buy plan Excel + CSV exporters
    ├── utils/               # Price masking utility
    ├── models/              # POData dataclasses
    ├── detectors/           # Format auto-detection
    └── main.py              # CLI entry point (optional)
```

## CLI usage (optional)

```bash
python -m po_extractor.main --input /path/to/pdfs --output /path/to/output
python -m po_extractor.main --input /path/to/pdfs --output /path/to/output --mask-prices
```
