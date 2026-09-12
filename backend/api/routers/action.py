"""POST /api/action."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent.service import AgentService
from db.port import DatabasePort
from mcp_servers.toolbox import Toolbox

from ..dependencies import get_agent_service, get_database, get_toolbox
from ..schemas import ActionRequest, AgentResponse

router = APIRouter(prefix="/api", tags=["action"])


@router.post("/action", response_model=AgentResponse)
async def post_action(
    payload: ActionRequest,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
    agent: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    surface = await database.fetch_one(
        "SELECT id, user_id FROM generated_ui WHERE id = ?", (payload.surface_id,)
    )
    if surface is None:
        raise HTTPException(status_code=404, detail="unknown surface")
    user_id = surface["user_id"]

    # Record the interaction through MCP (the only door to actions).
    await toolbox.call(
        "a2ui_action",
        {
            "user_id": user_id,
            "surface_id": payload.surface_id,
            "name": payload.name,
            "source_component_id": payload.source_component_id,
            "context": payload.context,
        },
    )

    # Continuity: use the user's most recent session as the ADK session id.
    latest = await database.fetch_one(
        "SELECT id FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1", (user_id,)
    )
    session_id = latest["id"] if latest else f"user:{user_id}"

    result = await agent.run_turn(
        session_id=session_id,
        user_id=user_id,
        action={
            "name": payload.name,
            "surface_id": payload.surface_id,
            "context": payload.context,
        },
    )
    return AgentResponse(**result)
