"""GET /api/ui/{surface_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from mcp_servers.toolbox import Toolbox

from ..dependencies import get_toolbox
from ..schemas import UiResponse

router = APIRouter(prefix="/api", tags=["ui"])


@router.get("/ui/{surface_id}", response_model=UiResponse)
async def get_ui(
    surface_id: str, toolbox: Toolbox = Depends(get_toolbox)
) -> UiResponse:
    result = await toolbox.call("hydrate_ui", {"surface_id": surface_id})
    if result.get("status") != "ok":
        raise HTTPException(status_code=404, detail="unknown surface")
    return UiResponse(
        status="ok",
        surface_id=surface_id,
        a2ui=result.get("a2ui", []),
        issues=result.get("issues", []),
    )
