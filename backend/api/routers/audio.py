"""GET /api/audio/{asset_id} — serve a cached TTS asset."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response

from mcp_servers.toolbox import Toolbox

from ..dependencies import get_toolbox
from ..schemas import HttpErrorDetail

router = APIRouter(prefix="/api", tags=["audio"])


@router.get(
    "/audio/{asset_id}",
    summary="Fetch cached TTS audio asset (REQ-API-07)",
    response_description="Raw audio stream (e.g. audio/mpeg)",
    operation_id="get_audio",
    responses={
        200: {
            "content": {"audio/mpeg": {}},
            "description": "Binary audio stream returned with public caching headers.",
        },
        404: {
            "description": "Audio asset not found or missing from cache.",
            "model": HttpErrorDetail,
        },
    },
)
async def get_audio(
    asset_id: str, toolbox: Toolbox = Depends(get_toolbox)
) -> Response:
    """Fetch pre-warmed or dynamically synthesized TTS audio bytes (REQ-API-07, REQ-ACC-03)."""
    meta = await toolbox.call("get_audio", {"asset_id": asset_id})
    if meta.get("status") != "ok":
        raise HTTPException(status_code=404, detail="unknown audio asset")
    file_path = meta.get("file_path")
    if not file_path or not Path(file_path).is_file():
        raise HTTPException(status_code=404, detail="audio file missing")
    media_type = mimetypes.guess_type(file_path)[0] or "audio/mpeg"
    return Response(
        content=Path(file_path).read_bytes(),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
