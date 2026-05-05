"""Shared FabricPart dataclass used across all client pipelines."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FabricPart:
    """One fabric component of a style (e.g. main body, lining, pocket mesh).

    Attributes
    ----------
    combo_idx    : 0-based index of the fabric combination (file row) this part
                   belongs to.  Styles that appear on N rows in the mapping file
                   produce N combinations (0 … N-1).  All fabric parts in the
                   same file row share the same combo_idx.
    seq          : 1-based ordering within its combination (1 = primary fabric)
    body_part    : human label such as "大身", "网布", "Main Body", "Lining"
                   Empty string if the source didn't specify a part name.
    hhn_no       : HHN fabric number, e.g. "HHN-JA-01715"
    composition  : wash-label composition, e.g. "92% Polyester 8% Elastane"
    weight_gsm   : fabric weight in g/m²  (0 if unknown)
    width_cm     : fabric width in cm     (0 if unknown)
    """

    combo_idx:   int  = 0
    seq:         int  = 0
    body_part:   str  = ""
    hhn_no:      str  = ""
    composition: str  = ""
    weight_gsm:  int  = 0
    width_cm:    int  = 0

    def is_empty(self) -> bool:
        return not self.hhn_no and not self.composition

    def display(self) -> str:
        """Short human-readable string for UI / exports."""
        parts = []
        if self.body_part:
            parts.append(self.body_part)
        if self.hhn_no:
            parts.append(self.hhn_no)
        if self.composition:
            parts.append(self.composition)
        if self.weight_gsm:
            parts.append(f"{self.weight_gsm}g/m²")
        return "  |  ".join(parts)
