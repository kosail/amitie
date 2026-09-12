"""El Reves negotiation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agent.negotiation import NegotiationService

from ..dependencies import get_negotiation_service
from ..schemas import AgentResponse, NegotiationRequest

router = APIRouter(prefix="/api", tags=["negotiation"])


@router.post("/negotiation/{session_id}/turn", response_model=AgentResponse)
async def negotiation_turn(
    session_id: str,
    payload: NegotiationRequest,
    negotiation: NegotiationService = Depends(get_negotiation_service),
) -> AgentResponse:
    result = await negotiation.run_round(
        session_id=session_id, user_id=payload.user_id, position=payload.position or None
    )
    return AgentResponse(**result)


@router.post("/negotiation/{session_id}/take-control", response_model=AgentResponse)
async def negotiation_take_control(
    session_id: str,
    payload: NegotiationRequest,
    negotiation: NegotiationService = Depends(get_negotiation_service),
) -> AgentResponse:
    result = await negotiation.run_round(
        session_id=session_id,
        user_id=payload.user_id,
        position=payload.position or None,
        take_control=True,
    )
    return AgentResponse(**result)
