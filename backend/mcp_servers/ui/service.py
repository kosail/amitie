"""UI persistence, hydration, and action logging.

`hydrate_ui` re-runs `financial_context` so re-fetched surfaces always carry
fresh data, then resolves any `{{...}}` placeholders (REQ-UI-01, REQ-UI-02).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from db.port import DatabasePort
from hydration.service import hydrate_components
from ui_contract.validator import validate_messages

from ..finance import service as finance_service

_VERSION = "v0.9"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _descriptor(
    user_id: str, entity_id: str, simulation: dict[str, Any] | None
) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "user_id": user_id,
        "context": "finance",
        "entity_id": entity_id or None,
    }
    if simulation:
        descriptor["simulation"] = simulation
    return descriptor


async def persist_ui(
    database: DatabasePort,
    *,
    user_id: str,
    domain: str,
    catalog_id: str,
    components: list[dict[str, Any]],
    data_model: dict[str, Any],
    entity_id: str = "",
    simulation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validate_messages(
        [
            {"version": _VERSION, "createSurface": {"surfaceId": "pending", "catalogId": catalog_id}},
            {"version": _VERSION, "updateComponents": {"surfaceId": "pending", "components": components}},
        ]
    )
    if not validation.ok:
        return {"status": "error", "issues": list(validation.issues)}

    surface_id = "surf_" + uuid.uuid4().hex[:12]
    now = _now()
    await database.execute(
        "INSERT INTO generated_ui (id, user_id, domain, entity_id, catalog_id, template_json, "
        "bindings_json, version, audience, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            surface_id,
            user_id,
            domain,
            entity_id or None,
            catalog_id,
            json.dumps(components, ensure_ascii=False),
            json.dumps(_descriptor(user_id, entity_id, simulation), ensure_ascii=False),
            1,
            "user",
            now,
            now,
        ),
    )
    return {
        "status": "ok",
        "surface_id": surface_id,
        "version": 1,
        "a2ui": [
            {"version": _VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id}},
            {"version": _VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}},
            {
                "version": _VERSION,
                "updateDataModel": {"surfaceId": surface_id, "path": "/", "value": data_model or {}},
            },
        ],
    }


async def hydrate_ui(database: DatabasePort, surface_id: str) -> dict[str, Any]:
    row = await database.fetch_one(
        "SELECT id, user_id, catalog_id, template_json, bindings_json, version "
        "FROM generated_ui WHERE id = ?",
        (surface_id,),
    )
    if row is None:
        return {"status": "error", "issues": [f"unknown surface {surface_id!r}"]}

    descriptor = json.loads(row["bindings_json"] or "{}")
    user_id = descriptor.get("user_id") or row["user_id"]
    context = await finance_service.financial_context(database, user_id)
    stored = json.loads(row["template_json"])
    components = hydrate_components(stored, context, simulation=descriptor.get("simulation"))

    version = row["version"]
    if json.dumps(components, sort_keys=True) != json.dumps(stored, sort_keys=True):
        version += 1
        await database.execute(
            "UPDATE generated_ui SET template_json = ?, version = ?, updated_at = ? WHERE id = ?",
            (json.dumps(components, ensure_ascii=False), version, _now(), surface_id),
        )

    return {
        "status": "ok",
        "surface_id": surface_id,
        "version": version,
        "a2ui": [
            {"version": _VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": row["catalog_id"]}},
            {"version": _VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}},
            {"version": _VERSION, "updateDataModel": {"surfaceId": surface_id, "path": "/", "value": context}},
        ],
    }


async def a2ui_action(
    database: DatabasePort,
    *,
    user_id: str,
    surface_id: str,
    name: str,
    source_component_id: str = "",
    context: dict[str, Any] | None = None,
    timestamp: str = "",
) -> dict[str, Any]:
    await database.execute(
        "INSERT INTO ui_actions (id, surface_id, user_id, action_name, source_component_id, "
        "context_json, created_at) VALUES (?,?,?,?,?,?,?)",
        (
            uuid.uuid4().hex,
            surface_id,
            user_id,
            name,
            source_component_id or None,
            json.dumps(context or {}, ensure_ascii=False),
            timestamp or _now(),
        ),
    )
    return {"status": "ok", "surface_id": surface_id, "action": name, "context": context or {}}
