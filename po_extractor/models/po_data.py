"""Unified data model for PO extraction."""
from dataclasses import dataclass, field, asdict


@dataclass
class SizeRow:
    """One row per PO / Style / Color / Size."""
    po_number: str
    style: str
    color: str
    size: str
    units: int
    upc: str


@dataclass
class POMetadata:
    po_number: str | None = None
    style: str | None = None
    po_date: str | None = None
    vendor: str | None = None
    issued_by: str | None = None
    factory: str | None = None
    country_of_origin: str | None = None
    vendor_country: str | None = None
    hanger: str | None = None
    source_format: str | None = None
    file_name: str | None = None
    file_path: str | None = None

    # Infor Nexus extended (blank for legacy)
    buyer: str | None = None
    ship_to: str | None = None
    destination_code: str | None = None
    division: str | None = None
    division_code: str | None = None
    division_name: str | None = None
    season: str | None = None
    incoterm: str | None = None
    origin_port: str | None = None
    payment_terms: str | None = None
    discount: str | None = None
    approval_status: str | None = None
    customer: str | None = None
    dim: str | None = None
    packaging: str | None = None
    style_description: str | None = None
    style_group: str | None = None
    unit_cost: str | None = None
    line_extended_cost: str | None = None
    factory_ship_date: str | None = None
    xport_date: str | None = None
    ratio: str | None = None
    version: str | None = None
    extracted_at: str | None = None
    company: str | None = None

    # --- Traceability fields ---
    parser_version: str | None = None
    parse_confidence: int | None = None          # 0–100
    validation_status: str | None = None        # "valid" | "warning" | "exception"
    revision_reason: str | None = None          # "new" | "updated" | "manual_correction" | None
    source_file_hash: str | None = None         # MD5 of original source file
    processed_by: str | None = None             # username who triggered processing

    # --- Reserved for future quotation-module integration ---
    external_quote_id: str | None = None        # reserved for future quotation-module integration
    source_module: str | None = None            # reserved for future quotation-module integration
    integration_status: str | None = None       # reserved for future quotation-module integration


@dataclass
class POData:
    metadata: POMetadata
    size_rows: list = field(default_factory=list)
    summary_rows: list = field(default_factory=list)  # [po, style, color, hanger]
