"""
Standard output column schema for all export files.

GOLDEN RULE
-----------
This file controls ONLY output column names (Excel downloads, reports).
Input parsing is NOT changed — each parser maps client-specific headers
to internal DB field names independently.

Structure of OUTPUT_FIELDS
---------------------------
Each entry is a dict with:
  db_col       : str   — internal DB / DataFrame column name (source of truth)
  label        : str   — standard output heading used in ALL export files
  client_alias : dict  — optional per-client row-1 header for dual-header files
                         key = client code, value = client's own column name
  dtype        : str   — "text" | "int" | "float" | "date"
  required     : bool  — must appear in every standard output
  notes        : str   — free-text explanation

Client codes used in client_alias
----------------------------------
  "sky_east"  — Sky East International (Zalando buy)
  "infor"     — Infor Nexus / standard PDF PO
  "legacy"    — Legacy GIII Excel POs
"""

from __future__ import annotations

OUTPUT_FIELDS: list[dict] = [
    # ── Identity ──────────────────────────────────────────────────────────────
    {
        "db_col":  "company",
        "label":   "Company",
        "client_alias": {
            "sky_east": "Brand",
            "infor":    "Company",
            "legacy":   "Company",
        },
        "dtype":    "text",
        "required": True,
        "notes":    "Trading company or brand name.",
    },
    {
        "db_col":  "pc_no",
        "label":   "Contract No.",
        "client_alias": {
            "sky_east": "PC No.",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "Sky East purchase contract number. Not present in other clients.",
    },
    {
        "db_col":  "po_number",
        "label":   "PO No.",
        "client_alias": {
            "sky_east": "Purchase Order Number",
            "infor":    "PO Number",
            "legacy":   "PO Number",
        },
        "dtype":    "text",
        "required": True,
        "notes":    "Client-issued purchase order number.",
    },
    {
        "db_col":  "config_sku",
        "label":   "Config SKU",
        "client_alias": {
            "sky_east": "Config SKU",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "Zalando-specific product configuration code.",
    },

    # ── Product ───────────────────────────────────────────────────────────────
    {
        "db_col":  "style",
        "label":   "Style No.",
        "client_alias": {
            "sky_east": "Main Supplier Config SKU",
            "infor":    "Style",
            "legacy":   "Style",
        },
        "dtype":    "text",
        "required": True,
        "notes":    "HHN / supplier style number.",
    },
    {
        "db_col":  "article_name",
        "label":   "Article Name",
        "client_alias": {
            "sky_east": "Supplier Article Name",
            "infor":    "Style Description",
            "legacy":   "Description",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "Product description / article name from client.",
    },
    {
        "db_col":  "brand",
        "label":   "Brand",
        "client_alias": {
            "sky_east": "Brand",
            "infor":    "Division Name",
            "legacy":   "Brand",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "End-consumer brand (e.g. Anna Field, Only & Sons).",
    },
    {
        "db_col":  "color_name",
        "label":   "Color",
        "client_alias": {
            "sky_east": "Main Supplier Color Description",
            "infor":    "Color",
            "legacy":   "Color",
        },
        "dtype":    "text",
        "required": True,
        "notes":    "Color description as supplied by client.",
    },
    {
        "db_col":  "colour_code",
        "label":   "Color Code",
        "client_alias": {
            "sky_east": "Colour Code",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "Numeric or alphanumeric color code (client-specific).",
    },
    {
        "db_col":  "launch_date",
        "label":   "Launch Date",
        "client_alias": {
            "sky_east": "Launch Date",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "Target market launch / sell-in month.",
    },

    # ── Sizes ─────────────────────────────────────────────────────────────────
    {
        "db_col":  "xs",
        "label":   "XS",
        "client_alias": {"sky_east": "XS", "infor": "XS", "legacy": "XS"},
        "dtype":    "int",
        "required": False,
        "notes":    "Units ordered in size XS.",
    },
    {
        "db_col":  "s",
        "label":   "S",
        "client_alias": {"sky_east": "S", "infor": "S", "legacy": "S"},
        "dtype":    "int",
        "required": False,
        "notes":    "Units ordered in size S.",
    },
    {
        "db_col":  "m",
        "label":   "M",
        "client_alias": {"sky_east": "M", "infor": "M", "legacy": "M"},
        "dtype":    "int",
        "required": False,
        "notes":    "Units ordered in size M.",
    },
    {
        "db_col":  "l",
        "label":   "L",
        "client_alias": {"sky_east": "L", "infor": "L", "legacy": "L"},
        "dtype":    "int",
        "required": False,
        "notes":    "Units ordered in size L.",
    },
    {
        "db_col":  "xl",
        "label":   "XL",
        "client_alias": {"sky_east": "XL", "infor": "XL", "legacy": "XL"},
        "dtype":    "int",
        "required": False,
        "notes":    "Units ordered in size XL.",
    },
    {
        "db_col":  "xxl",
        "label":   "XXL",
        "client_alias": {"sky_east": "2XL", "infor": "XXL", "legacy": "XXL"},
        "dtype":    "int",
        "required": False,
        "notes":    "Units ordered in size XXL. Sky East uses '2XL' as their label.",
    },
    {
        "db_col":  "total_qty",
        "label":   "Total Qty",
        "client_alias": {
            "sky_east": "TOTAL QUANTITY",
            "infor":    "Total Units",
            "legacy":   "Total Qty",
        },
        "dtype":    "int",
        "required": True,
        "notes":    "Total units across all sizes for this line.",
    },

    # ── Logistics ─────────────────────────────────────────────────────────────
    {
        "db_col":  "country_of_origin",
        "label":   "COO",
        "client_alias": {
            "infor":  "Country of Origin",
            "legacy": "COO",
        },
        "dtype":    "text",
        "required": True,
        "notes":    "Country of manufacture. Not supplied by Sky East in PO file.",
    },
    {
        "db_col":  "factory",
        "label":   "Factory",
        "client_alias": {
            "infor":  "Factory",
            "legacy": "Factory",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "Production factory name. Not present in Sky East PO files.",
    },
    {
        "db_col":  "ex_fty_date",
        "label":   "Ex-Factory Date",
        "client_alias": {
            "sky_east": "EX-FTY",
            "infor":    "Factory Ship Date",
            "legacy":   "X-Port Date",
        },
        "dtype":    "date",
        "required": True,
        "notes":    "Date goods leave the factory. Each client uses a different name.",
    },
    {
        "db_col":  "trade_term",
        "label":   "Trade Terms",
        "client_alias": {
            "sky_east": "Trade Term",
            "infor":    "Incoterm",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "Incoterms (e.g. FOB, CIF).",
    },

    # ── Financials ────────────────────────────────────────────────────────────
    {
        "db_col":  "fob_usd",
        "label":   "FOB (USD)",
        "client_alias": {
            "sky_east": "FOB\nUSD",
            "infor":    "Unit Cost",
            "legacy":   "FOB USD",
        },
        "dtype":    "float",
        "required": False,
        "notes":    "Unit FOB price in USD.",
    },
    {
        "db_col":  "total_cost_usd",
        "label":   "Total Cost (USD)",
        "client_alias": {
            "sky_east": "Total Cost\nUSD",
            "infor":    "Line Extended Cost",
            "legacy":   "Total Cost USD",
        },
        "dtype":    "float",
        "required": False,
        "notes":    "Total line value = FOB × Total Qty.",
    },

    # ── Fabric / Compliance ───────────────────────────────────────────────────
    {
        "db_col":  "fabric_item_no",
        "label":   "Fabric No.",
        "client_alias": {
            "sky_east": "Fabric Item Number",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "HHN internal fabric reference number.",
    },
    {
        "db_col":  "fabric_display_key",
        "label":   "Fabric Code",
        "client_alias": {},
        "dtype":    "text",
        "required": False,
        "notes":    "Fabric master display key (from Fabric DB).",
    },
    {
        "db_col":  "composition_en",
        "label":   "Composition",
        "client_alias": {
            "sky_east": "国标_大身_成分",
        },
        "dtype":    "text",
        "required": False,
        "notes":    "Fibre composition in English (from Fabric DB).",
    },
    {
        "db_col":  "shrinkage_rate",
        "label":   "Shrinkage Rate",
        "client_alias": {
            "sky_east": "国标_大身_烫缩",
        },
        "dtype":    "float",
        "required": False,
        "notes":    "Shrinkage % from Fabric DB.",
    },
    {
        "db_col":  "short_rate",
        "label":   "Short Rate",
        "client_alias": {
            "sky_east": "国标_大身_短码",
        },
        "dtype":    "float",
        "required": False,
        "notes":    "Short-size rate % from Fabric DB.",
    },

    # ── Traceability ──────────────────────────────────────────────────────────
    {
        "db_col":  "extracted_at",
        "label":   "Extracted At",
        "client_alias": {},
        "dtype":    "date",
        "required": False,
        "notes":    "Timestamp when this record was extracted by the system.",
    },
    {
        "db_col":  "source_file",
        "label":   "Source File",
        "client_alias": {},
        "dtype":    "text",
        "required": False,
        "notes":    "Original filename from which this PO was parsed.",
    },
]

# ── Convenience lookups ────────────────────────────────────────────────────────

# db_col → standard output label
LABEL: dict[str, str] = {f["db_col"]: f["label"] for f in OUTPUT_FIELDS}

# db_col → client alias  (returns "" if no alias for that client)
def client_label(db_col: str, client: str) -> str:
    """Return the client's own column name for db_col, or the standard label."""
    for f in OUTPUT_FIELDS:
        if f["db_col"] == db_col:
            return f["client_alias"].get(client, f["label"])
    return db_col

# Ordered list of required db_cols for a minimal standard output
REQUIRED_COLS: list[str] = [f["db_col"] for f in OUTPUT_FIELDS if f["required"]]

# Full ordered list of db_cols
ALL_COLS: list[str] = [f["db_col"] for f in OUTPUT_FIELDS]
