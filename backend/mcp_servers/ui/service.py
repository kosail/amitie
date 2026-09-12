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
from ..savings import service as savings_service

_VERSION = "v0.9"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _descriptor(
    user_id: str,
    domain: str,
    entity_id: str,
    simulation: dict[str, Any] | None,
) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "user_id": user_id,
        "context": "finance" if domain == "loans_credits" else domain,
        "domain": domain,
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
            json.dumps(_descriptor(user_id, domain, entity_id, simulation), ensure_ascii=False),
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
        "SELECT id, user_id, domain, entity_id, catalog_id, template_json, bindings_json, version "
        "FROM generated_ui WHERE id = ?",
        (surface_id,),
    )
    if row is None:
        return {"status": "error", "issues": [f"unknown surface {surface_id!r}"]}

    descriptor = json.loads(row["bindings_json"] or "{}")
    user_id = descriptor.get("user_id") or row["user_id"]
    stored = json.loads(row["template_json"])
    domain = descriptor.get("domain") or row["domain"]
    context = await finance_service.financial_context(database, user_id)
    savings = None
    if domain == "saving_bag":
        bag_id = descriptor.get("entity_id") or row["entity_id"]
        savings = await savings_service.savings_snapshot(database, bag_id) if bag_id else None
        context["savings"] = savings
    components = hydrate_components(
        stored, context, simulation=descriptor.get("simulation"), savings=savings
    )

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


async def record_negotiation_round(
    database: DatabasePort,
    *,
    session_id: str,
    actor: str,
    offer: dict[str, Any],
) -> dict[str, Any]:
    row = await database.fetch_one(
        "SELECT COALESCE(MAX(round_no), 0) AS n FROM negotiation_rounds WHERE session_id = ?",
        (session_id,),
    )
    round_no = int(row["n"]) + 1
    await database.execute(
        "INSERT INTO negotiation_rounds (id, session_id, round_no, actor, offer_json, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (
            uuid.uuid4().hex,
            session_id,
            round_no,
            actor,
            json.dumps(offer or {}, ensure_ascii=False),
            _now(),
        ),
    )
    return {"status": "ok", "round": round_no, "actor": actor, "offer": offer or {}}


async def get_negotiation(database: DatabasePort, session_id: str) -> dict[str, Any]:
    rows = await database.fetch_all(
        "SELECT round_no, actor, offer_json FROM negotiation_rounds WHERE session_id = ? "
        "ORDER BY round_no",
        (session_id,),
    )
    return {
        "status": "ok",
        "rounds": [
            {
                "round": row["round_no"],
                "actor": row["actor"],
                "offer": json.loads(row["offer_json"] or "{}"),
            }
            for row in rows
        ],
    }


async def get_session(database: DatabasePort, session_id: str) -> dict[str, Any]:
    row = await database.fetch_one(
        "SELECT id, user_id, active_surface_id, context_json FROM sessions WHERE id = ?",
        (session_id,),
    )
    if row is None:
        return {"status": "error", "issues": [f"unknown session {session_id!r}"]}
    return {
        "status": "ok",
        "session_id": row["id"],
        "user_id": row["user_id"],
        "active_surface_id": row["active_surface_id"],
        "context": json.loads(row["context_json"] or "{}"),
    }


async def set_session_context(
    database: DatabasePort, session_id: str, context: dict[str, Any]
) -> dict[str, Any]:
    row = await database.fetch_one(
        "SELECT context_json FROM sessions WHERE id = ?", (session_id,)
    )
    if row is None:
        return {"status": "error", "issues": [f"unknown session {session_id!r}"]}
    merged = json.loads(row["context_json"] or "{}")
    merged.update(context or {})
    await database.execute(
        "UPDATE sessions SET context_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(merged, ensure_ascii=False), _now(), session_id),
    )
    return {"status": "ok", "session_id": session_id, "context": merged}
