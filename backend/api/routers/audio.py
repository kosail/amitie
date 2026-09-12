"""GET /api/audio/{asset_id} — serve a cached TTS asset."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response

from mcp_servers.toolbox import Toolbox

from ..dependencies import get_toolbox

router = APIRouter(prefix="/api", tags=["audio"])


@router.get("/audio/{asset_id}")
async def get_audio(
    asset_id: str, toolbox: Toolbox = Depends(get_toolbox)
) -> Response:
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
