"""Deterministic normalization of A2UI components before schema validation.

LLMs reliably emit two shapes the A2UI JSON schemas reject even though our
prompt/hydration model uses them:

- a component ``action`` as a bare action-name string (the schema requires an
  ``Action`` object: ``{"event": {"name": ..., "context": {}}}``);
- numeric/boolean props as ``{{dot.path}}`` placeholder strings (the schema
  accepts only a literal or a ``{"path": ...}`` binding).

This module rewrites those into schema-valid shapes without touching the
values. It is pure and deterministic (INV-015); validation still runs after it.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .catalog import CATALOG, Catalog

_PLACEHOLDER = re.compile(r"^\{\{\s*([A-Za-z0-9_.]+)\s*\}\}$")
_ACTION_KEYS = ("id", "component", "children", "child", "action")
_NUMERIC_TOKENS = {"number", "dynamicNumber"}
_BOOLEAN_TOKENS = {"boolean", "dynamicBool"}


def _binding_from_placeholder(path: str) -> dict[str, str]:
    return {"path": "/" + path.replace(".", "/")}


def _coerce_numeric(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        match = _PLACEHOLDER.match(value.strip())
        if match:
            return _binding_from_placeholder(match.group(1))
        try:
            number = float(value)
        except ValueError:
            return value
        return int(number) if number.is_integer() else number
    return value


def _coerce_boolean(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        match = _PLACEHOLDER.match(value.strip())
        if match:
            return _binding_from_placeholder(match.group(1))
        lowered = value.strip().lower()
        if lowered in ("true", "false"):
            return lowered == "true"
    return value


def _normalize_action(value: Any, catalog: Catalog) -> Any:
    if isinstance(value, str) and value in catalog.actions:
        return {"event": {"name": value, "context": {}}}
    return value


def normalize_component(component: Any, catalog: Catalog = CATALOG) -> Any:
    if not isinstance(component, dict):
        return component
    component_type = component.get("component")
    spec = catalog.components.get(component_type) if isinstance(component_type, str) else None
    props = spec.props if spec is not None else {}
    normalized: dict[str, Any] = {}
    for key, value in component.items():
        if key == "action":
            normalized[key] = _normalize_action(value, catalog)
            continue
        token = props.get(key)
        if token in _NUMERIC_TOKENS:
            normalized[key] = _coerce_numeric(value)
        elif token in _BOOLEAN_TOKENS:
            normalized[key] = _coerce_boolean(value)
        else:
            normalized[key] = value
    return normalized


def normalize_components(
    components: Any, catalog: Catalog = CATALOG
) -> list[Any]:
    if not isinstance(components, list):
        return components
    return [normalize_component(component, catalog) for component in components]


def normalize_terminal(terminal: Mapping[str, Any], catalog: Catalog = CATALOG) -> dict[str, Any]:
    """Return a copy of a terminal_response with normalized components."""
    if not isinstance(terminal, Mapping):
        return dict(terminal)  # type: ignore[arg-type]
    result = dict(terminal)
    result["components"] = normalize_components(terminal.get("components"), catalog)
    return result
