"""Machine-readable A2UI catalogs.

`catalog.json` is the standard machine source derived from `A2UI_CATALOG.md`.
`voz_color.json` is the accessible catalog: it declares `extends` and reuses the
standard component set, but is its own catalog ID (the frontend keys accessible
styling on the ID). This registry drives the system prompt, the validator, and
the frontend contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

UI_CONTRACT_DIR = Path(__file__).resolve().parent
CATALOG_PATH = UI_CONTRACT_DIR / "catalog.json"
VOZ_COLOR_PATH = UI_CONTRACT_DIR / "voz_color.json"

STANDARD_CATALOG_ID = "amitie.standard.v1"
VOZ_COLOR_CATALOG_ID = "amitie.voz-color.v1"


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


def _components_from(raw: Mapping[str, Any]) -> dict[str, ComponentSpec]:
    return {
        name: ComponentSpec(
            name=name,
            required=tuple(spec.get("required", ())),
            props=dict(spec.get("props", {})),
        )
        for name, spec in (raw.get("components") or {}).items()
    }


def load_catalog(path: Path | None = None) -> Catalog:
    data: dict[str, Any] = json.loads((path or CATALOG_PATH).read_text(encoding="utf-8"))
    return Catalog(
        catalog_id=data["catalogId"],
        version=data["version"],
        messages=tuple(data["messages"]),
        actions=tuple(data["actions"]),
        components=_components_from(data),
    )


def _load_voz_color(base: Catalog) -> Catalog:
    data: dict[str, Any] = json.loads(VOZ_COLOR_PATH.read_text(encoding="utf-8"))
    if data.get("extends") not in (None, base.catalog_id):
        raise ValueError(f"unknown catalog base: {data.get('extends')!r}")
    components = dict(base.components)
    components.update(_components_from(data))
    return Catalog(
        catalog_id=data["catalogId"],
        version=data.get("version") or base.version,
        messages=tuple(data.get("messages") or base.messages),
        actions=tuple(data.get("actions") or base.actions),
        components=components,
    )


def load_catalogs() -> dict[str, Catalog]:
    standard = load_catalog(CATALOG_PATH)
    voz_color = _load_voz_color(standard)
    return {standard.catalog_id: standard, voz_color.catalog_id: voz_color}


CATALOGS: dict[str, Catalog] = load_catalogs()
CATALOG: Catalog = CATALOGS[STANDARD_CATALOG_ID]
CATALOG_ID = CATALOG.catalog_id
VOZ_COLOR: Catalog = CATALOGS[VOZ_COLOR_CATALOG_ID]
VOZ_COLOR_ID = VOZ_COLOR.catalog_id


def catalog_for(catalog_id: str | None) -> Catalog | None:
    if not catalog_id:
        return None
    return CATALOGS.get(catalog_id)
