"""Pure `{{path.to.value}}` placeholder resolution.

Placeholders are resolved against the same context that A2UI bindings point
into, so a persisted template can stay data-free. A string that is exactly one
placeholder preserves the underlying type; otherwise placeholders are
interpolated as text.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")


def collect_placeholders(value: Any) -> set[str]:
    paths: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, str):
            paths.update(_PLACEHOLDER.findall(node))
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            for item in node.values():
                visit(item)

    visit(value)
    return paths


def resolve_placeholders(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _resolve_string(value, context)
    if isinstance(value, list):
        return [resolve_placeholders(item, context) for item in value]
    if isinstance(value, dict):
        return {key: resolve_placeholders(item, context) for key, item in value.items()}
    return value


def _resolve_string(text: str, context: dict[str, Any]) -> Any:
    whole = _PLACEHOLDER.fullmatch(text.strip())
    if whole:
        return _lookup(whole.group(1), context)

    def replace(match: re.Match[str]) -> str:
        resolved = _lookup(match.group(1), context)
        return "" if resolved is None else str(resolved)

    return _PLACEHOLDER.sub(replace, text)


def _lookup(path: str, context: Any) -> Any:
    current = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current
