"""Configurable size order for PO exports.

Size order is persisted in ``{project_root}/data/size_order.json``.
Falls back to the hardcoded ``SIZE_ORDER`` constant in ``config.py`` when
the JSON file is absent or unreadable.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import SIZE_ORDER as _DEFAULT_ORDER

# Resolved relative to this file:
#   po_extractor/utils/size_config.py → po_extractor/ → project root
from ..config import DATA_DIR as _DATA_DIR_STR
_DATA_DIR = Path(_DATA_DIR_STR)
_SIZE_ORDER_JSON = _DATA_DIR / "size_order.json"


def get_size_order() -> list[str]:
    """Return the current ordered size list (from JSON or hardcoded default)."""
    try:
        if _SIZE_ORDER_JSON.exists():
            data = json.loads(_SIZE_ORDER_JSON.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return [str(s).strip().upper() for s in data if str(s).strip()]
    except Exception:
        pass
    return list(_DEFAULT_ORDER)


def save_size_order(sizes: list[str]) -> None:
    """Persist a new ordered size list to JSON."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean = [s.strip().upper() for s in sizes if s.strip()]
    _SIZE_ORDER_JSON.write_text(
        json.dumps(clean, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
