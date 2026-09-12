"""POST /api/message."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent.service import AgentService
from db.port import DatabasePort

from ..dependencies import get_agent_service, get_database, now_iso
from ..schemas import AgentResponse, MessageRequest

router = APIRouter(prefix="/api", tags=["message"])


@router.post("/message", response_model=AgentResponse)
async def post_message(
    payload: MessageRequest,
    database: DatabasePort = Depends(get_database),
    agent: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    session = await database.fetch_one(
        "SELECT id, user_id FROM sessions WHERE id = ?", (payload.session_id,)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")

    if payload.audio_b64 and not payload.text:
        return AgentResponse(status="error", message="audio input is not supported yet (M7)")
    if not payload.text:
        return AgentResponse(status="error", message="text is required")

    result = await agent.run_turn(
        session_id=payload.session_id, user_id=session["user_id"], text=payload.text
    )
    if result.get("status") == "ok" and result.get("surface_id"):
        await database.execute(
            "UPDATE sessions SET active_surface_id = ?, updated_at = ? WHERE id = ?",
            (result["surface_id"], now_iso(), payload.session_id),
        )
    return AgentResponse(**result)
