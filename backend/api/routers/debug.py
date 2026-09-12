"""GET /debug/trace/{trace_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from observability.tracing import Tracer

from ..dependencies import get_tracer
from ..schemas import TraceResponse

router = APIRouter(tags=["debug"])


@router.get("/debug/trace/{trace_id}", response_model=TraceResponse)
async def get_trace(trace_id: str, tracer: Tracer = Depends(get_tracer)) -> TraceResponse:
    events = await tracer.history(trace_id)
    return TraceResponse(trace_id=trace_id, events=events)
