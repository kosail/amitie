"""Saving Bags endpoints (REQ-API-05).

Every mutation resolves the deterministic writes through MCP first, then runs an
agent turn so the LLM decides the next interface and the closed loop holds
(INV-017). Every mutation returns a full A2UI message array (REQ-LOOP-05).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from agent.service import AgentService
from db.port import DatabasePort
from mcp_servers.toolbox import Toolbox

from ..dependencies import get_agent_service, get_database, get_toolbox, now_iso
from ..schemas import (
    SavingBagAnswerRequest,
    SavingBagCreateRequest,
    SavingBagRefreshRequest,
    SavingBagResponse,
)

router = APIRouter(prefix="/api", tags=["saving-bags"])


async def _resolve_session(
    database: DatabasePort, user_id: str, session_id: str | None
) -> str:
    if session_id:
        row = await database.fetch_one("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if row:
            return session_id
    latest = await database.fetch_one(
        "SELECT id FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
        (user_id,),
    )
    return latest["id"] if latest else f"user:{user_id}"


async def _touch_session(
    database: DatabasePort, session_id: str, surface_id: str | None
) -> None:
    if surface_id:
        await database.execute(
            "UPDATE sessions SET active_surface_id = ?, updated_at = ? WHERE id = ?",
            (surface_id, now_iso(), session_id),
        )


def _response(result: dict, **extra) -> SavingBagResponse:
    return SavingBagResponse(
        status=result.get("status", "error"),
        surface_id=result.get("surface_id"),
        a2ui=result.get("a2ui", []),
        assistant_text=result.get("assistant_text", ""),
        issues=result.get("issues", []),
        message=result.get("message"),
        catalog_id=result.get("catalog_id"),
        audio_ref=result.get("audio_ref"),
        error_code=result.get("error_code"),
        retryable=bool(result.get("retryable", False)),
        **extra,
    )


@router.post("/saving-bags", response_model=SavingBagResponse)
async def create_saving_bag(
    payload: SavingBagCreateRequest,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
    agent: AgentService = Depends(get_agent_service),
) -> SavingBagResponse:
    created = await toolbox.call(
        "create_bag",
        {
            "user_id": payload.user_id,
            "name": payload.name,
            "target_amount": payload.target_amount,
            "target_date": payload.target_date,
        },
    )
    if created.get("status") != "ok":
        return SavingBagResponse(status="error", issues=created.get("issues", []))
    bag = created["bag"]
    session_id = await _resolve_session(database, payload.user_id, payload.session_id)
    result = await agent.run_turn(
        session_id=session_id,
        user_id=payload.user_id,
        text=(
            f"El usuario quiere una bolsa de ahorro llamada '{bag['name']}' "
            f"(bag_id: {bag['id']}). Infiere las preguntas necesarias y emite el "
            "formulario con persist_ui (domain='saving_bag', entity_id=bag_id)."
        ),
    )
    await _touch_session(database, session_id, result.get("surface_id"))
    return _response(result, bag_id=bag["id"], bag=bag)


@router.get("/saving-bags", response_model=SavingBagResponse)
async def list_saving_bags(
    user_id: str = Query(default="u_ana"), toolbox: Toolbox = Depends(get_toolbox)
) -> SavingBagResponse:
    listed = await toolbox.call("list_bags", {"user_id": user_id})
    return SavingBagResponse(status="ok", bags=listed.get("bags", []))


@router.get("/saving-bags/{bag_id}", response_model=SavingBagResponse)
async def get_saving_bag(
    bag_id: str,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
) -> SavingBagResponse:
    snapshot = await toolbox.call("get_savings_snapshot", {"bag_id": bag_id})
    if snapshot.get("status") != "ok":
        raise HTTPException(status_code=404, detail="unknown saving bag")
    savings = snapshot["savings"]

    a2ui: list[dict] = []
    surface = await database.fetch_one(
        "SELECT id FROM generated_ui WHERE domain = 'saving_bag' AND entity_id = ? "
        "ORDER BY updated_at DESC, rowid DESC LIMIT 1",
        (bag_id,),
    )
    if surface is not None:
        hydrated = await toolbox.call("hydrate_ui", {"surface_id": surface["id"]})
        a2ui = hydrated.get("a2ui", [])

    return SavingBagResponse(
        status="ok",
        bag_id=bag_id,
        bag=savings["bag"],
        plan=savings.get("plan"),
        surface_id=surface["id"] if surface else None,
        a2ui=a2ui,
    )


@router.post("/saving-bags/{bag_id}/answer", response_model=SavingBagResponse)
async def answer_saving_bag(
    bag_id: str,
    payload: SavingBagAnswerRequest,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
    agent: AgentService = Depends(get_agent_service),
) -> SavingBagResponse:
    answered = await toolbox.call(
        "answer_bag", {"bag_id": bag_id, "answers": payload.answers}
    )
    if answered.get("status") != "ok":
        raise HTTPException(status_code=404, detail="unknown saving bag")
    session_id = await _resolve_session(database, payload.user_id, payload.session_id)
    result = await agent.run_turn(
        session_id=session_id,
        user_id=payload.user_id,
        text=(
            f"El usuario respondió la bolsa {bag_id} (respuestas ya guardadas): "
            f"{json.dumps(payload.answers, ensure_ascii=False)}. Investiga costos con "
            "research_costs, estima con estimate_total, calcula factibilidad con "
            "compute_feasibility y emite la superficie del plan con persist_ui."
        ),
    )
    await _touch_session(database, session_id, result.get("surface_id"))
    return _response(result, bag_id=bag_id)


@router.post("/saving-bags/{bag_id}/refresh", response_model=SavingBagResponse)
async def refresh_saving_bag(
    bag_id: str,
    payload: SavingBagRefreshRequest,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
    agent: AgentService = Depends(get_agent_service),
) -> SavingBagResponse:
    refreshed = await toolbox.call("refresh_bag", {"bag_id": bag_id})
    if refreshed.get("status") != "ok":
        raise HTTPException(status_code=404, detail="unknown saving bag")
    session_id = await _resolve_session(database, payload.user_id, payload.session_id)
    result = await agent.run_turn(
        session_id=session_id,
        user_id=payload.user_id,
        text=(
            f"Se actualizaron los costos de la bolsa {bag_id} (nueva investigación y plan "
            "recalculado). Reemite la superficie del plan con persist_ui."
        ),
    )
    await _touch_session(database, session_id, result.get("surface_id"))
    return _response(result, bag_id=bag_id, plan=refreshed.get("plan"))
