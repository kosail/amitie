"""JSON-Schema registry for A2UI validation.

Loads the vendored A2UI v0.9 message/common schemas plus our SDK-format catalog
and wires their cross-document `$ref`s (notably `catalog.json` and
`common_types.json`) so `jsonschema` can validate payloads.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

UI_CONTRACT_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = UI_CONTRACT_DIR / "schemas" / "0.9"
CATALOG_SCHEMA_PATH = UI_CONTRACT_DIR / "catalog.schema.json"

_A2UI_BASE = "https://a2ui.org/specification/v0_9"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def catalog_schema() -> dict[str, Any]:
    return _load(CATALOG_SCHEMA_PATH)


@lru_cache(maxsize=1)
def message_schema() -> dict[str, Any]:
    return _load(SCHEMA_DIR / "server_to_client.json")


@lru_cache(maxsize=1)
def registry() -> Registry:
    common = _load(SCHEMA_DIR / "common_types.json")
    messages = _load(SCHEMA_DIR / "server_to_client.json")
    catalog = _load(CATALOG_SCHEMA_PATH)
    resources = [
        (common["$id"], Resource.from_contents(common)),
        (messages["$id"], Resource.from_contents(messages)),
        (catalog["$id"], Resource.from_contents(catalog)),
        # The message/common schemas reference `catalog.json` relatively; point
        # that at our catalog so validation uses the team's component set.
        (f"{_A2UI_BASE}/catalog.json", Resource.from_contents(catalog)),
    ]
    return Registry().with_resources(resources)


@lru_cache(maxsize=1)
def message_validator() -> Draft202012Validator:
    return Draft202012Validator(message_schema(), registry=registry())
