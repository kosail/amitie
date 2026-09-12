"""Post-persist speech enrichment (REQ-ACC-03).

After an accessible surface is persisted, synthesize its speech through the
`voice` MCP and attach the audio reference to the surface data model and the
result. Deterministic and shared by AgentService and NegotiationService so every
accessible surface gets audio exactly once.
"""

from __future__ import annotations

from typing import Any

from mcp_servers.toolbox import Toolbox


class SpeechEnricher:
    def __init__(self, toolbox: Toolbox) -> None:
        self._toolbox = toolbox

    async def enrich(self, result: dict[str, Any] | None, *, user_id: str) -> dict[str, Any] | None:
        if not result or not result.get("accessible"):
            return result
        text = str(result.get("speech") or "").strip()
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
