"""Voice MCP server: TTS synthesis (cached) and STT transcription."""

from __future__ import annotations

from typing import Any

from db.port import DatabasePort
from mcp.server import MCPServer
from providers.voice import STTProvider, TTSProvider

from . import service


def build_voice_server(
    database: DatabasePort,
    tts: TTSProvider,
    stt: STTProvider,
    *,
    tts_options: dict[str, TTSProvider] | None = None,
    stt_options: dict[str, STTProvider] | None = None,
    cache_dir: str = "./audio_cache",
) -> MCPServer:
    server = MCPServer("voice")
    tts_options = tts_options or {}
    stt_options = stt_options or {}

    def _tts_for(provider: str) -> TTSProvider | None:
        return tts_options.get(provider) if provider else tts

    def _stt_for(provider: str) -> STTProvider | None:
        return stt_options.get(provider) if provider else stt

    @server.tool()
    async def synthesize_speech(
        text: str,
        user_id: str,
        surface_id: str = "",
        voice_id: str = "",
        speed: float = 1.0,
        provider: str = "",
    ) -> dict[str, Any]:
        """Synthesize speech for an accessible surface, cached by text hash.
        Returns an audio_ref the frontend can fetch. Pass `provider` to force a
        specific engine (elevenlabs/edge_tts) instead of the configured chain."""
        chosen = _tts_for(provider)
        if chosen is None:
            return {"status": "error", "issues": [f"unknown TTS provider {provider!r}"]}
        return await service.synthesize_speech(
            database,
            chosen,
            text=text,
            user_id=user_id,
            surface_id=surface_id,
            voice_id=voice_id,
            speed=speed,
            cache_dir=cache_dir,
        )

    @server.tool()
    async def transcribe_audio(
        audio_b64: str,
        language: str = "es-MX",
        mime: str = "audio/mpeg",
        provider: str = "",
    ) -> dict[str, Any]:
        """Transcribe base64 audio input into text for the agent to interpret.
        Pass `provider` to force a specific engine (gemini/faster_whisper)."""
        chosen = _stt_for(provider)
        if chosen is None:
            return {"status": "error", "issues": [f"unknown STT provider {provider!r}"]}
        return await service.transcribe_audio(
            database, chosen, audio_b64=audio_b64, language=language, mime=mime
        )

    @server.tool()
    async def get_audio(asset_id: str) -> dict[str, Any]:
        """Return metadata for a cached audio asset."""
        return await service.get_audio(database, asset_id)

    return server
