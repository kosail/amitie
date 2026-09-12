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
from hydration.speech import speech_text
from ui_contract.catalog import CATALOG_ID, VOZ_COLOR_ID
from ui_contract.validator import validate_messages

from ..finance import service as finance_service
from ..voice.service import text_hash as speech_hash

_VERSION = "v0.9"
_INACCESSIBLE_MODES = {"", "none", "null", "standard", "normal"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _accessibility_profile(
    database: DatabasePort, user_id: str
) -> dict[str, Any] | None:
    row = await database.fetch_one(
        "SELECT mode, voice_id, speed FROM accessibility_profiles WHERE user_id = ? "
        "ORDER BY id LIMIT 1",
        (user_id,),
    )
    if row is None:
        return None
    mode = str(row["mode"] or "").strip().lower()
    if mode in _INACCESSIBLE_MODES:
        return None
    return {
        "mode": mode,
        "voice_id": row["voice_id"] or "",
        "speed": float(row["speed"] or 1.0),
    }


def _descriptor(
    user_id: str,
    domain: str,
    entity_id: str,
    simulation: dict[str, Any] | None,
    *,
    accessible: bool = False,
    speech: str = "",
    voice_id: str = "",
    speed: float = 1.0,
    data_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "user_id": user_id,
        "context": "finance" if domain == "loans_credits" else domain,
        "domain": domain,
        "entity_id": entity_id or None,
        "accessible": accessible,
    }
    if simulation:
        descriptor["simulation"] = simulation
    if data_model:
        descriptor["data_model"] = data_model
    if accessible:
        descriptor.update({"speech": speech, "voice_id": voice_id, "speed": speed})
    return descriptor


async def _render(
    database: DatabasePort, row: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, Any]:
    """Shared hydration core: fresh data, placeholders, and structural revalidation."""
    user_id = descriptor.get("user_id") or row["user_id"]
    stored = json.loads(row["template_json"])
    domain = descriptor.get("domain") or row["domain"]
    context = await finance_service.financial_context(database, user_id)
    # Snapshot values captured at persist time (for `{{placeholders}}`); live
    # finance values take precedence where keys overlap.
    snapshot = descriptor.get("data_model")
    if isinstance(snapshot, dict) and snapshot:
        context = {**snapshot, **context}

    audio_ref = ""
    if descriptor.get("accessible"):
        spoken = str(descriptor.get("speech") or "")
        speech_payload: dict[str, Any] = {"text": spoken}
        if spoken:
            digest = speech_hash(
                spoken, descriptor.get("voice_id", ""), descriptor.get("speed", 1.0)
            )
            asset = await database.fetch_one(
                "SELECT id FROM audio_assets WHERE text_hash = ? ORDER BY created_at DESC LIMIT 1",
                (digest,),
            )
            if asset is not None:
                audio_ref = f"/api/audio/{asset['id']}"
                speech_payload["audioRef"] = audio_ref
        context["speech"] = speech_payload

    components = hydrate_components(
        stored, context, simulation=descriptor.get("simulation")
    )
    return {"components": components, "context": context, "audio_ref": audio_ref}


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
    speech: str = "",
) -> dict[str, Any]:
    profile = await _accessibility_profile(database, user_id)
    accessible = profile is not None
    # INV-003: accessible mode is automatic, never a caller choice.
    pinned_catalog = VOZ_COLOR_ID if accessible else CATALOG_ID
    spoken = (speech or "").strip()
    if accessible and not spoken:
        spoken = speech_text(components)

    validation = validate_messages(
        [
            {"version": _VERSION, "createSurface": {"surfaceId": "pending", "catalogId": pinned_catalog}},
            {"version": _VERSION, "updateComponents": {"surfaceId": "pending", "components": components}},
        ]
    )
    if not validation.ok:
        return {"status": "error", "issues": list(validation.issues)}

    surface_id = "surf_" + uuid.uuid4().hex[:12]
    now = _now()
    descriptor = _descriptor(
        user_id,
        domain,
        entity_id,
        simulation,
        accessible=accessible,
        speech=spoken,
        voice_id=(profile or {}).get("voice_id", ""),
        speed=(profile or {}).get("speed", 1.0),
        data_model=data_model,
    )
    await database.execute(
        "INSERT INTO generated_ui (id, user_id, domain, entity_id, catalog_id, template_json, "
        "bindings_json, version, audience, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            surface_id,
            user_id,
            domain,
            entity_id or None,
            pinned_catalog,
            json.dumps(components, ensure_ascii=False),
            json.dumps(descriptor, ensure_ascii=False),
            1,
            "accessible" if accessible else "user",
            now,
            now,
        ),
    )
    rendered = await _render(
        database,
        {
            "id": surface_id,
            "user_id": user_id,
            "domain": domain,
            "entity_id": entity_id or None,
            "catalog_id": pinned_catalog,
            "template_json": json.dumps(components, ensure_ascii=False),
            "bindings_json": json.dumps(descriptor, ensure_ascii=False),
            "version": 1,
        },
        descriptor,
    )
    await database.execute(
        "UPDATE generated_ui SET frozen_json = ? WHERE id = ?",
        (
            json.dumps(
                {
                    "catalog_id": pinned_catalog,
                    "components": rendered["components"],
                    "data_model": rendered["context"],
                    "audio_ref": rendered["audio_ref"],
                    "version": 1,
                },
                ensure_ascii=False,
            ),
            surface_id,
        ),
    )
    return {
        "status": "ok",
        "surface_id": surface_id,
        "version": 1,
        "catalog_id": pinned_catalog,
        "accessible": accessible,
        "speech": spoken if accessible else "",
        "voice_id": (profile or {}).get("voice_id", ""),
        "speed": (profile or {}).get("speed", 1.0),
        "a2ui": [
            {"version": _VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": pinned_catalog}},
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
    stored = json.loads(row["template_json"])
    rendered = await _render(database, row, descriptor)
    components = rendered["components"]

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
        "catalog_id": row["catalog_id"],
        "audio_ref": rendered["audio_ref"],
        "a2ui": [
            {"version": _VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": row["catalog_id"]}},
            {"version": _VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}},
            {"version": _VERSION, "updateDataModel": {"surfaceId": surface_id, "path": "/", "value": rendered["context"]}},
        ],
    }


async def kill_test(database: DatabasePort, surface_id: str) -> dict[str, Any]:
    """Serve the genuine frozen artifact with no agent and no live recompute (REQ-KT-01/02)."""
    row = await database.fetch_one(
        "SELECT id, catalog_id, version, frozen_json FROM generated_ui WHERE id = ?",
        (surface_id,),
    )
    if row is None:
        return {"status": "error", "issues": [f"unknown surface {surface_id!r}"]}
    if not row["frozen_json"]:
        return {"status": "error", "issues": [f"surface {surface_id!r} has no frozen artifact"]}

    frozen = json.loads(row["frozen_json"])
    catalog_id = frozen.get("catalog_id") or row["catalog_id"]
    return {
        "status": "ok",
        "surface_id": surface_id,
        "catalog_id": catalog_id,
        "version": frozen.get("version", row["version"]),
        "audio_ref": frozen.get("audio_ref", ""),
        "a2ui": [
            {"version": _VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id}},
            {"version": _VERSION, "updateComponents": {"surfaceId": surface_id, "components": frozen.get("components", [])}},
            {"version": _VERSION, "updateDataModel": {"surfaceId": surface_id, "path": "/", "value": frozen.get("data_model", {})}},
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
