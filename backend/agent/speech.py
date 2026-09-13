"""Post-persist speech enrichment.

After a surface is persisted, synthesize its speech through the `voice` MCP and
attach the audio reference to the surface data model and the result. Deterministic
and shared by AgentService and NegotiationService so every surface gets audio
exactly once.

Every audience gets audio now (product decision): accessible/simple users speak
the simplified `speech` summary, everyone else speaks the assistant's reply text
(`fallback_text`). Per-credit detail pages stay TTS-free (they never call this).
"""

from __future__ import annotations

from typing import Any

from mcp_servers.toolbox import Toolbox


class SpeechEnricher:
    def __init__(self, toolbox: Toolbox) -> None:
        self._toolbox = toolbox

    async def enrich(
        self,
        result: dict[str, Any] | None,
        *,
        user_id: str,
        fallback_text: str = "",
    ) -> dict[str, Any] | None:
        if not result:
            return result
        # Accessible/simple surfaces carry a purpose-built spoken summary; every
        # other audience speaks the assistant's own reply.
        text = str(result.get("speech") or "").strip() or str(fallback_text or "").strip()
        if not text:
            return result
        try:
            synthesis = await self._toolbox.call(
                "synthesize_speech",
                {
                    "text": text,
                    "user_id": user_id,
                    "surface_id": result.get("surface_id", ""),
                    "voice_id": result.get("voice_id", ""),
                    "speed": float(result.get("speed") or 1.0),
                },
            )
        except Exception:
            return result
        if not isinstance(synthesis, dict) or synthesis.get("status") != "ok":
            return result

        audio_ref = synthesis.get("audio_ref", "")
        result["audio_ref"] = audio_ref
        payload = {
            "text": text,
            "audioRef": audio_ref,
            "provider": synthesis.get("provider", ""),
        }
        for message in result.get("a2ui", []):
            if "updateDataModel" in message:
                value = message["updateDataModel"].get("value")
                if isinstance(value, dict):
                    value["speech"] = payload
        return result

