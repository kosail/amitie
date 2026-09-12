"""GET /debug/trace/{trace_id} and GET /debug/kill-test/{surface_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from mcp_servers.toolbox import Toolbox
from observability.tracing import Tracer

from ..dependencies import get_toolbox, get_tracer
from ..schemas import TraceResponse, UiResponse

router = APIRouter(tags=["debug"])


@router.get("/debug/trace/{trace_id}", response_model=TraceResponse)
async def get_trace(trace_id: str, tracer: Tracer = Depends(get_tracer)) -> TraceResponse:
    events = await tracer.history(trace_id)
    return TraceResponse(trace_id=trace_id, events=events)


@router.get("/debug/kill-test/{surface_id}", response_model=UiResponse)
async def get_kill_test(
    surface_id: str, toolbox: Toolbox = Depends(get_toolbox)
) -> UiResponse:
    """Serve a persisted surface from its genuine frozen artifact, with no agent
    and no live recomputation (REQ-KT-01, REQ-KT-02, INV-032)."""
    result = await toolbox.call("kill_test", {"surface_id": surface_id})
    if result.get("status") != "ok":
        detail = "; ".join(result.get("issues") or ["no frozen artifact"])
        raise HTTPException(status_code=404, detail=detail)
    return UiResponse(
        status="ok",
        surface_id=surface_id,
        a2ui=result.get("a2ui", []),
        catalog_id=result.get("catalog_id"),
        audio_ref=result.get("audio_ref"),
    )
