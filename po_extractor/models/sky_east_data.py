from dataclasses import dataclass, field
from .fabric_part import FabricPart
from ..utils.style_norm import normalize_style_no


@dataclass
class SkyEastItem:
    pc_no: str
    zalando_po: str            # e.g. PO2276067C
    style: str                 # e.g. S25DDR2036 (Main Supplier Config SKU)
    config_sku: str            # e.g. AN621C2EC-Q11
    article_name: str
    brand: str                 # Anna Field / About You
    color_name: str
    colour_code: str
    launch_date: str
    fabric_item_no: str        # primary HHN (fabric_parts[0].hhn_no) — kept for compat
    fabrication: str           # human-readable multi-fabric display string
    contract_no: str
    sizes: dict                # {"XS": 49, "S": 143, "M": 214, "L": 173, "XL": 121, "2XL": 0}
    total_qty: int
    fob_usd: float
    total_cost_usd: float
    ex_fty_date: str | None = None
    picture_id: str | None = None          # DISPIMG ID extracted from formula
    fabric_parts: list = field(default_factory=list)  # list[FabricPart] — structured fabric data
    return_label: str = "NA"               # "Yes" / "No" / "NA" — from the client PO's Return Label column

    def __post_init__(self):
        # "/" in a style is stored as "_" (TP3267-3/4SLV -> TP3267-3_4SLV) so
        # mapping/photo/search lookups agree on one spelling. Only the style:
        # config_sku, colours and fabric codes keep their slashes.
        self.style = normalize_style_no(self.style)


@dataclass
class SkyEastContract:
    pc_no: str
    pc_date: str | None = None
    buyer: str | None = None
    seller: str | None = None
    currency: str | None = None
    payment_terms: str | None = None
    trade_term: str | None = None
    items: list = field(default_factory=list)
    source_file: str | None = None
    file_path: str | None = None
    extracted_at: str | None = None
    parser_version: str | None = None
    parse_confidence: int | None = None
    validation_status: str | None = None   # "valid" | "warning" | "exception" — same scale as POMetadata
    source_file_hash: str | None = None
    processed_by: str | None = None
    # Rows dropped for having 0 total units — {"row": int, "style": str, "po": str}.
    # Surfaced in the upload log so a blanked-out/cancelled line isn't silently lost.
    skipped_zero_qty: list = field(default_factory=list)
