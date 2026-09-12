"""El Reves negotiation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agent.negotiation import NegotiationService

from ..dependencies import get_negotiation_service
from ..schemas import AgentResponse, NegotiationRequest

router = APIRouter(prefix="/api", tags=["negotiation"])


@router.post(
    "/negotiation/{session_id}/turn",
    response_model=AgentResponse,
    summary="Advance El Revés negotiation turn (REQ-API-06)",
    response_description="Negotiation round outcome with counterproposal or agreement in A2UI",
    operation_id="negotiation_turn",
    responses={
        200: {
            "description": "Round evaluated; returns updated offer state and negotiation A2UI.",
            "model": AgentResponse,
        },
    },
)
async def negotiation_turn(
    session_id: str,
    payload: NegotiationRequest,
    negotiation: NegotiationService = Depends(get_negotiation_service),
) -> AgentResponse:
    """Execute one round of the El Revés bank negotiation (REQ-API-06, INV-001).

    - The agent negotiates against a simulated bank persona using bank lender policies.
    - Evaluates interest rates, terms, and liquidity tradeoff constraints.
    - Emits updated negotiation UI with bank counteroffer or final agreement.
    """
    result = await negotiation.run_round(
        session_id=session_id, user_id=payload.user_id, position=payload.position or None
    )
    return AgentResponse(**result)


@router.post(
    "/negotiation/{session_id}/take-control",
    response_model=AgentResponse,
    summary="User takes manual control of El Revés negotiation (REQ-API-06)",
    response_description="Manual counterproposal evaluated by the bank persona with updated A2UI",
    operation_id="negotiation_take_control",
    responses={
        200: {
            "description": "Manual position evaluated by the bank persona.",
            "model": AgentResponse,
        },
    },
)
async def negotiation_take_control(
    session_id: str,
    payload: NegotiationRequest,
    negotiation: NegotiationService = Depends(get_negotiation_service),
) -> AgentResponse:
    """Allow the user to intervene directly and propose custom terms to the bank persona."""
    result = await negotiation.run_round(
        session_id=session_id,
        user_id=payload.user_id,
        position=payload.position or None,
        take_control=True,
    )
    return AgentResponse(**result)
