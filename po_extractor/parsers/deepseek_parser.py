"""DeepSeek AI-powered PO parser.

Sends the raw PDF text to the DeepSeek Chat API and asks it to return a
structured JSON object with all PO fields.  Falls back to the regex parser
on API errors so the extraction pipeline never silently fails.

DeepSeek API is OpenAI-compatible; the openai SDK is used with a custom
base_url pointing at api.deepseek.com.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from ..config import FORMAT_INFOR_NEXUS, FORMAT_LEGACY
from ..models import POData, POMetadata, SizeRow
from ..utils.deepseek_client import chat_kwargs

PARSER_VERSION = "ds-1.0"

_SYSTEM_PROMPT = """\
You are a purchase order data extraction assistant.
Extract every key field from the PO text provided and return ONLY a valid JSON
object — no markdown, no explanation, no extra text.

Required fields (use null if not found):
  po_number, issue_date, version,
  buyer, seller, factory, factory_code,
  ship_to, destination_code, end_customer,
  incoterm, origin_port, payment_terms, discount,
  approval_status, country_of_origin,
  division_code, division_name, season, issued_by,
  style, style_description, style_group,
  unit_cost, total_extended_cost, total_quantity,
  xport_date, factory_ship_date,
  size_rows: [
    { size, upc, quantity, color }
  ]

Rules:
- All values are strings unless noted.
- size_rows is a list of objects; quantity is an integer.
- color is the item colour for that size row (null if the PO shows none).
- discount should include the % sign if present.
- xport_date and factory_ship_date are YYYY-MM-DD strings.
- Return exactly one JSON object, nothing else.
"""


def _call_deepseek(text: str, api_key: str, model: str = "deepseek-chat") -> dict:
    """Call DeepSeek API and return the parsed JSON dict."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": text[:12000]},  # cap tokens
        ],
        max_tokens=2048,
        response_format={"type": "json_object"},
        **chat_kwargs(model),
    )
    raw = response.choices[0].message.content or "{}"
    return json.loads(raw)


def _safe_str(v) -> str | None:
    return str(v).strip() if v is not None else None


def _to_po_data(d: dict, file_path: str, source_format: str) -> POData:
    """Map the DeepSeek JSON dict → POData."""
    factory_name = _safe_str(d.get("factory"))
    factory_code = _safe_str(d.get("factory_code"))
    factory = f"{factory_code} - {factory_name}" if factory_code and factory_name else (factory_name or factory_code)

    meta = POMetadata(
        po_number=_safe_str(d.get("po_number")),
        po_date=_safe_str(d.get("issue_date")),
        version=_safe_str(d.get("version")),
        buyer=_safe_str(d.get("buyer")),
        seller=_safe_str(d.get("seller")),
        factory=factory,
        ship_to=_safe_str(d.get("ship_to")),
        destination_code=_safe_str(d.get("destination_code")),
        customer=_safe_str(d.get("end_customer")),
        incoterm=_safe_str(d.get("incoterm")),
        origin_port=_safe_str(d.get("origin_port")),
        payment_terms=_safe_str(d.get("payment_terms")),
        discount=_safe_str(d.get("discount")),
        approval_status=_safe_str(d.get("approval_status")),
        country_of_origin=_safe_str(d.get("country_of_origin")),
        division_code=_safe_str(d.get("division_code")),
        division_name=_safe_str(d.get("division_name")),
        season=_safe_str(d.get("season")),
        issued_by=_safe_str(d.get("issued_by")),
        style=_safe_str(d.get("style")),
        style_description=_safe_str(d.get("style_description")),
        style_group=_safe_str(d.get("style_group")),
        unit_cost=_safe_str(d.get("unit_cost")),
        line_extended_cost=_safe_str(d.get("total_extended_cost")),
        xport_date=_safe_str(d.get("xport_date")),
        factory_ship_date=_safe_str(d.get("factory_ship_date")),
        extracted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source_format=source_format,
        file_name=os.path.basename(file_path),
        file_path=file_path,
        parser_version=PARSER_VERSION,
    )

    po_number = meta.po_number or ""
    size_rows: list[SizeRow] = []
    for row in d.get("size_rows") or []:
        size = _safe_str(row.get("size"))
        upc  = _safe_str(row.get("upc")) or ""
        qty  = row.get("quantity")
        if size and size != "-":
            try:
                size_rows.append(SizeRow(
                    po_number=po_number,
                    style=meta.style or "",
                    # Real per-row colour from the model (blank when the PO
                    # has none) — never the division code, which polluted
                    # every export with a wrong-but-plausible value.
                    color=_safe_str(row.get("color")) or "",
                    size=size,
                    units=int(qty) if qty is not None else 0,
                    upc=upc,
                ))
            except (ValueError, TypeError):
                pass

    key_fields = [meta.po_number, meta.factory, meta.country_of_origin,
                  meta.xport_date, meta.division_code, meta.style]
    missing = sum(1 for f in key_fields if not f)
    meta.parse_confidence = max(0, 100 - missing * 10)
    meta.validation_status = (
        "valid" if meta.parse_confidence >= 70 and size_rows
        else ("exception" if not size_rows else "warning")
    )

    return POData(metadata=meta, size_rows=size_rows)


def parse(text: str, file_path: str, api_key: str,
          model: str = "deepseek-chat",
          source_format: str = FORMAT_INFOR_NEXUS) -> POData:
    """Parse PO text via DeepSeek API.  Raises on API/network errors."""
    d = _call_deepseek(text, api_key=api_key, model=model)
    return _to_po_data(d, file_path=file_path, source_format=source_format)
