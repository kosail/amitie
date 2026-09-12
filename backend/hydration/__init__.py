"""Hydration: rebuild data and resolve `{{...}}` placeholders (M3.2)."""

from .placeholders import collect_placeholders, resolve_placeholders
from .service import hydrate_components, revalidate

__all__ = [
    "collect_placeholders",
    "hydrate_components",
    "resolve_placeholders",
    "revalidate",
]
