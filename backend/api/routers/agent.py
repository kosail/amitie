"""POST /api/agent/greeting — deterministic spoken greeting for the La Mesa tab."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent.service import AgentService
from db.port import DatabasePort

from ..dependencies import get_agent_service, get_database
from ..schemas import AgentGreetingRequest, AgentResponse

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/greeting", response_model=AgentResponse)
async def greeting(
    payload: AgentGreetingRequest,
    database: DatabasePort = Depends(get_database),
    agent: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    session = await database.fetch_one(
        "SELECT id, user_id FROM sessions WHERE id = ?", (payload.session_id,)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")
    result = await agent.greeting(user_id=session["user_id"])
    return AgentResponse(**result)
