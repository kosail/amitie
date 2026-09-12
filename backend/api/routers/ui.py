"""GET /api/ui/{surface_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from mcp_servers.toolbox import Toolbox

from ..dependencies import get_toolbox
from ..schemas import HttpErrorDetail, UiResponse

router = APIRouter(prefix="/api", tags=["ui"])


@router.get(
    "/ui/{surface_id}",
    response_model=UiResponse,
    summary="Hydrate a persisted surface (REQ-API-04)",
    response_description="Hydrated A2UI surface with current financial numbers",
    operation_id="get_ui",
    responses={
        200: {
            "description": "Surface hydrated successfully with fresh data.",
            "model": UiResponse,
        },
        404: {
            "description": "Surface not found.",
            "model": HttpErrorDetail,
        },
    },
)
async def get_ui(
    surface_id: str, toolbox: Toolbox = Depends(get_toolbox)
) -> UiResponse:
    """Hydrate a persisted UI surface with fresh financial data before delivery (REQ-API-04, INV-022).

    - Resolves stored placeholders against live SQLite data.
    - Runs revalidation pass to detect any structural mutations needed.
    - Stale or cached numbers are never delivered to the client.
    """
    result = await toolbox.call("hydrate_ui", {"surface_id": surface_id})
    if result.get("status") != "ok":
        raise HTTPException(status_code=404, detail="unknown surface")
    return UiResponse(
        status="ok",
        surface_id=surface_id,
        a2ui=result.get("a2ui", []),
        issues=result.get("issues", []),
        catalog_id=result.get("catalog_id"),
        audio_ref=result.get("audio_ref"),
    )
