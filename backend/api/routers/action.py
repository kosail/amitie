"""POST /api/action."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent.negotiation import NegotiationService
from agent.service import AgentService
from db.port import DatabasePort
from mcp_servers.toolbox import Toolbox

from ..dependencies import (
    get_agent_service,
    get_database,
    get_negotiation_service,
    get_toolbox,
)
from ..schemas import ActionRequest, AgentResponse, HttpErrorDetail

router = APIRouter(prefix="/api", tags=["action"])


@router.post(
    "/action",
    response_model=AgentResponse,
    summary="Submit closed-loop A2UI action (REQ-API-03)",
    response_description="Updated A2UI interface and assistant state after processing component action",
    operation_id="post_action",
    responses={
        200: {
            "description": "Action processed successfully; returns updated A2UI message array.",
            "model": AgentResponse,
        },
        404: {
            "description": "Surface not found.",
            "model": HttpErrorDetail,
        },
    },
)
async def post_action(
    payload: ActionRequest,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
    agent: AgentService = Depends(get_agent_service),
    negotiation: NegotiationService = Depends(get_negotiation_service),
) -> AgentResponse:
    """Submit a user interaction emitted by an A2UI component (REQ-API-03, INV-017).

    - Closes the loop: interactions such as moving a liquidity/term slider (`tune_tradeoff`),
      toggling assumptions (`toggle_assumption`), or accepting a debt consolidation offer (`accept_offer`)
      are fed back into the agent context.
    - If accepting an offer, launches or transitions to the El Revés negotiation loop.
    - If tuning tradeoffs or assumptions, recalculates the deterministic financial math via MCP
      and triggers structural revalidation or BreakAlert mutation.
    """
    surface = await database.fetch_one(
        "SELECT id, user_id FROM generated_ui WHERE id = ?", (payload.surface_id,)
    )
    if surface is None:
        raise HTTPException(status_code=404, detail="unknown surface")
    user_id = surface["user_id"]

    if payload.name == "accept_offer":
        offer = payload.context.get("offer") or {}
        session_id = payload.context.get("session_id")
        if not session_id:
            latest = await database.fetch_one(
                "SELECT id FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
                (user_id,),
            )
            session_id = latest["id"] if latest else f"user:{user_id}"
        return AgentResponse(
            **await negotiation.accept(session_id=session_id, user_id=user_id, offer=offer)
        )

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
