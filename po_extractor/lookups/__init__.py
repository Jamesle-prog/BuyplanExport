"""Lookup tables built from reference Excel files.

Usage
-----
from po_extractor.lookups import EANLookup, FabricLookup, ProgressLookup

ean     = EANLookup(path_to_ean_file)
fabric  = FabricLookup(path_to_fabric_file)
progress= ProgressLookup(path_to_progress_file)

# Lookups
ean.get_ean("DR4532", "S")           → "4070598094480"
fabric.get_composition("DR4532")     → "92%Recycle Polyester 8%Elastane"
fabric.get_fabric_nos("DR4532")      → [("大身","HHN-JA-01715"), ("网布","HHN-MS-01794")]
progress.get_contract_no("DR4532", "NAVY")  → "26302-ZA7011"
"""
from .ean_lookup        import EANLookup
from .fabric_lookup     import FabricLookup
from .progress_lookup   import ProgressLookup
from .config_sku_lookup import ConfigSKULookup

__all__ = ["EANLookup", "FabricLookup", "ProgressLookup", "ConfigSKULookup"]
