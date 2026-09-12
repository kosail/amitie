"""Machine-readable A2UI catalog for the M3 subset.

`catalog.json` is the single machine source derived from `A2UI_CATALOG.md`.
It drives the system prompt, the validator, and (later) the frontend contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    required: tuple[str, ...]
    props: dict[str, str]


@dataclass(frozen=True)
class Catalog:
    catalog_id: str
    version: str
    messages: tuple[str, ...]
    actions: tuple[str, ...]
    components: dict[str, ComponentSpec]

    def component_names(self) -> tuple[str, ...]:
        return tuple(self.components)


def load_catalog(path: Path | None = None) -> Catalog:
    data: dict[str, Any] = json.loads((path or CATALOG_PATH).read_text(encoding="utf-8"))
    components = {
        name: ComponentSpec(
            name=name,
            required=tuple(spec.get("required", ())),
            props=dict(spec.get("props", {})),
        )
        for name, spec in data["components"].items()
    }
    return Catalog(
        catalog_id=data["catalogId"],
        version=data["version"],
        messages=tuple(data["messages"]),
        actions=tuple(data["actions"]),
        components=components,
    )


CATALOG = load_catalog()
CATALOG_ID = CATALOG.catalog_id
