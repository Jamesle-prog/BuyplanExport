"""CPRS API — full typed client generated from CPRS_API.openapi.json.

    from po_extractor.cprs import CprsApiClient
    api = CprsApiClient("http://localhost:3100", api_key="…")
    run = api.evaluation.evaluate({"clientId": "…", "channel": "WHOLESALE"})

The buy-plan-specific, best-effort helper (`CprsClient`) still lives in
`po_extractor/utils/cprs_client.py`; this package is the complete raw surface.
Regenerate with `python scripts/gen_cprs_client.py` after updating the spec.
"""
from __future__ import annotations

from .client import CprsApiClient, CprsError, cprs_api_from_settings
from . import models

__all__ = ["CprsApiClient", "CprsError", "cprs_api_from_settings", "models"]
