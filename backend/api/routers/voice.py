"""POST /debug/stt and POST /debug/tts: isolated voice I/O for testing.

DEBUG ONLY — not part of the frozen frontend contract, and not for the frontend
to call. These call the voice MCP (caching + `audio_assets`) and accept an
optional `provider` to force one engine (gemini / faster_whisper, elevenlabs /
edge_tts) so each can be validated independently instead of silently falling
back. Disabled when `ENABLE_DEBUG_ENDPOINTS=0`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Response

from mcp_servers.toolbox import Toolbox

from ..dependencies import get_toolbox
from ..schemas import SttRequest, SttResponse, TtsRequest, TtsResponse

router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/stt", response_model=SttResponse)
async def transcribe(
    payload: SttRequest, toolbox: Toolbox = Depends(get_toolbox)
) -> SttResponse:
    if not payload.audio_b64:
        return SttResponse(status="error", error_code="bad_request", message="audio_b64 is required")
    result = await toolbox.call(
        "transcribe_audio",
        {
            "audio_b64": payload.audio_b64,
            "language": payload.language,
            "mime": payload.mime,
            "provider": payload.provider,
        },
    )
    if result.get("status") != "ok":
        issues = result.get("issues") or ["transcription failed"]
        return SttResponse(
            status="error", error_code="provider_unavailable", message="; ".join(issues)
        )
    return SttResponse(
        status="ok",
        text=result.get("text", ""),
        provider=result.get("provider"),
        language=result.get("language", payload.language),
    )


@router.post("/tts")
async def synthesize(
    payload: TtsRequest,
    raw: bool = False,
    toolbox: Toolbox = Depends(get_toolbox),
):
    if not payload.text.strip():
        return TtsResponse(status="error", error_code="bad_request", message="text is required")
    result = await toolbox.call(
        "synthesize_speech",
        {
            "text": payload.text,
            "user_id": "",
            "voice_id": payload.voice_id,
            "speed": payload.speed,
            "provider": payload.provider,
        },
    )
    if result.get("status") != "ok":
        reason = result.get("reason") or "; ".join(result.get("issues") or [])
        return TtsResponse(
            status="error",
            error_code="provider_unavailable",
            message=reason or "speech synthesis failed",
        )

    audio_id = result.get("audio_id")
    audio_ref = result.get("audio_ref")
    mime = result.get("mime") or "audio/mpeg"
    meta = await toolbox.call("get_audio", {"asset_id": audio_id}) if audio_id else {}
    file_path = meta.get("file_path") if isinstance(meta, dict) else None
    size = Path(file_path).stat().st_size if file_path and Path(file_path).is_file() else None

    if raw and file_path and Path(file_path).is_file():
        return Response(
            content=Path(file_path).read_bytes(),
            media_type=mime,
            headers={
                "X-Audio-Id": str(audio_id),
                "X-Audio-Ref": str(audio_ref),
                "X-TTS-Provider": str(result.get("provider")),
            },
        )
    return TtsResponse(
        status="ok",
        audio_id=audio_id,
        audio_ref=audio_ref,
        provider=result.get("provider"),
        mime=mime,
        bytes=size,
        cached=bool(result.get("cached", False)),
    )
