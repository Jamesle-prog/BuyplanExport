"""Output format registry — each format has an ID, version, description, and entry point."""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class OutputFormat:
    format_id: str
    version: str
    display_name: str
    description: str
    file_suffix: str    # e.g. "buy_plan"
    extension: str      # e.g. ".xlsx"
    # entry point filled in at registration time
    export_fn: Callable | None = None


_REGISTRY: dict[str, OutputFormat] = {}


def register(fmt: OutputFormat) -> OutputFormat:
    _REGISTRY[fmt.format_id] = fmt
    return fmt


def get(format_id: str) -> OutputFormat | None:
    return _REGISTRY.get(format_id)


def all_formats() -> list[OutputFormat]:
    return list(_REGISTRY.values())
